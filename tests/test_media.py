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
    output = tmp_path / "clip.mp4"

    result = MediaProcessor().process(
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
    assert "pad=ceil(iw/2)*2:ceil(ih/2)*2:0:0:color=white" in result.commands[-1]
