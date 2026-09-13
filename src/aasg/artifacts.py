"""Fresh AndroidX output discovery and atomic publication."""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

from aasg.errors import ProcessingError

Fingerprint = dict[str, tuple[int, int]]


def fingerprint_tree(root: Path) -> Fingerprint:
    if not root.is_dir():
        return {}
    result: Fingerprint = {}
    for path in root.rglob("*"):
        if path.is_file():
            stat = path.stat()
            result[path.relative_to(root).as_posix()] = (stat.st_size, stat.st_mtime_ns)
    return result


def find_fresh_output(root: Path, relative_suffix: str, before: Fingerprint) -> Path:
    normalized = relative_suffix.lstrip("/")
    matches: list[Path] = []
    for path in root.rglob("*") if root.is_dir() else []:
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative != normalized and not relative.endswith(f"/{normalized}"):
            continue
        stat = path.stat()
        current = (stat.st_size, stat.st_mtime_ns)
        if before.get(relative) != current:
            matches.append(path)
    if not matches:
        raise ProcessingError(
            f"Expected fresh Test Storage output was not found: {relative_suffix}"
        )
    if len(matches) > 1:
        names = ", ".join(str(path) for path in matches)
        raise ProcessingError(f"Ambiguous Test Storage output {relative_suffix!r}: {names}")
    return matches[0]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stage_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def publish_atomically(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.aasg.tmp")
    shutil.copy2(source, temporary)
    temporary.replace(destination)
