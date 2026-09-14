"""Typed FFmpeg media processing."""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aasg.errors import PrerequisiteError, ProcessingError
from aasg.frames import FrameAsset, resolve_frame
from aasg.models import (
    AasgConfig,
    BackgroundStep,
    BlurStep,
    CropStep,
    DeviceFrameStep,
    EdgeFadeStep,
    FeatherStep,
    PadStep,
    PipelineConfig,
    RedactStep,
    Region,
    ResizeStep,
    SemanticMetadata,
    TemporalFadeStep,
    TrimStep,
)


@dataclass
class MediaInfo:
    kind: str
    width: int
    height: int
    duration: float | None


@dataclass(frozen=True)
class ProcessingResult:
    commands: list[str]
    frames: list[dict[str, Any]]


def probe(path: Path, ffprobe: str = "ffprobe") -> MediaInfo:
    try:
        result = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_type,width,height:format=duration",
                "-of",
                "json",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        duration_value = data.get("format", {}).get("duration")
        duration = float(duration_value) if duration_value is not None else None
        kind = "image" if duration is None or duration <= 0.05 else "video"
        return MediaInfo(kind, int(stream["width"]), int(stream["height"]), duration)
    except FileNotFoundError as error:
        raise PrerequisiteError(f"Executable not found: {ffprobe}") from error
    except (subprocess.SubprocessError, KeyError, ValueError, json.JSONDecodeError) as error:
        raise ProcessingError(f"Unreadable media file: {path}") from error


class MediaProcessor:
    def __init__(self, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> None:
        self.ffmpeg = ffmpeg
        self.ffprobe = ffprobe
        self._frame_bounds: dict[tuple[Path, int, int], Region] = {}

    def process(
        self,
        source: Path,
        destination: Path,
        pipeline: PipelineConfig,
        *,
        config: AasgConfig,
        config_path: Path,
        metadata_path: Path | None = None,
        variables: dict[str, str] | None = None,
        dry_run: bool = False,
    ) -> ProcessingResult:
        if not source.is_file():
            raise ProcessingError(f"Input media does not exist: {source}")
        info = probe(source, self.ffprobe)
        metadata = self._load_metadata(metadata_path, source.name)
        commands: list[str] = []
        frame_provenance: list[dict[str, Any]] = []
        destination.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="aasg-media-") as temporary_name:
            temporary_root = Path(temporary_name)
            current = source
            for index, step in enumerate(pipeline.steps):
                if info.kind == "video" and isinstance(step, (EdgeFadeStep, FeatherStep)):
                    raise ProcessingError(f"{step.type} supports images only")
                if info.kind == "image" and isinstance(step, (TrimStep, TemporalFadeStep)):
                    raise ProcessingError(f"{step.type} supports videos only")
                suffix = ".png" if info.kind == "image" else ".mkv"
                output = temporary_root / f"step-{index:02d}{suffix}"
                command, info, provenance = self._command_for_step(
                    current,
                    output,
                    step,
                    info,
                    metadata,
                    config,
                    config_path,
                    variables or {},
                )
                commands.append(shlex.join(command))
                if provenance:
                    frame_provenance.append(provenance)
                if not dry_run:
                    self._execute(command)
                    current = output

            final_temporary = temporary_root / (
                "final.png" if info.kind == "image" else "final.mp4"
            )
            if info.kind == "image":
                if pipeline.steps:
                    if not dry_run:
                        shutil.copy2(current, final_temporary)
                else:
                    commands.append(
                        f"copy {shlex.quote(str(source))} {shlex.quote(str(destination))}"
                    )
                    if not dry_run:
                        shutil.copy2(source, final_temporary)
            else:
                padding_color = self._video_padding_color(pipeline, variables or {})
                final_command = [
                    self.ffmpeg,
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-i",
                    str(current),
                    "-vf",
                    f"fps={pipeline.frame_rate},"
                    "pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:"
                    f"color={padding_color},format=yuv420p",
                    "-an",
                    "-c:v",
                    "libx264",
                    "-crf",
                    str(pipeline.crf),
                    "-movflags",
                    "+faststart",
                    str(final_temporary),
                ]
                commands.append(shlex.join(final_command))
                if not dry_run:
                    self._execute(final_command)
            if not dry_run:
                final_temporary.replace(destination)
                probe(destination, self.ffprobe)
        return ProcessingResult(commands, frame_provenance)

    @staticmethod
    def _video_padding_color(pipeline: PipelineConfig, variables: dict[str, str]) -> str:
        for step in reversed(pipeline.steps):
            if isinstance(step, DeviceFrameStep) and step.background is not None:
                return MediaProcessor._variant_value(
                    step.background, variables, "device-frame background"
                )
            if isinstance(step, BackgroundStep):
                return MediaProcessor._variant_value(step.color, variables, "background color")
        return "black"

    @staticmethod
    def _load_metadata(path: Path | None, media_name: str) -> SemanticMetadata | None:
        if path is None:
            return None
        try:
            metadata = SemanticMetadata.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ProcessingError(f"Invalid semantic metadata: {path}") from error
        if metadata.media != media_name:
            raise ProcessingError(
                f"Semantic metadata names {metadata.media!r}, expected {media_name!r}"
            )
        return metadata

    def _command_for_step(
        self,
        source: Path,
        output: Path,
        step: object,
        info: MediaInfo,
        metadata: SemanticMetadata | None,
        config: AasgConfig,
        config_path: Path,
        variables: dict[str, str],
    ) -> tuple[list[str], MediaInfo, dict[str, Any] | None]:
        if isinstance(step, ResizeStep):
            if step.fit == "stretch":
                expression = f"scale={step.width}:{step.height}"
            elif step.fit == "contain":
                expression = (
                    f"scale={step.width}:{step.height}:force_original_aspect_ratio=decrease,"
                    f"pad={step.width}:{step.height}:(ow-iw)/2:(oh-ih)/2:color=black@0"
                )
            else:
                expression = (
                    f"scale={step.width}:{step.height}:force_original_aspect_ratio=increase,"
                    f"crop={step.width}:{step.height}"
                )
            return (
                self._filtered(source, output, expression, info),
                MediaInfo(info.kind, step.width, step.height, info.duration),
                None,
            )
        if isinstance(step, CropStep):
            region = self._crop_region(step, metadata, info)
            expression = f"crop={region.width}:{region.height}:{region.x}:{region.y}"
            return (
                self._filtered(source, output, expression, info),
                MediaInfo(info.kind, region.width, region.height, info.duration),
                None,
            )
        if isinstance(step, PadStep):
            if step.width < info.width or step.height < info.height:
                raise ProcessingError("pad dimensions cannot be smaller than the input")
            expression = f"pad={step.width}:{step.height}:(ow-iw)/2:(oh-ih)/2:color={step.color}"
            return (
                self._filtered(source, output, expression, info),
                MediaInfo(info.kind, step.width, step.height, info.duration),
                None,
            )
        if isinstance(step, BackgroundStep):
            color = self._variant_value(step.color, variables, "background color")
            command = self._background(source, output, color, info)
            return command, info, None
        if isinstance(step, BlurStep):
            return self._filtered(source, output, f"gblur=sigma={step.sigma}", info), info, None
        if isinstance(step, RedactStep):
            command = self._redact(source, output, step, info, metadata)
            return command, info, None
        if isinstance(step, EdgeFadeStep):
            expression = self._alpha_expression(step.edges, step.pixels)
            command = self._alpha_mask(source, output, expression, info)
            return command, info, None
        if isinstance(step, FeatherStep):
            expression = self._alpha_expression(["top", "right", "bottom", "left"], step.pixels)
            command = self._alpha_mask(source, output, expression, info)
            return command, info, None
        if isinstance(step, TrimStep):
            expression = (
                f"trim=start={step.start_seconds}:duration={step.duration_seconds},"
                "setpts=PTS-STARTPTS"
            )
            command = self._filtered(source, output, expression, info)
            return (
                command,
                MediaInfo(info.kind, info.width, info.height, step.duration_seconds),
                None,
            )
        if isinstance(step, TemporalFadeStep):
            filters: list[str] = []
            if step.in_seconds:
                filters.append(f"fade=t=in:st=0:d={step.in_seconds}")
            if step.out_seconds:
                if info.duration is None or step.out_seconds > info.duration:
                    raise ProcessingError("temporal fade-out requires a known, sufficient duration")
                filters.append(
                    f"fade=t=out:st={info.duration - step.out_seconds}:d={step.out_seconds}"
                )
            return self._filtered(source, output, ",".join(filters) or "null", info), info, None
        if isinstance(step, DeviceFrameStep):
            asset = resolve_frame(config, config_path, step.source, step.frame)
            background = (
                self._variant_value(step.background, variables, "device-frame background")
                if step.background is not None
                else None
            )
            crop = self._frame_crop(asset) if step.crop_to_frame else None
            command = self._device_frame(source, output, step, info, asset, background, crop)
            size = asset.metadata.frame_size
            provenance = dict(asset.provenance)
            if crop is not None:
                provenance["crop"] = {
                    "mode": "alpha_bounds",
                    "x": crop.x,
                    "y": crop.y,
                    "width": crop.width,
                    "height": crop.height,
                }
            return (
                command,
                MediaInfo(
                    info.kind,
                    crop.width if crop is not None else size["width"],
                    crop.height if crop is not None else size["height"],
                    info.duration,
                ),
                provenance,
            )
        raise ProcessingError(f"Unsupported pipeline step: {step!r}")

    def _filtered(self, source: Path, output: Path, expression: str, info: MediaInfo) -> list[str]:
        command = [
            self.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-vf",
            expression,
        ]
        return self._output_options(command, output, info)

    def _background(self, source: Path, output: Path, color: str, info: MediaInfo) -> list[str]:
        command = [
            self.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c={color}:s={info.width}x{info.height},format=bgra",
            "-i",
            str(source),
            "-filter_complex",
            "[0:v][1:v]overlay=0:0:format=auto:shortest=1",
        ]
        return self._output_options(command, output, info)

    def _redact(
        self,
        source: Path,
        output: Path,
        step: RedactStep,
        info: MediaInfo,
        metadata: SemanticMetadata | None,
    ) -> list[str]:
        if metadata is None:
            raise ProcessingError("redact requires semantic metadata")
        regions = [self._metadata_region(metadata, name) for name in step.regions]
        if step.mode == "solid":
            expression = ",".join(
                f"drawbox=x={r.x}:y={r.y}:w={r.width}:h={r.height}:color={step.color}:t=fill"
                for r in regions
            )
            return self._filtered(source, output, expression, info)
        chains: list[str] = []
        current = "0:v"
        for index, region in enumerate(regions):
            chains.append(f"[{current}]split[base{index}][blur{index}]")
            chains.append(
                f"[blur{index}]crop={region.width}:{region.height}:{region.x}:{region.y},"
                f"gblur=sigma={step.sigma}[patch{index}]"
            )
            next_label = f"redacted{index}"
            chains.append(f"[base{index}][patch{index}]overlay={region.x}:{region.y}[{next_label}]")
            current = next_label
        command = [
            self.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-filter_complex",
            ";".join(chains),
            "-map",
            f"[{current}]",
        ]
        return self._output_options(command, output, info)

    def _alpha_mask(
        self, source: Path, output: Path, expression: str, info: MediaInfo
    ) -> list[str]:
        command = [
            self.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(source),
            "-f",
            "lavfi",
            "-i",
            f"color=white:s={info.width}x{info.height}",
            "-filter_complex",
            f"[0:v]format=rgba[base];[1:v]format=gray,geq=lum='{expression}'[alpha];"
            "[base][alpha]alphamerge",
        ]
        return self._output_options(command, output, info)

    def _device_frame(
        self,
        source: Path,
        output: Path,
        step: DeviceFrameStep,
        info: MediaInfo,
        asset: FrameAsset,
        background: str | None,
        crop: Region | None,
    ) -> list[str]:
        screen = asset.metadata.screen
        frame_size = asset.metadata.frame_size
        if step.fit == "stretch":
            fit = f"scale={screen.width}:{screen.height}"
        elif step.fit == "contain":
            fit = (
                f"scale={screen.width}:{screen.height}:force_original_aspect_ratio=decrease,"
                f"pad={screen.width}:{screen.height}:(ow-iw)/2:(oh-ih)/2:color=black"
            )
        else:
            fit = (
                f"scale={screen.width}:{screen.height}:force_original_aspect_ratio=increase,"
                f"crop={screen.width}:{screen.height}"
            )
        filter_parts = [
            f"[0:v]{fit},format=rgba[screen]",
            f"color=c=black@0.0:s={frame_size['width']}x{frame_size['height']},format=rgba[canvas]",
            f"[canvas][screen]overlay={screen.x}:{screen.y}:format=auto:shortest=1[screen_canvas]",
            "[2:v]format=gray[mask]",
            "[screen_canvas][mask]alphamerge[masked]",
            "[masked][1:v]overlay=0:0:format=auto:shortest=1[framed]",
        ]
        final_label = "framed"
        if background:
            filter_parts.extend(
                [
                    f"color=c={background}:s={frame_size['width']}x{frame_size['height']}[bg]",
                    "[bg][framed]overlay=0:0:format=auto:shortest=1[final]",
                ]
            )
            final_label = "final"
        if crop is not None and (
            crop.x != 0
            or crop.y != 0
            or crop.width != frame_size["width"]
            or crop.height != frame_size["height"]
        ):
            filter_parts.append(
                f"[{final_label}]crop={crop.width}:{crop.height}:{crop.x}:{crop.y}[cropped]"
            )
            final_label = "cropped"
        command = [self.ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(source)]
        if info.kind == "video":
            command.extend(["-loop", "1"])
        command.extend(["-i", str(asset.frame_path)])
        if info.kind == "video":
            command.extend(["-loop", "1"])
        command.extend(
            [
                "-i",
                str(asset.mask_path),
                "-filter_complex",
                ";".join(filter_parts),
                "-map",
                f"[{final_label}]",
            ]
        )
        return self._output_options(command, output, info)

    def _frame_crop(self, asset: FrameAsset) -> Region:
        frame_size = asset.metadata.frame_size
        frame_path = asset.frame_path.resolve()
        stat = frame_path.stat()
        key = (frame_path, stat.st_size, stat.st_mtime_ns)
        cached = self._frame_bounds.get(key)
        if cached is not None:
            return cached
        width = frame_size["width"]
        height = frame_size["height"]
        command = [
            self.ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(frame_path),
            "-vf",
            "format=rgba,alphaextract",
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "pipe:1",
        ]
        try:
            result = subprocess.run(command, check=True, capture_output=True, timeout=30)
        except FileNotFoundError as error:
            raise PrerequisiteError(f"Executable not found: {self.ffmpeg}") from error
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise ProcessingError(f"Could not inspect frame alpha: {frame_path}") from error
        alpha = result.stdout
        expected_size = width * height
        if len(alpha) != expected_size:
            raise ProcessingError(f"Frame dimensions do not match frameSize metadata: {frame_path}")
        min_x = width
        min_y = height
        max_x = -1
        max_y = -1
        for index, value in enumerate(alpha):
            if value == 0:
                continue
            x = index % width
            y = index // width
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
        if max_x < 0 or max_y < 0:
            raise ProcessingError(f"Cannot crop a fully transparent device frame: {frame_path}")
        crop = Region(
            x=min_x,
            y=min_y,
            width=max_x - min_x + 1,
            height=max_y - min_y + 1,
        )
        screen = asset.metadata.screen
        if (
            screen.x < crop.x
            or screen.y < crop.y
            or screen.x + screen.width > crop.x + crop.width
            or screen.y + screen.height > crop.y + crop.height
        ):
            raise ProcessingError(
                f"Frame alpha bounds do not contain the configured screen rectangle: {frame_path}"
            )
        self._frame_bounds[key] = crop
        return crop

    @staticmethod
    def _variant_value(
        value: str | dict[str, str], variables: dict[str, str], description: str
    ) -> str:
        if isinstance(value, str):
            return value
        theme = variables.get("theme")
        if theme is None or theme not in value:
            raise ProcessingError(f"{description} requires a configured --theme value")
        return value[theme]

    @staticmethod
    def _crop_region(step: CropStep, metadata: SemanticMetadata | None, info: MediaInfo) -> Region:
        if step.region:
            if metadata is None:
                raise ProcessingError(f"crop region {step.region!r} requires semantic metadata")
            original = MediaProcessor._metadata_region(metadata, step.region)
        else:
            assert step.x is not None and step.y is not None
            assert step.width is not None and step.height is not None
            original = Region(x=step.x, y=step.y, width=step.width, height=step.height)
        x = original.x - step.padding
        y = original.y - step.padding
        width = original.width + 2 * step.padding
        height = original.height + 2 * step.padding
        if x < 0 or y < 0 or x + width > info.width or y + height > info.height:
            raise ProcessingError("crop plus padding exceeds media bounds")
        return Region(x=x, y=y, width=width, height=height)

    @staticmethod
    def _metadata_region(metadata: SemanticMetadata, name: str) -> Region:
        try:
            return metadata.regions[name]
        except KeyError as error:
            raise ProcessingError(f"Semantic region not found: {name}") from error

    @staticmethod
    def _alpha_expression(edges: Sequence[str], pixels: int) -> str:
        terms = ["1"]
        mapping = {
            "top": f"Y/{pixels}",
            "right": f"(W-1-X)/{pixels}",
            "bottom": f"(H-1-Y)/{pixels}",
            "left": f"X/{pixels}",
        }
        terms.extend(mapping[edge] for edge in edges)
        expression = terms[0]
        for term in terms[1:]:
            expression = f"min({expression},{term})"
        return f"255*max(0,{expression})"

    @staticmethod
    def _output_options(command: list[str], output: Path, info: MediaInfo) -> list[str]:
        if info.kind == "image":
            return [*command, "-frames:v", "1", str(output)]
        duration = ["-t", f"{info.duration:.6f}"] if info.duration is not None else []
        return [
            *command,
            *duration,
            "-an",
            "-c:v",
            "ffv1",
            "-pix_fmt",
            "bgra",
            str(output),
        ]

    @staticmethod
    def _execute(command: list[str]) -> None:
        try:
            subprocess.run(command, check=True, timeout=300)
        except FileNotFoundError as error:
            raise PrerequisiteError(f"Executable not found: {command[0]}") from error
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise ProcessingError(f"Media command failed: {shlex.join(command)}") from error
