from __future__ import annotations

from pathlib import Path

import pytest
from conftest import write_config

from aasg.config import load_config, render_template, resolve_inside
from aasg.errors import ConfigurationError


def test_loads_strict_config(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path))

    assert config.schema_version == 1
    assert config.captures["home"].test == "example.HomeCaptureTest"


def test_rejects_unknown_fields(tmp_path: Path) -> None:
    path = write_config(tmp_path, {"unexpected": True})

    with pytest.raises(ConfigurationError, match="unexpected"):
        load_config(path)


def test_rejects_unknown_template_fields(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    text = path.read_text().replace("home-{theme}.png", "home-{device}.png")
    path.write_text(text)

    with pytest.raises(ConfigurationError, match="device"):
        load_config(path)


@pytest.mark.parametrize("unsafe", ["../home-{theme}.png", "/tmp/home-{theme}.png"])
def test_rejects_unsafe_template_paths(tmp_path: Path, unsafe: str) -> None:
    path = write_config(tmp_path)
    text = path.read_text().replace("screenshots/raw/{locale}/home-{theme}.png", unsafe)
    path.write_text(text)

    with pytest.raises(ConfigurationError, match="contained relative path"):
        load_config(path)


def test_resolve_inside_rejects_traversal(tmp_path: Path) -> None:
    with pytest.raises(ConfigurationError, match="escapes"):
        resolve_inside(tmp_path, "../outside")


def test_rejects_path_unsafe_identifiers(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    text = path.read_text().replace("  home:\n", "  ../home:\n", 1)
    path.write_text(text)

    with pytest.raises(ConfigurationError, match="path-safe"):
        load_config(path)


def test_render_template() -> None:
    assert (
        render_template("{capture}/{locale}-{theme}", capture="home", locale="en", theme="dark")
        == "home/en-dark"
    )


def test_rejects_unsafe_direct_instrumentation_device_path(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = path.read_text()
    data = data.replace(
        "  theme_argument: screenshotTheme\n",
        "  theme_argument: screenshotTheme\n"
        "  direct_instrumentation:\n"
        "    application_id: example.app\n"
        "    test_application_id: example.app.test\n"
        "    runner: example.Runner\n"
        "    app_apk: app.apk\n"
        "    test_apk: test.apk\n"
        "    device_output_dir: /../unsafe\n",
    )
    path.write_text(data)

    with pytest.raises(ConfigurationError, match="safe absolute device path"):
        load_config(path)
