"""Configuration loading, rendering, and path safety."""

from __future__ import annotations

import string
from pathlib import Path, PurePosixPath

import yaml
from pydantic import ValidationError

from aasg import __version__
from aasg.errors import ConfigurationError
from aasg.models import CONFIG_SCHEMA_VERSION, AasgConfig, LocalFrameSource

ALLOWED_TEMPLATE_FIELDS = {"capture", "locale", "theme", "artifact", "stem"}


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
            templates.extend([artifact.source, artifact.publish])
            if artifact.metadata:
                templates.append(artifact.metadata)
            templates.extend(rendition.publish for rendition in artifact.renditions)
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
schema: 2
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
    test: com.example.HomeScreenshotCaptureTest
    arguments: {screenshot: home, notAnnotation: ""}
    artifacts:
      - id: home
        type: image
        source: screenshots/{locale}/home-{theme}.png
        publish: screenshots/raw/{locale}/home-{theme}.png
pipelines: {}
frame_sources: {}
"""
