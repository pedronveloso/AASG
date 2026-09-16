from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
import yaml
from conftest import write_config

from aasg.android import CommandResult, Device, ShowTapsState
from aasg.capture import (
    CaptureRunner,
    Selection,
    expand_capture_ids,
    expand_navigation_modes,
    expand_variant_ids,
    has_selectable_navigation,
)
from aasg.config import load_config
from aasg.errors import CaptureError, ExitCode, PrerequisiteError


def test_expands_groups_and_all_variants(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path))

    assert expand_capture_ids(config, ["screenshots"], False) == ["home"]
    assert expand_variant_ids(["all"], config.variants.locales, name="locales") == ["en", "es"]
    assert expand_navigation_modes(["all"]) == ["gestural", "three-button"]


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
    assert outcome.manifest["schema"] == 5
    assert outcome.manifest["navigation"]["status"] == "ignored"
    assert outcome.manifest["show_taps"]["status"] == "ignored"
    assert outcome.manifest["variants"][0]["status"] == "succeeded"
    assert outcome.manifest["assets"] == ["artifacts/screenshots/raw/en/home-light.png"]
    assert (outcome.run_root / "run.json").is_file()


def test_dry_run_plans_capture_defaults(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["captures"]["home"]["defaults"] = [
        {
            "type": "role",
            "role": "android.app.role.BROWSER",
            "holders": ["com.example.app"],
        },
        {"type": "setting", "namespace": "global", "key": "font_scale", "value": "1.0"},
    ]
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    config = load_config(path)

    outcome = CaptureRunner().run(
        config=config,
        config_path=path,
        device=Device("dry-run", "device"),
        selection=Selection(["home"], ["en"], ["light"]),
        dry_run=True,
    )

    assert outcome.manifest["defaults"]["status"] == "planned"
    assert [event["status"] for event in outcome.manifest["variants"][0]["default_events"]] == [
        "planned",
        "planned",
    ]


def test_default_initialization_warning_does_not_block_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["captures"]["home"]["defaults"] = [
        {"type": "setting", "namespace": "global", "key": "font_scale", "value": "1.0"}
    ]
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    config = load_config(path)
    runner = CaptureRunner()
    monkeypatch.setattr(
        "aasg.capture.active_user",
        lambda *args: (_ for _ in ()).throw(PrerequisiteError("no user")),
    )
    monkeypatch.setattr(
        "aasg.capture.run_supervised", lambda *args, **kwargs: CommandResult(0, 0.1)
    )
    monkeypatch.setattr(runner, "_collect_variant", lambda *args, **kwargs: ([], []))

    outcome = runner.run(
        config=config,
        config_path=path,
        device=Device("ABC", "device"),
        selection=Selection(["home"], ["en"], ["light"]),
    )

    assert outcome.exit_code == 0
    assert outcome.manifest["defaults"]["status"] == "warning"
    assert outcome.manifest["variants"][0]["status"] == "succeeded"


def test_collected_artifact_records_semantic_metadata_checksum(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    artifact = data["captures"]["home"]["artifacts"][0]
    artifact["metadata"] = "screenshots/{locale}/home-{theme}.metadata.json"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    config = load_config(path)
    additional_output = tmp_path / config.android.additional_output_dir
    source = additional_output / "worker" / "screenshots" / "en" / "home-light.png"
    metadata = source.with_name("home-light.metadata.json")
    source.parent.mkdir(parents=True)
    source.write_bytes(b"image")
    metadata.write_text('{"schema": 1, "media": "home-light.png", "regions": {}}')
    runner = CaptureRunner()
    monkeypatch.setattr(runner, "_validate", lambda *args: None)

    records, _ = runner._collect_variant(
        config,
        path,
        tmp_path / "artifacts",
        additional_output,
        tmp_path / "run",
        "home",
        config.captures["home"],
        "en",
        "light",
        "ignore",
        {},
        False,
    )

    assert records[0]["metadata"] == {
        "source": "screenshots/en/home-light.metadata.json",
        "sha256": hashlib.sha256(metadata.read_bytes()).hexdigest(),
    }


def configured_video_path(tmp_path: Path, *, show_taps: bool = True) -> Path:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    capture = data["captures"]["home"]
    capture["show_taps"] = show_taps
    capture["artifacts"][0]["type"] = "video"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def test_video_dry_run_plans_default_show_taps(tmp_path: Path) -> None:
    path = configured_video_path(tmp_path)
    config = load_config(path)

    outcome = CaptureRunner().run(
        config=config,
        config_path=path,
        device=Device("dry-run", "device"),
        selection=Selection(["home"], ["en"], ["light"]),
        dry_run=True,
    )

    assert outcome.manifest["show_taps"] == {
        "status": "planned",
        "required": [True],
        "events": [],
        "restoration": {"status": "planned"},
    }
    variant = outcome.manifest["variants"][0]
    assert variant["show_taps"] is True
    assert variant["effective_show_taps"] is True


def test_dry_run_expands_mixed_navigation_policies(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    home = data["captures"]["home"]
    home["navigation"] = "all"
    home["artifacts"][0]["publish"] = "screenshots/raw/{locale}/home-{theme}-{navigation}.png"
    fixed = copy.deepcopy(home)
    fixed["label"] = "Fixed"
    fixed["navigation"] = "three-button"
    fixed["artifacts"][0]["publish"] = "screenshots/raw/{locale}/fixed-{theme}.png"
    ignored = copy.deepcopy(home)
    ignored["label"] = "Ignored"
    ignored["navigation"] = "ignore"
    ignored["artifacts"][0]["publish"] = "screenshots/raw/{locale}/ignored-{theme}.png"
    data["captures"] = {"home": home, "fixed": fixed, "ignored": ignored}
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    (tmp_path / "gradlew").touch()
    config = load_config(path)
    selection = Selection(
        ["home", "fixed", "ignored"],
        ["en"],
        ["light"],
        ["gestural", "three-button"],
    )

    outcome = CaptureRunner().run(
        config=config,
        config_path=path,
        device=Device("dry-run", "device"),
        selection=selection,
        dry_run=True,
    )

    assert has_selectable_navigation(config, selection.captures)
    assert [variant["navigation"] for variant in outcome.manifest["variants"]] == [
        "gestural",
        "three-button",
        "three-button",
        "ignore",
    ]
    assert outcome.manifest["selection"]["navigation"] == ["gestural", "three-button"]
    assert outcome.manifest["navigation"]["status"] == "planned"
    assert outcome.manifest["assets"][:2] == [
        "artifacts/screenshots/raw/en/home-light-gestural.png",
        "artifacts/screenshots/raw/en/home-light-three-button.png",
    ]


def test_preparation_failure_is_persisted(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["android"]["prepare_tasks"] = [":app:assembleDebug"]
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    config = load_config(path)
    serial = "device-serial-9876"

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise CaptureError(f"Gradle command failed for adb -s {serial} token=secret-value")

    monkeypatch.setattr("aasg.capture.run_supervised", fail)

    outcome = CaptureRunner().run(
        config=config,
        config_path=path,
        device=Device(serial, "device"),
        selection=Selection(["home"], ["en"], ["light"]),
    )

    assert outcome.failed == 1
    assert outcome.exit_code == int(ExitCode.CAPTURE_FAILED)
    assert outcome.manifest["prepare_error"]
    assert (outcome.run_root / "run.json").is_file()
    serialized = (outcome.run_root / "run.json").read_text()
    assert serial not in serialized
    assert "…9876" in outcome.manifest["prepare_error"]
    assert "token=<redacted>" in outcome.manifest["prepare_error"]


class FakeNavigationController:
    available = ("gestural", "three-button")
    original_mode = "three-button"
    current_mode = "three-button"

    def __init__(self, *, restore_error: str | None = None) -> None:
        self.events: list[dict[str, object]] = []
        self.restore_error = restore_error
        self.restored = False

    def require_modes(self, modes: set[str]) -> None:
        assert modes

    def ensure(self, mode: str) -> dict[str, object]:
        self.current_mode = mode
        event: dict[str, object] = {"action": "switch", "mode": mode, "status": "succeeded"}
        self.events.append(event)
        return event

    def restore(self) -> dict[str, object]:
        self.restored = True
        if self.restore_error is not None:
            raise PrerequisiteError(self.restore_error)
        event: dict[str, object] = {
            "action": "restore",
            "mode": "three-button",
            "status": "succeeded",
        }
        self.events.append(event)
        return event

    def manual_restore_guidance(self) -> str:
        return "adb -s '<device-serial>' shell restore"


class FakeShowTapsController:
    user = 0

    def __init__(self, *, restore_error: str | None = None) -> None:
        self.original_state = ShowTapsState(False, None)
        self.current_state = self.original_state
        self.events: list[dict[str, object]] = []
        self.restore_error = restore_error
        self.restore_count = 0

    def ensure(self, value: bool) -> dict[str, object]:
        self.current_state = ShowTapsState(True, value)
        event: dict[str, object] = {
            "action": "set",
            "value": value,
            "status": "succeeded",
        }
        self.events.append(event)
        return event

    def restore(self) -> dict[str, object]:
        self.restore_count += 1
        if self.restore_error is not None:
            raise PrerequisiteError(self.restore_error)
        self.current_state = self.original_state
        event: dict[str, object] = {
            "action": "restore",
            "value": None,
            "status": "succeeded",
        }
        self.events.append(event)
        return event

    def manual_restore_guidance(self) -> str:
        return "adb -s '<device-serial>' shell settings delete system show_touches"


def test_navigation_initialization_error_is_redacted_from_manifest(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    path = configured_navigation_path(tmp_path)
    config = load_config(path)
    serial = "device-serial-9876"

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise PrerequisiteError(f"Command failed: adb -s {serial} token=secret-value")

    monkeypatch.setattr("aasg.capture.active_user", fail)

    outcome = CaptureRunner().run(
        config=config,
        config_path=path,
        device=Device(serial, "device"),
        selection=Selection(["home"], ["en"], ["light"]),
    )

    serialized = (outcome.run_root / "run.json").read_text()
    assert outcome.manifest["navigation"]["status"] == "failed"
    assert serial not in serialized
    assert "…9876" in outcome.manifest["navigation"]["error"]
    assert "token=<redacted>" in outcome.manifest["navigation"]["error"]


def test_show_taps_initialization_error_is_redacted_from_manifest(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    path = configured_video_path(tmp_path)
    config = load_config(path)
    serial = "device-serial-9876"

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise PrerequisiteError(f"Command failed: adb -s {serial} token=secret-value")

    monkeypatch.setattr("aasg.capture.active_user", fail)

    outcome = CaptureRunner().run(
        config=config,
        config_path=path,
        device=Device(serial, "device"),
        selection=Selection(["home"], ["en"], ["light"]),
    )

    serialized = (outcome.run_root / "run.json").read_text()
    assert outcome.manifest["show_taps"]["status"] == "failed"
    assert serial not in serialized
    assert "…9876" in outcome.manifest["show_taps"]["error"]
    assert "token=<redacted>" in outcome.manifest["show_taps"]["error"]


def test_variant_and_restoration_errors_are_redacted_from_manifest(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    path = configured_navigation_path(tmp_path)
    config = load_config(path)
    serial = "device-serial-9876"
    controller = FakeNavigationController(
        restore_error=f"Restore failed: adb -s {serial} token=secret-value"
    )
    monkeypatch.setattr("aasg.capture.active_user", lambda *args: 0)
    monkeypatch.setattr("aasg.capture.NavigationController.inspect", lambda **kwargs: controller)

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise CaptureError(f"Capture failed: adb -s {serial} token=secret-value")

    monkeypatch.setattr("aasg.capture.run_supervised", fail)

    outcome = CaptureRunner().run(
        config=config,
        config_path=path,
        device=Device(serial, "device"),
        selection=Selection(["home"], ["en"], ["light"]),
    )

    serialized = (outcome.run_root / "run.json").read_text()
    assert outcome.manifest["variants"][0]["status"] == "failed"
    assert outcome.manifest["navigation"]["restoration"]["status"] == "failed"
    assert serial not in serialized
    assert "…9876" in outcome.manifest["variants"][0]["error"]
    assert "token=<redacted>" in outcome.manifest["navigation"]["restoration"]["error"]


@pytest.mark.parametrize("configured", [True, False])
def test_video_capture_applies_and_restores_show_taps_before_collection(
    tmp_path: Path, monkeypatch, configured: bool
) -> None:  # type: ignore[no-untyped-def]
    path = configured_video_path(tmp_path, show_taps=configured)
    config = load_config(path)
    controller = FakeShowTapsController()
    monkeypatch.setattr("aasg.capture.active_user", lambda *args: 0)
    monkeypatch.setattr("aasg.capture.ShowTapsController.inspect", lambda **kwargs: controller)
    monkeypatch.setattr(
        "aasg.capture.run_supervised", lambda *args, **kwargs: CommandResult(0, 0.25)
    )
    runner = CaptureRunner()

    def collect(*args, **kwargs):  # type: ignore[no-untyped-def]
        assert controller.current_state == controller.original_state
        return [], []

    monkeypatch.setattr(runner, "_collect_variant", collect)

    outcome = runner.run(
        config=config,
        config_path=path,
        device=Device("ABC", "device"),
        selection=Selection(["home"], ["en"], ["light"]),
    )

    variant = outcome.manifest["variants"][0]
    assert outcome.exit_code == 0
    assert variant["show_taps"] is configured
    assert variant["effective_show_taps"] is configured
    assert variant["show_taps_restoration"]["status"] == "succeeded"
    assert outcome.manifest["show_taps"]["original"] == {"present": False, "value": None}
    assert controller.restore_count == 2


def test_show_taps_restoration_failure_prevents_video_publication(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    path = configured_video_path(tmp_path)
    config = load_config(path)
    controller = FakeShowTapsController(restore_error="show taps restore failed")
    monkeypatch.setattr("aasg.capture.active_user", lambda *args: 0)
    monkeypatch.setattr("aasg.capture.ShowTapsController.inspect", lambda **kwargs: controller)
    monkeypatch.setattr(
        "aasg.capture.run_supervised", lambda *args, **kwargs: CommandResult(0, 0.25)
    )
    runner = CaptureRunner()
    collected = False

    def collect(*args, **kwargs):  # type: ignore[no-untyped-def]
        nonlocal collected
        collected = True
        return [], []

    monkeypatch.setattr(runner, "_collect_variant", collect)

    outcome = runner.run(
        config=config,
        config_path=path,
        device=Device("ABC", "device"),
        selection=Selection(["home"], ["en"], ["light"]),
    )

    assert not collected
    assert outcome.failed == 1
    assert outcome.exit_code == int(ExitCode.UNAVAILABLE)
    assert outcome.manifest["show_taps"]["restoration"]["status"] == "failed"
    assert "<device-serial>" in outcome.manifest["show_taps"]["restoration"]["manual_command"]


def test_interruption_restores_show_taps_and_persists_manifest(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    path = configured_video_path(tmp_path)
    config = load_config(path)
    controller = FakeShowTapsController()
    monkeypatch.setattr("aasg.capture.active_user", lambda *args: 0)
    monkeypatch.setattr("aasg.capture.ShowTapsController.inspect", lambda **kwargs: controller)

    def interrupt(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise KeyboardInterrupt

    monkeypatch.setattr("aasg.capture.run_supervised", interrupt)

    with pytest.raises(KeyboardInterrupt):
        CaptureRunner().run(
            config=config,
            config_path=path,
            device=Device("ABC", "device"),
            selection=Selection(["home"], ["en"], ["light"]),
        )

    manifests = list((tmp_path / "artifacts" / "aasg" / "runs").glob("*/run.json"))
    manifest = json.loads(manifests[0].read_text())
    assert controller.restore_count == 2
    assert manifest["result"]["exit_code"] == int(ExitCode.INTERRUPTED)
    assert manifest["show_taps"]["restoration"]["status"] == "succeeded"


def configured_navigation_path(tmp_path: Path) -> Path:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["captures"]["home"]["navigation"] = "gestural"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    return path


def test_restoration_failure_sets_prerequisite_exit_code(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    path = configured_navigation_path(tmp_path)
    config = load_config(path)
    controller = FakeNavigationController(restore_error="restore failed")
    monkeypatch.setattr("aasg.capture.active_user", lambda *args: 0)
    monkeypatch.setattr("aasg.capture.NavigationController.inspect", lambda **kwargs: controller)
    runner = CaptureRunner()
    monkeypatch.setattr(
        runner,
        "_run_variant",
        lambda **kwargs: {"status": "succeeded", "artifacts": []},
    )

    outcome = runner.run(
        config=config,
        config_path=path,
        device=Device("ABC", "device"),
        selection=Selection(["home"], ["en"], ["light"]),
    )

    assert controller.restored
    assert outcome.exit_code == int(ExitCode.UNAVAILABLE)
    assert outcome.manifest["navigation"]["restoration"]["status"] == "failed"
    assert "<device-serial>" in outcome.manifest["navigation"]["restoration"]["manual_command"]


def test_capture_failure_remains_authoritative_and_restores_navigation(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    path = configured_navigation_path(tmp_path)
    config = load_config(path)
    controller = FakeNavigationController(restore_error="restore failed")
    monkeypatch.setattr("aasg.capture.active_user", lambda *args: 0)
    monkeypatch.setattr("aasg.capture.NavigationController.inspect", lambda **kwargs: controller)
    runner = CaptureRunner()
    monkeypatch.setattr(
        runner,
        "_run_variant",
        lambda **kwargs: {
            "status": "failed",
            "artifacts": [],
            "exit_code": int(ExitCode.CAPTURE_FAILED),
        },
    )

    outcome = runner.run(
        config=config,
        config_path=path,
        device=Device("ABC", "device"),
        selection=Selection(["home"], ["en"], ["light"]),
    )

    assert controller.restored
    assert outcome.exit_code == int(ExitCode.CAPTURE_FAILED)
    assert outcome.manifest["navigation"]["restoration"]["status"] == "failed"


def test_interruption_restores_navigation_and_persists_manifest(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    path = configured_navigation_path(tmp_path)
    config = load_config(path)
    controller = FakeNavigationController()
    monkeypatch.setattr("aasg.capture.active_user", lambda *args: 0)
    monkeypatch.setattr("aasg.capture.NavigationController.inspect", lambda **kwargs: controller)
    runner = CaptureRunner()

    def interrupt(**kwargs):  # type: ignore[no-untyped-def]
        raise KeyboardInterrupt

    monkeypatch.setattr(runner, "_run_variant", interrupt)

    with pytest.raises(KeyboardInterrupt):
        runner.run(
            config=config,
            config_path=path,
            device=Device("ABC", "device"),
            selection=Selection(["home"], ["en"], ["light"]),
        )

    manifests = list((tmp_path / "artifacts" / "aasg" / "runs").glob("*/run.json"))
    manifest = json.loads(manifests[0].read_text())
    assert controller.restored
    assert manifest["result"]["exit_code"] == int(ExitCode.INTERRUPTED)
    assert manifest["navigation"]["restoration"]["status"] == "succeeded"
