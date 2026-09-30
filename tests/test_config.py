from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from conftest import write_config

from aasg.config import (
    load_config,
    metadata_path,
    publication_path,
    render_template,
    resolve_inside,
    source_path,
)
from aasg.errors import ConfigurationError


def test_loads_strict_config(tmp_path: Path) -> None:
    config = load_config(write_config(tmp_path))

    assert config.schema_version == 9
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
    metadata.update({"id": "timeline", "type": "json", "metadata": False})
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
    artifact["metadata"] = True
    artifact["renditions"] = [{"publish_dir": "recordings/{locale}", "pipeline": "promo"}]
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
        artifact["metadata"] = True
    artifact["renditions"] = [{"publish_dir": "recordings/{locale}", "pipeline": "promo"}]
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
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    assert load_config(path).captures["home"].navigation == policy


def test_rejects_invalid_navigation_policy(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["captures"]["home"]["navigation"] = "two-button"
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(ConfigurationError, match="navigation"):
        load_config(path)


def test_publication_directory_requires_locale(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["captures"]["home"]["artifacts"][0]["publish_dir"] = "screenshots/raw"
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(ConfigurationError, match=r"must contain \{locale\}"):
        load_config(path)


def test_rejects_publication_path_collisions(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["pipelines"] = {"copy": {"steps": []}}
    data["captures"]["home"]["artifacts"][0]["renditions"] = [
        {"publish_dir": "screenshots/raw/{locale}", "pipeline": "copy"}
    ]
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(ConfigurationError, match="Publication path collision"):
        load_config(path)


def test_rejects_case_only_inferred_source_path_collisions(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["captures"]["Home"] = data["captures"]["home"].copy()
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(ConfigurationError, match="Inferred source path collision"):
        load_config(path)


def test_rejects_unsupported_rendition_extension(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["pipelines"] = {"copy": {"steps": []}}
    data["captures"]["home"]["artifacts"][0]["renditions"] = [
        {"publish_dir": "screenshots/framed/{locale}", "pipeline": "copy", "extension": ".exe"}
    ]
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(ConfigurationError, match="Unsupported image rendition extension"):
        load_config(path)


def test_publication_name_uses_capture_and_variant_ids() -> None:
    assert (
        publication_path(
            "screenshots/raw/{locale}",
            capture_id="store-2",
            artifact_id="store-2",
            artifact_count=1,
            artifact_type="image",
            locale="en",
            theme="light",
            navigation="three-button",
        )
        == "screenshots/raw/en/store-2-light-three-button.png"
    )
    assert (
        publication_path(
            "screenshots/raw/{locale}",
            capture_id="home",
            artifact_id="overview",
            artifact_count=2,
            artifact_type="image",
            locale="en",
            theme="dark",
            navigation="ignore",
        )
        == "screenshots/raw/en/home-overview-dark.png"
    )
    assert (
        publication_path(
            "videos/framed/{locale}",
            capture_id="walkthrough",
            artifact_id="walkthrough",
            artifact_count=1,
            artifact_type="video",
            locale="es",
            theme="light",
            navigation="gestural",
            extension=".webm",
        )
        == "videos/framed/es/walkthrough-light-gestural.webm"
    )


@pytest.mark.parametrize(
    ("artifact_type", "artifact_count", "artifact_id", "expected"),
    [
        ("image", 1, "store-2", "aasg/screenshots/en/store-2-light.png"),
        ("video", 1, "store-2", "aasg/videos/en/store-2-light.mp4"),
        ("json", 1, "store-2", "aasg/json/en/store-2-light.json"),
        ("image", 2, "card", "aasg/screenshots/en/store-2-card-light.png"),
    ],
)
def test_inferred_source_paths(
    artifact_type: str, artifact_count: int, artifact_id: str, expected: str
) -> None:
    source = source_path(
        capture_id="store-2",
        artifact_id=artifact_id,
        artifact_count=artifact_count,
        artifact_type=artifact_type,
        locale="en",
        theme="light",
    )
    assert source == expected
    assert metadata_path(source) == str(Path(expected).with_suffix(".metadata.json"))


def test_schema_nine_rejects_explicit_source_and_metadata_paths(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    artifact = data["captures"]["home"]["artifacts"][0]
    artifact["source"] = "screenshots/{locale}/home-{theme}.png"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    with pytest.raises(ConfigurationError, match="source"):
        load_config(path)

    del artifact["source"]
    artifact["metadata"] = "screenshots/{locale}/home-{theme}.metadata.json"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    with pytest.raises(ConfigurationError, match="metadata"):
        load_config(path)

    artifact["metadata"] = "true"
    path.write_text(yaml.safe_dump(data, sort_keys=False))
    with pytest.raises(ConfigurationError, match="metadata"):
        load_config(path)


def test_rejects_inferred_source_collisions(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    artifact = data["captures"]["home"]["artifacts"][0]
    duplicate = {**artifact, "publish_dir": "screenshots/other/{locale}"}
    data["captures"]["home"]["artifacts"].append(duplicate)
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(ConfigurationError, match="Inferred source path collision"):
        load_config(path)


def test_accepts_literal_braces_in_directory_template() -> None:
    template = "screenshots/{locale}/{{literal}}"
    assert render_template(template, locale="en") == "screenshots/en/{literal}"


@pytest.mark.parametrize("schema", [1, 2, 3, 4, 5, 6, 7, 8])
def test_rejects_unsupported_config_schema_with_migration_guidance(
    tmp_path: Path, schema: int
) -> None:
    path = write_config(tmp_path, {"schema": schema})

    with pytest.raises(
        ConfigurationError,
        match=rf"Unsupported configuration schema {schema}.*requires schema 9.*migrate",
    ):
        load_config(path)


def test_validates_capture_defaults(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["captures"]["home"]["defaults"] = [
        {
            "type": "permission",
            "package": "com.example.app",
            "permission": "android.permission.POST_NOTIFICATIONS",
            "state": "granted",
        },
        {
            "type": "role",
            "role": "android.app.role.BROWSER",
            "holders": ["com.example.app"],
        },
        {"type": "setting", "namespace": "global", "key": "font_scale", "value": "1.0"},
    ]
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    assert [default.type for default in load_config(path).captures["home"].defaults] == [
        "permission",
        "role",
        "setting",
    ]


@pytest.mark.parametrize(
    ("default", "message"),
    [
        (
            {
                "type": "permission",
                "package": "bad",
                "permission": "android.permission.CAMERA",
                "state": "granted",
            },
            "package",
        ),
        (
            {
                "type": "permission",
                "package": "com.example.app",
                "permission": "CAMERA",
                "state": "granted",
            },
            "permission",
        ),
        ({"type": "role", "role": "bad", "holders": []}, "role"),
        ({"type": "role", "role": "android.app.role.BROWSER", "holders": ["bad"]}, "holders"),
        (
            {"type": "setting", "namespace": "system", "key": "show_touches", "value": "1"},
            "reserved",
        ),
        ({"type": "setting", "namespace": "system", "key": "not safe", "value": "1"}, "key"),
        ({"type": "unknown"}, "type"),
    ],
)
def test_rejects_invalid_capture_defaults(
    tmp_path: Path, default: dict[str, object], message: str
) -> None:
    path = write_config(tmp_path)
    data = yaml.safe_load(path.read_text())
    data["captures"]["home"]["defaults"] = [default]
    path.write_text(yaml.safe_dump(data, sort_keys=False))

    with pytest.raises(ConfigurationError, match=message):
        load_config(path)


def test_rejects_unknown_fields(tmp_path: Path) -> None:
    path = write_config(tmp_path, {"unexpected": True})

    with pytest.raises(ConfigurationError, match="unexpected"):
        load_config(path)


def test_rejects_unknown_template_fields(tmp_path: Path) -> None:
    path = write_config(tmp_path)
    text = path.read_text().replace("screenshots/raw/{locale}", "screenshots/raw/{device}")
    path.write_text(text)

    with pytest.raises(ConfigurationError, match="device"):
        load_config(path)


@pytest.mark.parametrize("unsafe", ["../{locale}", "/tmp/{locale}"])
def test_rejects_unsafe_template_paths(tmp_path: Path, unsafe: str) -> None:
    path = write_config(tmp_path)
    text = path.read_text().replace("screenshots/raw/{locale}", unsafe)
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
