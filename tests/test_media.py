from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from conftest import write_config

from aasg.config import load_config
from aasg.errors import ProcessingError
from aasg.media import MediaProcessor, probe
from aasg.models import AasgConfig


def make_image(path: Path, *, size: str = "100x100", color: str = "red") -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color={color}:s={size}",
            "-frames:v",
            "1",
            str(path),
        ],
        check=True,
    )


def rgba_pixels(path: Path) -> bytes:
    return subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "rgba",
            "pipe:1",
        ],
        check=True,
        capture_output=True,
    ).stdout


def make_local_frame(
    root: Path,
    *,
    frame_source: str,
    screen: dict[str, int],
    frame_size: tuple[int, int] = (120, 240),
) -> None:
    frame_root = root / "frames" / "android-phone" / "generic" / "black"
    frame_root.mkdir(parents=True)
    frame_path = frame_root / "frame.png"
    mask_path = frame_root / "mask.png"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            frame_source,
            "-frames:v",
            "1",
            str(frame_path),
        ],
        check=True,
    )
    width, height = frame_size
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            f"color=black:s={width}x{height},format=gray,"
            f"drawbox=x={screen['x']}:y={screen['y']}:w={screen['width']}:"
            f"h={screen['height']}:color=white:t=fill",
            "-frames:v",
            "1",
            str(mask_path),
        ],
        check=True,
    )
    (frame_root / "template.json").write_text(
        json.dumps(
            {
                "frame": "frame.png",
                "mask": "mask.png",
                "screen": screen,
                "frameSize": {"width": width, "height": height},
                "sha256": {
                    "frame": hashlib.sha256(frame_path.read_bytes()).hexdigest(),
                    "mask": hashlib.sha256(mask_path.read_bytes()).hexdigest(),
                },
            }
        )
    )


def frame_pipeline_config(
    root: Path,
    *,
    crop_to_frame: bool,
    background: str | dict[str, str] | None = None,
) -> tuple[Path, AasgConfig]:
    step: dict[str, object] = {
        "type": "device_frame",
        "source": "local",
        "frame": "android-phone/generic/black",
        "fit": "contain",
        "crop_to_frame": crop_to_frame,
    }
    if background is not None:
        step["background"] = background
    path = write_config(
        root,
        {
            "frame_sources": {"local": {"kind": "local", "root": "frames", "license": "CC0-1.0"}},
            "pipelines": {"frame": {"steps": [step]}},
        },
    )
    return path, load_config(path)


def test_semantic_crop_and_feather(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    make_image(source)
    metadata = tmp_path / "source.metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "schema": 1,
                "media": "source.png",
                "regions": {"card": {"x": 20, "y": 20, "width": 40, "height": 40}},
            }
        )
    )
    path = write_config(
        tmp_path,
        {
            "pipelines": {
                "card": {
                    "steps": [
                        {"type": "crop", "region": "card", "padding": 10},
                        {"type": "feather", "pixels": 10},
                    ]
                }
            }
        },
    )
    config = load_config(path)
    output = tmp_path / "card.png"

    MediaProcessor().process(
        source,
        output,
        config.pipelines["card"],
        config=config,
        config_path=path,
        metadata_path=metadata,
    )

    info = probe(output)
    assert (info.width, info.height) == (60, 60)
    pixels = rgba_pixels(output)
    assert pixels[3] < pixels[(30 * 60 + 30) * 4 + 3]


def test_image_pipeline_operations_and_directional_alpha(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    make_image(source)
    metadata = tmp_path / "source.metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "schema": 1,
                "media": source.name,
                "regions": {"secret": {"x": 10, "y": 10, "width": 20, "height": 20}},
            }
        )
    )
    path = write_config(
        tmp_path,
        {
            "pipelines": {
                "poster": {
                    "steps": [
                        {"type": "redact", "regions": ["secret"], "mode": "solid"},
                        {"type": "blur", "sigma": 1.0},
                        {"type": "resize", "width": 80, "height": 60, "fit": "stretch"},
                        {"type": "pad", "width": 100, "height": 80, "color": "black"},
                        {
                            "type": "background",
                            "color": {"light": "white", "dark": "black"},
                        },
                        {"type": "edge_fade", "edges": ["bottom"], "pixels": 12},
                    ]
                }
            }
        },
    )
    config = load_config(path)
    output = tmp_path / "poster.png"

    MediaProcessor().process(
        source,
        output,
        config.pipelines["poster"],
        config=config,
        config_path=path,
        metadata_path=metadata,
        variables={"theme": "light"},
    )

    info = probe(output)
    pixels = rgba_pixels(output)
    assert (info.width, info.height) == (100, 80)
    assert pixels[(10 * 100 + 50) * 4 + 3] > pixels[(79 * 100 + 50) * 4 + 3]


def test_metadata_must_name_its_media(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    make_image(source)
    metadata = tmp_path / "wrong.metadata.json"
    metadata.write_text(json.dumps({"schema": 1, "media": "other.png", "regions": {}}))
    path = write_config(tmp_path, {"pipelines": {"noop": {"steps": []}}})
    config = load_config(path)

    with pytest.raises(ProcessingError, match=r"expected 'source\.png'"):
        MediaProcessor().process(
            source,
            tmp_path / "out.png",
            config.pipelines["noop"],
            config=config,
            config_path=path,
            metadata_path=metadata,
        )


def test_framed_trimmed_video(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=50x100:rate=20:duration=2",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
    )
    frame_root = tmp_path / "frames" / "android-phone" / "generic" / "black"
    frame_root.mkdir(parents=True)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=black@0.0:s=120x240,format=rgba,drawbox=x=0:y=0:w=120:h=240:color=blue:t=5",
            "-frames:v",
            "1",
            str(frame_root / "frame.png"),
        ],
        check=True,
    )
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=black:s=120x240,format=gray,drawbox=x=10:y=20:w=100:h=200:color=white:t=fill",
            "-frames:v",
            "1",
            str(frame_root / "mask.png"),
        ],
        check=True,
    )
    (frame_root / "template.json").write_text(
        json.dumps(
            {
                "frame": "frame.png",
                "mask": "mask.png",
                "screen": {"x": 10, "y": 20, "width": 100, "height": 200},
                "frameSize": {"width": 120, "height": 240},
                "sha256": {
                    "frame": hashlib.sha256((frame_root / "frame.png").read_bytes()).hexdigest(),
                    "mask": hashlib.sha256((frame_root / "mask.png").read_bytes()).hexdigest(),
                },
            }
        )
    )
    path = write_config(
        tmp_path,
        {
            "frame_sources": {"local": {"kind": "local", "root": "frames", "license": "CC0-1.0"}},
            "pipelines": {
                "clip": {
                    "frame_rate": 30,
                    "crf": 18,
                    "steps": [
                        {"type": "trim", "start_seconds": 0.2, "duration_seconds": 1.0},
                        {"type": "temporal_fade", "in_seconds": 0.1, "out_seconds": 0.1},
                        {
                            "type": "device_frame",
                            "source": "local",
                            "frame": "android-phone/generic/black",
                            "fit": "contain",
                            "background": {"light": "white", "dark": "black"},
                        },
                    ],
                }
            },
        },
    )
    config = load_config(path)
    assert config.pipelines["clip"].steps[-1].model_dump()["crop_to_frame"] is False
    output = tmp_path / "clip.mp4"

    processor = MediaProcessor()
    result = processor.process(
        source,
        output,
        config.pipelines["clip"],
        config=config,
        config_path=path,
        variables={"theme": "dark"},
    )

    info = probe(output)
    stream = json.loads(
        subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=codec_name,pix_fmt,r_frame_rate",
                "-of",
                "json",
                str(output),
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    )["streams"][0]
    assert (info.width, info.height) == (120, 240)
    assert info.duration == pytest.approx(1.0, abs=0.1)
    assert stream == {"codec_name": "h264", "pix_fmt": "yuv420p", "r_frame_rate": "30/1"}
    assert result.frames[0]["license"] == "CC0-1.0"


def test_device_frame_crops_transparent_margins_and_records_bounds(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    make_image(source, size="50x100")
    screen = {"x": 20, "y": 30, "width": 80, "height": 180}
    make_local_frame(
        tmp_path,
        frame_source=(
            "color=black@0.0:s=120x240,format=rgba,"
            "drawbox=x=10:y=20:w=100:h=200:color=blue@1.0:t=5:replace=1"
        ),
        screen=screen,
    )
    path, config = frame_pipeline_config(tmp_path, crop_to_frame=True)
    output = tmp_path / "cropped.png"

    processor = MediaProcessor()
    result = processor.process(
        source,
        output,
        config.pipelines["frame"],
        config=config,
        config_path=path,
    )

    info = probe(output)
    assert (info.width, info.height) == (100, 200)
    assert result.frames[0]["crop"] == {
        "mode": "alpha_bounds",
        "x": 10,
        "y": 20,
        "width": 100,
        "height": 200,
    }
    assert "crop=100:200:10:20" in result.commands[-1]
    pixels = rgba_pixels(output)
    assert any(pixels[index] for index in range(3, info.width * 4, 4))
    bottom_alpha = (info.height - 1) * info.width * 4 + 3
    assert any(pixels[index] for index in range(bottom_alpha, len(pixels), 4))
    assert any(pixels[row * info.width * 4 + 3] for row in range(info.height))
    assert any(pixels[(row * info.width + info.width - 1) * 4 + 3] for row in range(info.height))
    dry_run = processor.process(
        source,
        tmp_path / "planned.png",
        config.pipelines["frame"],
        config=config,
        config_path=path,
        dry_run=True,
    )
    assert "crop=100:200:10:20" in dry_run.commands[-1]
    assert dry_run.frames[0]["crop"] == result.frames[0]["crop"]
    assert len(processor._frame_bounds) == 1


def test_cropped_device_frame_video_is_padded_to_even_dimensions(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=50x100:rate=10:duration=0.2",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
    )
    screen = {"x": 20, "y": 30, "width": 80, "height": 180}
    make_local_frame(
        tmp_path,
        frame_source=(
            "color=black@0.0:s=120x240,format=rgba,"
            "drawbox=x=10:y=20:w=101:h=201:color=blue@1.0:t=5:replace=1"
        ),
        screen=screen,
    )
    path, config = frame_pipeline_config(
        tmp_path,
        crop_to_frame=True,
        background={"light": "white", "dark": "black"},
    )
    output = tmp_path / "cropped.mp4"

    result = MediaProcessor().process(
        source,
        output,
        config.pipelines["frame"],
        config=config,
        config_path=path,
        variables={"theme": "light"},
    )

    info = probe(output)
    assert (info.width, info.height) == (102, 202)
    assert result.frames[0]["crop"]["width"] == 101
    assert result.frames[0]["crop"]["height"] == 201


def test_crop_to_frame_treats_opaque_frame_as_already_tight(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    make_image(source, size="50x100")
    screen = {"x": 10, "y": 20, "width": 100, "height": 200}
    make_local_frame(
        tmp_path,
        frame_source="color=blue:s=120x240,format=rgba",
        screen=screen,
    )
    path, config = frame_pipeline_config(tmp_path, crop_to_frame=True)
    output = tmp_path / "opaque.png"

    result = MediaProcessor().process(
        source,
        output,
        config.pipelines["frame"],
        config=config,
        config_path=path,
    )

    info = probe(output)
    assert (info.width, info.height) == (120, 240)
    assert result.frames[0]["crop"]["width"] == 120
    assert "crop=" not in result.commands[-1]


@pytest.mark.parametrize(
    ("frame_source", "screen", "message"),
    [
        (
            "color=black@0.0:s=120x240,format=rgba",
            {"x": 10, "y": 20, "width": 100, "height": 200},
            "fully transparent",
        ),
        (
            "color=black@0.0:s=120x240,format=rgba,"
            "drawbox=x=20:y=30:w=80:h=180:color=blue@1.0:t=5:replace=1",
            {"x": 10, "y": 20, "width": 100, "height": 200},
            "do not contain",
        ),
    ],
)
def test_crop_to_frame_rejects_invalid_frame_alpha(
    tmp_path: Path,
    frame_source: str,
    screen: dict[str, int],
    message: str,
) -> None:
    source = tmp_path / "source.png"
    make_image(source, size="50x100")
    make_local_frame(tmp_path, frame_source=frame_source, screen=screen)
    path, config = frame_pipeline_config(tmp_path, crop_to_frame=True)

    with pytest.raises(ProcessingError, match=message):
        MediaProcessor().process(
            source,
            tmp_path / "invalid.png",
            config.pipelines["frame"],
            config=config,
            config_path=path,
        )


def test_video_encoder_pads_odd_dimensions_with_pipeline_background(tmp_path: Path) -> None:
    source = tmp_path / "source.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=50x100:rate=10:duration=0.2",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
    )
    path = write_config(
        tmp_path,
        {
            "pipelines": {
                "odd": {
                    "steps": [
                        {"type": "resize", "width": 101, "height": 201, "fit": "stretch"},
                        {"type": "background", "color": {"light": "white", "dark": "black"}},
                    ]
                }
            }
        },
    )
    config = load_config(path)
    output = tmp_path / "odd.mp4"

    result = MediaProcessor().process(
        source,
        output,
        config.pipelines["odd"],
        config=config,
        config_path=path,
        variables={"theme": "light"},
    )

    info = probe(output)
    assert (info.width, info.height) == (102, 202)
    assert "color=c=white:s=101x201,format=bgra" in result.commands[-2]
    assert "pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:color=white" in result.commands[-1]
