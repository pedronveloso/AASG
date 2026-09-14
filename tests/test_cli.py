from __future__ import annotations

import json
import tomllib
from pathlib import Path

import yaml
from conftest import write_config
from typer.testing import CliRunner

from aasg import __version__
from aasg.android import Device, NavigationState
from aasg.cli import app

runner = CliRunner()


def configure_navigation(path: Path, policy: str) -> None:
    data = yaml.safe_load(path.read_text())
    capture = data["captures"]["home"]
    capture["navigation"] = policy
    if policy == "all":
        capture["artifacts"][0]["publish"] = (
            "screenshots/raw/{locale}/home-{theme}-{navigation}.png"
        )
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def test_version_option() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_package_versions_are_synchronized() -> None:
    root = Path(__file__).parents[1]
    pyproject = root / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    lock = tomllib.loads((root / "uv.lock").read_text(encoding="utf-8"))
    packages = [
        package
        for package in lock["package"]
        if package["name"] == "android-auto-screengrabs"
        and package.get("source") == {"editable": "."}
    ]

    assert len(packages) == 1
    assert project["version"] == packages[0]["version"] == __version__


def test_config_validate(tmp_path: Path) -> None:
    path = write_config(tmp_path)

    result = runner.invoke(app, ["config", "validate", "--config", str(path)])

    assert result.exit_code == 0
    assert "Valid schema 4" in result.output


def test_init_refuses_to_overwrite_with_usage_exit(tmp_path: Path) -> None:
    path = tmp_path / "aasg.yaml"

    assert runner.invoke(app, ["init", str(path)]).exit_code == 0
    result = runner.invoke(app, ["init", str(path)])

    assert result.exit_code == 2
    assert "Refusing to overwrite" in result.output


def test_capture_prints_relative_planned_asset_paths(tmp_path: Path) -> None:
    path = write_config(tmp_path)

    result = runner.invoke(
        app,
        [
            "capture",
            "home",
            "--config",
            str(path),
            "--device",
            "dry-run",
            "--locale",
            "en",
            "--theme",
            "light",
            "--non-interactive",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Planned assets:" in result.output
    assert "artifacts/screenshots/raw/en/home-light.png" in result.output


def test_show_taps_is_not_an_interactive_capture_choice(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["captures"]["home"]["artifacts"][0]["type"] = "video"
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    result = runner.invoke(
        app,
        [
            "capture",
            "home",
            "--config",
            str(path),
            "--locale",
            "en",
            "--theme",
            "light",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert "Show taps" not in result.output


def test_capture_json_includes_relative_asset_paths(tmp_path: Path) -> None:
    path = write_config(tmp_path)

    result = runner.invoke(
        app,
        [
            "capture",
            "home",
            "--config",
            str(path),
            "--device",
            "dry-run",
            "--locale",
            "en",
            "--theme",
            "light",
            "--non-interactive",
            "--dry-run",
            "--json",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.output)["assets"] == ["artifacts/screenshots/raw/en/home-light.png"]


def test_all_navigation_capture_prompts_once_and_allows_both_modes(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    configure_navigation(path, "all")

    result = runner.invoke(
        app,
        [
            "capture",
            "home",
            "--config",
            str(path),
            "--locale",
            "en",
            "--theme",
            "light",
            "--dry-run",
        ],
        input="all\n",
    )

    assert result.exit_code == 0
    assert result.output.count("Navigation") == 1
    assert "home-light-gestural.png" in result.output
    assert "home-light-three-button.png" in result.output


def test_non_interactive_all_navigation_defaults_to_both_modes(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    configure_navigation(path, "all")

    result = runner.invoke(
        app,
        [
            "capture",
            "home",
            "--config",
            str(path),
            "--locale",
            "en",
            "--theme",
            "light",
            "--non-interactive",
            "--dry-run",
            "--json",
        ],
    )

    assets = json.loads(result.output)["assets"]
    assert result.exit_code == 0
    assert assets == [
        "artifacts/screenshots/raw/en/home-light-gestural.png",
        "artifacts/screenshots/raw/en/home-light-three-button.png",
    ]


def test_fixed_navigation_does_not_prompt_and_rejects_navigation_flag(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    configure_navigation(path, "gestural")
    arguments = [
        "capture",
        "home",
        "--config",
        str(path),
        "--locale",
        "en",
        "--theme",
        "light",
        "--dry-run",
    ]

    result = runner.invoke(app, arguments)
    invalid = runner.invoke(app, [*arguments, "--navigation", "three-button"])

    assert result.exit_code == 0
    assert "Navigation\n" not in result.output
    assert invalid.exit_code == 2
    assert "only applies to captures configured with navigation: all" in invalid.output


def test_capture_rejects_unknown_navigation_mode(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    configure_navigation(path, "all")
    result = runner.invoke(
        app,
        [
            "capture",
            "home",
            "--config",
            str(path),
            "--locale",
            "en",
            "--theme",
            "light",
            "--navigation",
            "two-button",
            "--non-interactive",
            "--dry-run",
        ],
    )
    assert result.exit_code == 2
    assert "Unknown navigation mode: two-button" in result.output


def test_doctor_reports_system_navigation_capabilities(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    path = write_config(tmp_path)
    configure_navigation(path, "all")
    (tmp_path / "gradlew").touch()
    device = Device("ABC", "device", "Pixel 8", "pixel", 35)
    monkeypatch.setattr("aasg.cli.shutil.which", lambda executable: f"/bin/{executable}")
    monkeypatch.setattr("aasg.cli.discover_devices", lambda adb: [device])
    monkeypatch.setattr("aasg.cli.enrich_device", lambda adb, found: found)
    monkeypatch.setattr("aasg.cli.active_user", lambda adb, serial: 0)
    monkeypatch.setattr(
        "aasg.cli.navigation_state",
        lambda adb, serial, user: NavigationState(("gestural", "three-button"), ("three-button",)),
    )

    result = runner.invoke(app, ["doctor", "--config", str(path)])

    assert result.exit_code == 0
    assert "System navigation" in result.output
    assert "active three-button" in result.output


def test_capture_previews_previous_selection_before_confirmation(
    tmp_path: Path, monkeypatch
) -> None:  # type: ignore[no-untyped-def]
    path = write_config(tmp_path)
    monkeypatch.setattr(
        "aasg.cli.load_selection",
        lambda _: {
            "device": "emulator-5554",
            "captures": ["home"],
            "locales": ["en"],
            "themes": ["light"],
            "navigation": ["gestural", "three-button"],
        },
    )

    result = runner.invoke(
        app,
        ["capture", "--config", str(path), "--dry-run"],
        input="y\n",
    )

    assert result.exit_code == 0
    assert "Previous selection:" in result.output
    assert "Device: …5554" in result.output
    assert "Captures: Home (home)" in result.output
    assert "Locales: English (en)" in result.output
    assert "Themes: Light (light)" in result.output
    assert "Navigation for 'all' captures: Gesture navigation (gestural), " in result.output
    assert "Use the previous capture selection? [Y/n]:" in result.output
