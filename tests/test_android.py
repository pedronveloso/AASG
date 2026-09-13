from __future__ import annotations

import sys
from pathlib import Path

import pytest

from aasg import android
from aasg.android import (
    CommandResult,
    Device,
    active_user,
    discover_devices,
    gradle_command,
    instrumentation_command,
    instrumentation_succeeded,
    run_supervised,
    select_device,
)
from aasg.errors import CaptureError, PrerequisiteError
from aasg.models import AndroidConfig, CaptureConfig, DirectInstrumentationConfig


def test_discovers_devices(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        android,
        "_run_text",
        lambda command: (
            "List of devices attached\n"
            "emulator-5554 device product:sdk model:Pixel_8 transport_id:1\n"
            "ABC unauthorized transport_id:2\n"
        ),
    )

    devices = discover_devices("adb")

    assert devices[0] == Device("emulator-5554", "device", "Pixel 8", "sdk")
    assert devices[1].state == "unauthorized"


def test_select_device_requires_explicit_serial_for_multiple() -> None:
    devices = [Device("one", "device"), Device("two", "device")]

    with pytest.raises(PrerequisiteError, match="More than one"):
        select_device(devices, None)
    assert select_device(devices, "two").serial == "two"


def test_builds_gradle_runner_arguments() -> None:
    config = AndroidConfig(
        test_task=":app:connectedDebugAndroidTest",
        additional_output_dir="output",
        locale_argument="locale",
        theme_argument="theme",
    )
    capture = CaptureConfig(
        label="Home",
        test="example.HomeTest",
        arguments={"scenario": "home", "notAnnotation": ""},
        artifacts=[],
    )

    command = gradle_command(config, capture, "en", "dark")

    assert command[:2] == ["./gradlew", ":app:connectedDebugAndroidTest"]
    assert "-Pandroid.testInstrumentationRunnerArguments.class=example.HomeTest" in command
    assert "-Pandroid.testInstrumentationRunnerArguments.notAnnotation=" in command


def test_builds_direct_instrumentation_with_numeric_user_and_empty_argument() -> None:
    config = AndroidConfig(
        test_task=":app:connectedDebugAndroidTest",
        additional_output_dir="output",
        locale_argument="locale",
        theme_argument="theme",
        direct_instrumentation=DirectInstrumentationConfig(
            application_id="example.app",
            test_application_id="example.app.test",
            runner="example.Runner",
            app_apk="app.apk",
            test_apk="test.apk",
            device_output_dir="/sdcard/Android/media/example.app/output",
        ),
    )
    capture = CaptureConfig(
        label="Home",
        test="example.HomeTest",
        arguments={"notAnnotation": ""},
        artifacts=[],
    )

    command = instrumentation_command(config, capture, "en", "dark", serial="ABC", user=0)

    assert command[:4] == ["adb", "-s", "ABC", "shell"]
    assert "am instrument --user 0" in command[4]
    assert "-e notAnnotation ''" in command[4]
    assert command[4].endswith("example.app.test/example.Runner")


def test_reads_and_validates_active_android_user(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(android, "_run_text", lambda command: "0\n")
    assert active_user("adb", "ABC") == 0

    monkeypatch.setattr(android, "_run_text", lambda command: "-2\n")
    with pytest.raises(PrerequisiteError, match="invalid active user"):
        active_user("adb", "ABC")


def test_recognizes_instrumentation_result() -> None:
    assert instrumentation_succeeded(
        CommandResult(0, 1.0, ("OK (1 test)", "INSTRUMENTATION_CODE: -1"))
    )
    assert not instrumentation_succeeded(
        CommandResult(0, 1.0, ("FAILURES!!!", "INSTRUMENTATION_CODE: -1"))
    )


def test_supervised_command_times_out_even_without_output(tmp_path: Path) -> None:
    with pytest.raises(CaptureError, match="timed out"):
        run_supervised(
            [sys.executable, "-c", "import time; time.sleep(5)"],
            cwd=tmp_path,
            timeout_seconds=1,
            log_path=tmp_path / "command.log",
        )
