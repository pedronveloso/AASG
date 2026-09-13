from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from conftest import write_config

from aasg.config import load_config
from aasg.errors import ConfigurationError
from aasg.frames import refresh_source, resolve_frame
from aasg.models import RemoteFrameSource


def test_loads_local_frame_pack(tmp_path: Path) -> None:
    frame_root = tmp_path / "frames" / "android-phone" / "generic" / "black"
    frame_root.mkdir(parents=True)
    frame_bytes = b"frame"
    mask_bytes = b"mask"
    (frame_root / "frame.png").write_bytes(frame_bytes)
    (frame_root / "mask.png").write_bytes(mask_bytes)
    (frame_root / "template.json").write_text(
        json.dumps(
            {
                "frame": "frame.png",
                "mask": "mask.png",
                "screen": {"x": 10, "y": 20, "width": 100, "height": 200},
                "frameSize": {"width": 120, "height": 240},
                "hexColor": "#000000",
                "sha256": {
                    "frame": hashlib.sha256(frame_bytes).hexdigest(),
                    "mask": hashlib.sha256(mask_bytes).hexdigest(),
                },
            }
        )
    )
    path = write_config(
        tmp_path,
        {"frame_sources": {"local": {"kind": "local", "root": "frames", "license": "CC0-1.0"}}},
    )
    config = load_config(path)

    asset = resolve_frame(config, path, "local", "android-phone/generic/black")

    assert asset.metadata.screen.width == 100
    assert asset.provenance["license"] == "CC0-1.0"


def test_refresh_invalidates_cached_assets(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    root = tmp_path / "cache"
    assets = root / "assets"
    assets.mkdir(parents=True)
    (assets / "old-frame.png").write_bytes(b"old")
    monkeypatch.setattr("aasg.frames._source_cache", lambda _name: root)
    monkeypatch.setattr("aasg.frames.load_remote_index", lambda *args, **kwargs: ({}, {}))

    refresh_source(
        "community",
        RemoteFrameSource(kind="device-frames-media", allow_unlicensed_downloads=True),
    )

    assert not assets.exists()


def test_local_frame_paths_cannot_escape_pack(tmp_path: Path) -> None:
    frame_root = tmp_path / "frames" / "generic"
    frame_root.mkdir(parents=True)
    (tmp_path / "outside.png").write_bytes(b"outside")
    mask = frame_root / "mask.png"
    mask.write_bytes(b"mask")
    (frame_root / "template.json").write_text(
        json.dumps(
            {
                "frame": "../../outside.png",
                "mask": "mask.png",
                "screen": {"x": 1, "y": 1, "width": 10, "height": 10},
                "frameSize": {"width": 12, "height": 12},
                "sha256": {
                    "frame": hashlib.sha256(b"outside").hexdigest(),
                    "mask": hashlib.sha256(b"mask").hexdigest(),
                },
            }
        )
    )
    path = write_config(
        tmp_path,
        {"frame_sources": {"local": {"kind": "local", "root": "frames", "license": "MIT"}}},
    )
    config = load_config(path)

    with pytest.raises(ConfigurationError, match="escapes"):
        resolve_frame(config, path, "local", "generic")
