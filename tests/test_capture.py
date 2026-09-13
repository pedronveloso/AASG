from __future__ import annotations

from pathlib import Path

import yaml
from conftest import write_config

from aasg.android import CommandResult, Device
from aasg.capture import CaptureRunner, Selection, expand_capture_ids, expand_variant_ids
from aasg.config import load_config
from aasg.errors import ExitCode


def test_expands_groups_and_all_variants(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path))

    assert expand_capture_ids(config, ["screenshots"], False) == ["home"]
    assert expand_variant_ids(["all"], config.variants.locales, name="locales") == ["en", "es"]


def test_dry_run_writes_resolved_manifest(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    (tmp_path / "gradlew").touch()
    config = load_config(path)

    outcome = CaptureRunner().run(
        config=config,
        config_path=path,
        device=Device("dry-run", "device"),
        selection=Selection(["home"], ["en"], ["light"]),
        dry_run=True,
    )

    assert outcome.failed == 0
    assert outcome.manifest["variants"][0]["status"] == "succeeded"
    assert outcome.manifest["assets"] == ["artifacts/screenshots/raw/en/home-light.png"]
    assert (outcome.run_root / "run.json").is_file()


def test_preparation_failure_is_persisted(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["android"]["prepare_tasks"] = [":app:assembleDebug"]
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    config = load_config(path)
    monkeypatch.setattr(
        "aasg.capture.run_supervised", lambda *args, **kwargs: CommandResult(1, 0.25)
    )

    outcome = CaptureRunner().run(
        config=config,
        config_path=path,
        device=Device("emulator-5554", "device"),
        selection=Selection(["home"], ["en"], ["light"]),
    )

    assert outcome.failed == 1
    assert outcome.exit_code == int(ExitCode.CAPTURE_FAILED)
    assert outcome.manifest["prepare_error"]
    assert (outcome.run_root / "run.json").is_file()
