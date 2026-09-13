from __future__ import annotations

from pathlib import Path

import pytest

from aasg.artifacts import find_fresh_output, fingerprint_tree, publish_atomically
from aasg.errors import ProcessingError


def test_finds_only_changed_exact_suffix(tmp_path: Path) -> None:
    output = tmp_path / "device" / "screenshots" / "en" / "home.png"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"old")
    before = fingerprint_tree(tmp_path)
    output.write_bytes(b"newer")

    assert find_fresh_output(tmp_path, "screenshots/en/home.png", before) == output


def test_rejects_stale_output(tmp_path: Path) -> None:
    output = tmp_path / "screenshots" / "home.png"
    output.parent.mkdir(parents=True)
    output.write_bytes(b"old")
    before = fingerprint_tree(tmp_path)

    with pytest.raises(ProcessingError, match="fresh"):
        find_fresh_output(tmp_path, "screenshots/home.png", before)


def test_atomic_publish_replaces_destination(tmp_path: Path) -> None:
    source = tmp_path / "new"
    destination = tmp_path / "published" / "result"
    source.write_text("new")
    destination.parent.mkdir()
    destination.write_text("old")

    publish_atomically(source, destination)

    assert destination.read_text() == "new"
