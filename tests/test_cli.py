from __future__ import annotations

import json
import tomllib
from pathlib import Path

from conftest import write_config
from typer.testing import CliRunner

from aasg import __version__
from aasg.cli import app

runner = CliRunner()


def test_version_option() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_package_versions_are_synchronized() -> None:
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]

    assert project["version"] == __version__


def test_config_validate(tmp_path: Path) -> None:
    path = write_config(tmp_path)

    result = runner.invoke(app, ["config", "validate", "--config", str(path)])

    assert result.exit_code == 0
    assert "Valid schema 2" in result.output


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
    assert "Use the previous capture selection? [Y/n]:" in result.output
