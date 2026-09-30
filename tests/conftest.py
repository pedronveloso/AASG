from __future__ import annotations

from pathlib import Path

import yaml


def write_config(root: Path, overrides: dict[str, object] | None = None) -> Path:
    data: dict[str, object] = {
        "schema": 9,
        "project": {
            "artifact_root": "artifacts",
            "run_log_root": "artifacts/aasg/runs",
            "default_timeout_seconds": 5,
        },
        "android": {
            "min_api": 33,
            "adb": "adb",
            "gradle_wrapper": "./gradlew",
            "prepare_tasks": [],
            "test_task": ":app:connectedDebugAndroidTest",
            "additional_output_dir": "app/build/outputs/additional",
            "locale_argument": "screenshotLocale",
            "theme_argument": "screenshotTheme",
        },
        "variants": {
            "locales": {"en": "English", "es": "Spanish"},
            "themes": {"light": "Light", "dark": "Dark"},
            "groups": {"screenshots": ["home"]},
        },
        "captures": {
            "home": {
                "label": "Home",
                "description": "Current connection and audio path",
                "test": "example.HomeCaptureTest",
                "arguments": {"scenario": "home"},
                "artifacts": [
                    {
                        "id": "home",
                        "type": "image",
                        "publish_dir": "screenshots/raw/{locale}",
                    }
                ],
            }
        },
        "pipelines": {},
        "frame_sources": {},
    }
    if overrides:
        data.update(overrides)
    path = root / "aasg.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path
