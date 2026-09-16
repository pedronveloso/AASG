from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from conftest import write_config

from aasg.config import load_config, render_template, resolve_inside
from aasg.errors import ConfigurationError


def test_loads_strict_config(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path))

    assert config.schema_version == 6
    assert config.captures["home"].test == "example.HomeCaptureTest"
    assert config.captures["home"].navigation == "ignore"
    assert config.captures["home"].show_taps is True


def test_accepts_disabled_show_taps_for_video_capture(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    capture = data["captures"]["home"]
    capture["show_taps"] = False
    capture["artifacts"][0]["type"] = "video"
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    assert load_config(path).captures["home"].show_taps is False


def test_rejects_capture_with_video_and_image_artifacts(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    capture = data["captures"]["home"]
    video = capture["artifacts"][0].copy()
    video.update({"id": "walkthrough", "type": "video"})
    capture["artifacts"].append(video)
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(ConfigurationError, match=r"video artifacts.*not image artifacts"):
        load_config(path)


def test_accepts_capture_with_video_and_json_artifacts(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    capture = data["captures"]["home"]
    capture["artifacts"][0]["type"] = "video"
    metadata = capture["artifacts"][0].copy()
    metadata.update({"id": "timeline", "type": "json"})
    capture["artifacts"].append(metadata)
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    assert [artifact.type for artifact in load_config(path).captures["home"].artifacts] == [
        "video",
        "json",
    ]


def test_accepts_video_gesture_overlay_with_metadata_and_native_taps_disabled(
    tmp_path: Path,
) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    capture = data["captures"]["home"]
    capture["show_taps"] = False
    artifact = capture["artifacts"][0]
    artifact["type"] = "video"
    artifact["metadata"] = "recordings/home.metadata.json"
    artifact["renditions"] = [{"publish": "recordings/home-promo.mp4", "pipeline": "promo"}]
    data["pipelines"] = {"promo": {"steps": [{"type": "gesture_overlay"}]}}
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    step = load_config(path).pipelines["promo"].steps[0]

    assert step.model_dump() == {
        "type": "gesture_overlay",
        "color": "#FFFFFF",
        "halo_color": "#000000A0",
        "radius_px": 44,
        "trail": True,
        "timing_offset_ms": 0,
        "motion": "standard",
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("show_taps", "requires show_taps: false"),
        ("metadata", "requires artifact metadata"),
        ("image", "supports video artifacts only"),
        ("order", "must be the first pipeline step"),
        ("duplicate", "only one gesture_overlay"),
    ],
)
def test_rejects_invalid_gesture_overlay_configuration(
    tmp_path: Path, mutation: str, message: str
) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    capture = data["captures"]["home"]
    capture["show_taps"] = mutation == "show_taps"
    artifact = capture["artifacts"][0]
    artifact["type"] = "image" if mutation == "image" else "video"
    if mutation != "metadata":
        artifact["metadata"] = "recordings/home.metadata.json"
    artifact["renditions"] = [{"publish": "recordings/home-promo.mp4", "pipeline": "promo"}]
    steps: list[dict[str, object]] = [{"type": "gesture_overlay"}]
    if mutation == "order":
        steps.insert(0, {"type": "resize", "width": 100, "height": 200})
    if mutation == "duplicate":
        steps.append({"type": "gesture_overlay"})
    data["pipelines"] = {"promo": {"steps": steps}}
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(ConfigurationError, match=message):
        load_config(path)


@pytest.mark.parametrize("policy", ["gestural", "three-button", "all", "ignore"])
def test_accepts_navigation_policies(tmp_path: Path, policy: str) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    capture = data["captures"]["home"]
    capture["navigation"] = policy
    if policy == "all":
        capture["artifacts"][0]["publish"] = (
            "screenshots/raw/{locale}/home-{theme}-{navigation}.png"
        )
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    assert load_config(path).captures["home"].navigation == policy


def test_rejects_invalid_navigation_policy(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["captures"]["home"]["navigation"] = "two-button"
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(ConfigurationError, match="navigation"):
        load_config(path)


def test_all_navigation_requires_distinct_publication_paths(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["captures"]["home"]["navigation"] = "all"
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(ConfigurationError, match=r"must contain \{navigation\}"):
        load_config(path)


@pytest.mark.parametrize("field", ["publish", "rendition"])
def test_all_navigation_rejects_escaped_navigation_literal(tmp_path: Path, field: str) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    capture = data["captures"]["home"]
    capture["navigation"] = "all"
    artifact = capture["artifacts"][0]
    artifact["publish"] = "screenshots/raw/{locale}/home-{theme}-{navigation}.png"
    if field == "publish":
        artifact["publish"] = "screenshots/raw/{locale}/home-{{navigation}}.png"
    else:
        data["pipelines"] = {"copy": {"steps": []}}
        artifact["renditions"] = [
            {
                "publish": "screenshots/framed/{locale}/home-{{navigation}}.png",
                "pipeline": "copy",
            }
        ]
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(ConfigurationError, match=r"must contain \{navigation\}"):
        load_config(path)


def test_all_navigation_accepts_literal_braces_with_navigation_field(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["captures"]["home"]["navigation"] = "all"
    template = "screenshots/raw/{locale}/home-{{literal}}-{navigation}.png"
    data["captures"]["home"]["artifacts"][0]["publish"] = template
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    load_config(path)

    assert render_template(template, locale="en", navigation="gestural") == (
        "screenshots/raw/en/home-{literal}-gestural.png"
    )
    assert render_template(template, locale="en", navigation="three-button") == (
        "screenshots/raw/en/home-{literal}-three-button.png"
    )


@pytest.mark.parametrize("schema", [1, 2, 3, 4, 5, 7])
def test_rejects_unsupported_config_schema_with_migration_guidance(
    tmp_path: Path, schema: int
) -> None:
    path = write_config(tmp_path, {"schema": schema})

    with pytest.raises(
        ConfigurationError,
        match=rf"Unsupported configuration schema {schema}.*requires schema 6.*migrate",
    ):
        load_config(path)


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
    assert (
        render_template("{capture}-{navigation}", capture="home", navigation="gestural")
        == "home-gestural"
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
