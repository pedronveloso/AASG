"""Configuration loading, rendering, and path safety."""

from __future__ import annotations

import re
import string
from pathlib import Path, PurePosixPath

import yaml
from pydantic import ValidationError

from aasg import __version__
from aasg.errors import ConfigurationError
from aasg.models import CONFIG_SCHEMA_VERSION, AasgConfig, LocalFrameSource

ALLOWED_TEMPLATE_FIELDS = {"capture", "locale", "theme", "navigation", "artifact", "stem"}
SOURCE_KINDS = {
    "image": ("screenshots", ".png"),
    "video": ("videos", ".mp4"),
    "json": ("json", ".json"),
}


def load_config(path: Path) -> AasgConfig:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigurationError(f"Configuration file not found: {path}") from error
    except yaml.YAMLError as error:
        raise ConfigurationError(f"Invalid YAML in {path}: {error}") from error
    if not isinstance(raw, dict):
        raise ConfigurationError(f"Configuration root must be a mapping: {path}")
    schema_version = raw.get("schema")
    if schema_version is not None and schema_version != CONFIG_SCHEMA_VERSION:
        raise ConfigurationError(
            f"Unsupported configuration schema {schema_version!r}. AASG {__version__} requires "
            f"schema {CONFIG_SCHEMA_VERSION}; migrate {path.name} before retrying."
        )
    try:
        config = AasgConfig.model_validate(raw)
    except ValidationError as error:
        raise ConfigurationError(str(error)) from error
    validate_templates(config)
    validate_declared_paths(config, path)
    validate_source_paths(config)
    validate_publication_paths(config, path)
    return config


def validate_declared_paths(config: AasgConfig, config_path: Path) -> None:
    values = [
        config.project.artifact_root,
        config.project.run_log_root,
        config.android.gradle_wrapper,
        config.android.additional_output_dir,
    ]
    if config.android.direct_instrumentation:
        values.extend(
            [
                config.android.direct_instrumentation.app_apk,
                config.android.direct_instrumentation.test_apk,
            ]
        )
    values.extend(
        source.root
        for source in config.frame_sources.values()
        if isinstance(source, LocalFrameSource)
    )
    for value in values:
        project_path(config_path, value)


def validate_templates(config: AasgConfig) -> None:
    templates: list[str] = []
    for capture in config.captures.values():
        for artifact in capture.artifacts:
            templates.append(artifact.publish_dir)
            templates.extend(rendition.publish_dir for rendition in artifact.renditions)
            for publish_dir in [
                artifact.publish_dir,
                *(r.publish_dir for r in artifact.renditions),
            ]:
                if not any(
                    field == "locale" for _, field, _, _ in string.Formatter().parse(publish_dir)
                ):
                    raise ConfigurationError(
                        f"Publication directory must contain {{locale}}: {publish_dir!r}"
                    )
            if artifact.metadata and artifact.type == "json":
                raise ConfigurationError("JSON artifacts cannot have a metadata sidecar")
            for rendition in artifact.renditions:
                extension = publication_extension(
                    rendition.extension or SOURCE_KINDS[artifact.type][1]
                ).lower()
                supported = (
                    {".png", ".jpg", ".jpeg"}
                    if artifact.type == "image"
                    else {".mp4", ".mov", ".mkv", ".webm"}
                )
                if artifact.type == "json" or extension not in supported:
                    raise ConfigurationError(
                        f"Unsupported {artifact.type} rendition extension: {extension}"
                    )
    formatter = string.Formatter()
    for template in templates:
        template_path = PurePosixPath(template)
        if not template or template_path.is_absolute() or ".." in template_path.parts:
            raise ConfigurationError(f"Template must be a contained relative path: {template!r}")
        for _, field_name, format_spec, conversion in formatter.parse(template):
            if field_name and field_name not in ALLOWED_TEMPLATE_FIELDS:
                raise ConfigurationError(
                    f"Unsupported template field {field_name!r} in {template!r}"
                )
            if format_spec or conversion:
                raise ConfigurationError(f"Formatting modifiers are not supported in {template!r}")


def publication_extension(value: str) -> str:
    extension = value if value.startswith(".") and "/" not in value else PurePosixPath(value).suffix
    if not re.fullmatch(r"\.[A-Za-z0-9]+", extension):
        raise ConfigurationError(f"Publication extension must be a simple file suffix: {value!r}")
    return extension


def source_path(
    *,
    capture_id: str,
    artifact_id: str,
    artifact_count: int,
    artifact_type: str,
    locale: str,
    theme: str,
) -> str:
    directory, extension = SOURCE_KINDS[artifact_type]
    parts = [capture_id]
    if artifact_count > 1:
        parts.append(artifact_id)
    parts.append(theme)
    return str(PurePosixPath("aasg") / directory / locale / ("-".join(parts) + extension))


def metadata_path(source: str) -> str:
    return str(PurePosixPath(source).with_suffix(".metadata.json"))


def publication_path(
    publish_dir: str,
    *,
    capture_id: str,
    artifact_id: str,
    artifact_count: int,
    artifact_type: str,
    locale: str,
    theme: str,
    navigation: str,
    extension: str | None = None,
) -> str:
    values = {
        "capture": capture_id,
        "artifact": artifact_id,
        "stem": artifact_id,
        "locale": locale,
        "theme": theme,
        "navigation": navigation,
    }
    directory = render_template(publish_dir, **values)
    parts = [capture_id]
    if artifact_count > 1:
        parts.append(artifact_id)
    parts.append(theme)
    if navigation != "ignore":
        parts.append(navigation)
    suffix = publication_extension(extension or SOURCE_KINDS[artifact_type][1])
    return str(PurePosixPath(directory) / ("-".join(parts) + suffix))


def validate_source_paths(config: AasgConfig) -> None:
    seen: dict[str, str] = {}
    for capture_id, capture in config.captures.items():
        for locale in capture.locales or config.variants.locales:
            for theme in capture.themes or config.variants.themes:
                for artifact in capture.artifacts:
                    source = source_path(
                        capture_id=capture_id,
                        artifact_id=artifact.id,
                        artifact_count=len(capture.artifacts),
                        artifact_type=artifact.type,
                        locale=locale,
                        theme=theme,
                    )
                    owner = f"{capture_id}/{artifact.id}/{locale}/{theme}"
                    paths = [source]
                    if artifact.metadata:
                        paths.append(metadata_path(source))
                    for relative in paths:
                        if previous := seen.get(relative.casefold()):
                            raise ConfigurationError(
                                f"Inferred source path collision at {relative!r}: "
                                f"{previous} and {owner}"
                            )
                        seen[relative.casefold()] = owner


def validate_publication_paths(config: AasgConfig, config_path: Path) -> None:
    artifact_root = project_path(config_path, config.project.artifact_root)
    seen: dict[str, str] = {}
    for capture_id, capture in config.captures.items():
        navigation_modes = (
            ["gestural", "three-button"] if capture.navigation == "all" else [capture.navigation]
        )
        for locale in capture.locales or config.variants.locales:
            for theme in capture.themes or config.variants.themes:
                for navigation in navigation_modes:
                    for artifact in capture.artifacts:
                        paths = [
                            publication_path(
                                artifact.publish_dir,
                                capture_id=capture_id,
                                artifact_id=artifact.id,
                                artifact_count=len(capture.artifacts),
                                artifact_type=artifact.type,
                                locale=locale,
                                theme=theme,
                                navigation=navigation,
                            )
                        ]
                        paths.extend(
                            publication_path(
                                rendition.publish_dir,
                                capture_id=capture_id,
                                artifact_id=artifact.id,
                                artifact_count=len(capture.artifacts),
                                artifact_type=artifact.type,
                                locale=locale,
                                theme=theme,
                                navigation=navigation,
                                extension=rendition.extension,
                            )
                            for rendition in artifact.renditions
                        )
                        owner = f"{capture_id}/{artifact.id}/{locale}/{theme}/{navigation}"
                        for relative in paths:
                            destination = resolve_inside(artifact_root, relative)
                            collision_key = str(destination).casefold()
                            if previous := seen.get(collision_key):
                                raise ConfigurationError(
                                    f"Publication path collision at {relative!r}: "
                                    f"{previous} and {owner}"
                                )
                            seen[collision_key] = owner


def render_template(template: str, **values: str) -> str:
    try:
        return template.format(**values)
    except KeyError as error:
        raise ConfigurationError(
            f"Template {template!r} requires unavailable field {error.args[0]!r}"
        ) from error


def resolve_inside(base: Path, value: str) -> Path:
    resolved_base = base.resolve()
    candidate = (resolved_base / value).resolve()
    if not candidate.is_relative_to(resolved_base):
        raise ConfigurationError(f"Path escapes declared root {resolved_base}: {value}")
    return candidate


def project_path(config_path: Path, value: str) -> Path:
    return resolve_inside(config_path.resolve().parent, value)


STARTER_CONFIG = """# AASG configuration. Paths are relative to this file.
schema: 9
project:
  artifact_root: artifacts
  run_log_root: artifacts/aasg/runs
  default_timeout_seconds: 90
android:
  min_api: 33
  adb: adb
  gradle_wrapper: ./gradlew
  prepare_tasks: [":app:assembleDebug", ":app:assembleDebugAndroidTest"]
  test_task: ":app:connectedDebugAndroidTest"
  additional_output_dir: app/build/outputs/connected_android_test_additional_output
  locale_argument: screenshotLocale
  theme_argument: screenshotTheme
  # Optional compatibility path for hosts/devices where AGP launches `am instrument`
  # with an invalid symbolic user. APKs are still built by prepare_tasks.
  # direct_instrumentation:
  #   application_id: com.example.app
  #   test_application_id: com.example.app.test
  #   runner: com.example.TestRunner
  #   app_apk: app/build/outputs/apk/debug/app-debug.apk
  #   test_apk: app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
  #   device_output_dir: /sdcard/Android/media/com.example.app/additional_test_output
variants:
  locales: {en: English}
  themes: {light: Light, dark: Dark}
captures:
  home:
    label: Home
    description: Main screen after setup
    test: com.example.HomeScreenshotCaptureTest
    navigation: ignore
    # Optional Android defaults are applied before each variant and restored after the run.
    # defaults:
    #   - type: role
    #     role: android.app.role.BROWSER
    #     holders: [com.example.app]
    arguments: {screenshot: home, notAnnotation: ""}
    artifacts:
      - id: home
        type: image
        publish_dir: screenshots/raw/{locale}
  walkthrough:
    label: Walkthrough
    description: Recorded onboarding journey
    test: com.example.WalkthroughVideoCaptureTest
    show_taps: true
    arguments: {recording: walkthrough}
    artifacts:
      - id: walkthrough
        type: video
        publish_dir: videos/raw/{locale}
pipelines: {}
frame_sources: {}
"""
