"""Device-frame providers and cache management."""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from platformdirs import user_cache_path

from aasg.config import project_path, resolve_inside
from aasg.errors import AasgError, ConfigurationError, PrerequisiteError
from aasg.models import AasgConfig, FrameMetadata, LocalFrameSource, RemoteFrameSource


@dataclass(frozen=True)
class FrameAsset:
    frame_id: str
    frame_path: Path
    mask_path: Path
    metadata: FrameMetadata
    provenance: dict[str, Any]


def cache_root() -> Path:
    return user_cache_path("aasg") / "frames"


def _source_cache(name: str) -> Path:
    safe = hashlib.sha256(name.encode()).hexdigest()[:16]
    return cache_root() / safe


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_sha256(path: Path, expected: object, description: str) -> None:
    if not isinstance(expected, str) or _sha256(path).lower() != expected.lower():
        raise PrerequisiteError(f"Cached {description} failed SHA-256 verification: {path}")


def _download(url: str, destination: Path) -> dict[str, str | None]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with httpx.stream("GET", url, follow_redirects=True, timeout=30) as response:
            response.raise_for_status()
            with temporary.open("wb") as output:
                for chunk in response.iter_bytes():
                    output.write(chunk)
            etag = response.headers.get("etag")
    except (httpx.HTTPError, OSError) as error:
        temporary.unlink(missing_ok=True)
        raise PrerequisiteError(f"Could not download frame asset {url}: {error}") from error
    temporary.replace(destination)
    return {"etag": etag, "sha256": _sha256(destination)}


def load_remote_index(
    source_name: str,
    source: RemoteFrameSource,
    *,
    refresh: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not source.allow_unlicensed_downloads:
        raise ConfigurationError(
            f"Frame source {source_name!r} has no recognized license. Set "
            "allow_unlicensed_downloads: true to opt in without redistributing its assets."
        )
    root = _source_cache(source_name)
    index_path = root / "index.json"
    manifest_path = root / "index-manifest.json"
    if refresh or not index_path.is_file():
        download = _download(source.index_url, index_path)
        manifest = {
            "url": source.index_url,
            "retrieved_at": datetime.now(UTC).isoformat(),
            **download,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError) as error:
        raise PrerequisiteError(f"Invalid cached frame index for {source_name!r}") from error
    if not isinstance(index, dict) or not isinstance(manifest, dict):
        raise PrerequisiteError(f"Invalid cached frame index for {source_name!r}")
    _verify_sha256(index_path, manifest.get("sha256"), f"index for {source_name!r}")
    return index, manifest


def list_frames(source_name: str, source: RemoteFrameSource) -> list[str]:
    index, _ = load_remote_index(source_name, source)
    frames: list[str] = []
    for category, models in index.items():
        if not isinstance(models, dict):
            continue
        for model, variants in models.items():
            if not isinstance(variants, dict):
                continue
            frames.extend(f"{category}/{model}/{variant}" for variant in variants)
    return sorted(frames)


def resolve_frame(
    config: AasgConfig,
    config_path: Path,
    source_name: str,
    frame_id: str,
) -> FrameAsset:
    source = config.frame_sources.get(source_name)
    if source is None:
        raise ConfigurationError(f"Unknown frame source: {source_name}")
    if isinstance(source, LocalFrameSource):
        root = project_path(config_path, source.root)
        frame_root = root.joinpath(*frame_id.split("/"))
        return _load_local(frame_id, frame_root, source.license)
    return _load_remote(source_name, source, frame_id)


def frame_cache_available(
    config: AasgConfig, config_path: Path, source_name: str, frame_id: str
) -> tuple[bool, str]:
    source = config.frame_sources.get(source_name)
    if source is None:
        return False, f"unknown source {source_name!r}"
    if isinstance(source, LocalFrameSource):
        try:
            asset = _load_local(
                frame_id,
                project_path(config_path, source.root).joinpath(*frame_id.split("/")),
                source.license,
            )
        except AasgError as error:
            return False, str(error)
        return True, str(asset.frame_path.parent)
    parts = frame_id.split("/")
    if len(parts) != 3:
        return False, f"invalid frame ID {frame_id!r}"
    root = _source_cache(source_name)
    required = [
        root / "index.json",
        root / "index-manifest.json",
        root / "assets" / Path(*parts) / "frame.png",
        root / "assets" / Path(*parts) / "mask.png",
        root / "assets" / Path(*parts) / "manifest.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        return False, f"not cached: {frame_id}"
    return True, str(required[2].parent)


def _load_local(frame_id: str, root: Path, license_name: str) -> FrameAsset:
    metadata_path = root / "template.json"
    try:
        metadata = FrameMetadata.model_validate_json(metadata_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ConfigurationError(f"Invalid local frame metadata: {metadata_path}") from error
    frame = resolve_inside(root, metadata.frame)
    mask = resolve_inside(root, metadata.mask)
    if not frame.is_file() or not mask.is_file():
        raise ConfigurationError(f"Local frame is missing frame or mask under {root}")
    if metadata.sha256 is None:
        raise ConfigurationError(
            f"Local frame metadata must declare sha256 checksums: {metadata_path}"
        )
    actual_frame_sha = _sha256(frame)
    actual_mask_sha = _sha256(mask)
    if actual_frame_sha.lower() != metadata.sha256.frame.lower():
        raise ConfigurationError(f"Local frame failed SHA-256 verification: {frame}")
    if actual_mask_sha.lower() != metadata.sha256.mask.lower():
        raise ConfigurationError(f"Local mask failed SHA-256 verification: {mask}")
    return FrameAsset(
        frame_id,
        frame,
        mask,
        metadata,
        {
            "kind": "local",
            "license": license_name,
            "frame_sha256": actual_frame_sha,
            "mask_sha256": actual_mask_sha,
        },
    )


def _load_remote(
    source_name: str,
    source: RemoteFrameSource,
    frame_id: str,
) -> FrameAsset:
    parts = frame_id.split("/")
    if len(parts) != 3:
        raise ConfigurationError("Remote frame IDs use category/model/variant")
    index, index_manifest = load_remote_index(source_name, source)
    try:
        entry = index[parts[0]][parts[1]][parts[2]]
        metadata = FrameMetadata.model_validate(
            {
                "frame": "frame.png",
                "mask": "mask.png",
                "screen": entry["screen"],
                "frameSize": entry["frameSize"],
                "hexColor": entry.get("hexColor"),
            }
        )
        frame_url = str(entry["frame"])
        mask_url = str(entry["mask"])
    except (KeyError, TypeError, ValueError) as error:
        raise ConfigurationError(f"Unknown or invalid remote frame: {frame_id}") from error

    frame_root = _source_cache(source_name) / "assets" / Path(*parts)
    frame_path = frame_root / "frame.png"
    mask_path = frame_root / "mask.png"
    asset_manifest_path = frame_root / "manifest.json"
    if not frame_path.is_file() or not mask_path.is_file():
        frame_download = _download(frame_url, frame_path)
        mask_download = _download(mask_url, mask_path)
        asset_manifest = {
            "frame_id": frame_id,
            "retrieved_at": datetime.now(UTC).isoformat(),
            "frame_url": frame_url,
            "mask_url": mask_url,
            "frame": frame_download,
            "mask": mask_download,
            "license": None,
        }
        asset_manifest_path.write_text(
            json.dumps(asset_manifest, indent=2) + "\n", encoding="utf-8"
        )
    try:
        asset_manifest = json.loads(asset_manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PrerequisiteError(f"Invalid cache manifest for frame {frame_id}") from error
    if not isinstance(asset_manifest, dict):
        raise PrerequisiteError(f"Invalid cache manifest for frame {frame_id}")
    cached_frame = asset_manifest.get("frame")
    cached_mask = asset_manifest.get("mask")
    _verify_sha256(
        frame_path,
        cached_frame.get("sha256") if isinstance(cached_frame, dict) else None,
        f"frame {frame_id}",
    )
    _verify_sha256(
        mask_path,
        cached_mask.get("sha256") if isinstance(cached_mask, dict) else None,
        f"mask {frame_id}",
    )
    return FrameAsset(
        frame_id,
        frame_path,
        mask_path,
        metadata,
        {
            "kind": "device-frames-media",
            "license": None,
            "index": index_manifest,
            "asset": asset_manifest,
            "host": urlparse(source.index_url).hostname,
        },
    )


def refresh_source(name: str, source: RemoteFrameSource) -> None:
    load_remote_index(name, source, refresh=True)
    # The new index can point at revised artwork or geometry. Invalidate selected
    # assets only after the replacement index has been downloaded successfully.
    shutil.rmtree(_source_cache(name) / "assets", ignore_errors=True)
