from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from aasg import android
from aasg.android import (
    BrowserRoleController,
    BrowserRoleState,
    CommandResult,
    Device,
    NavigationController,
    NavigationState,
    ShowTapsController,
    ShowTapsState,
    active_user,
    browser_role_update_command,
    discover_devices,
    gradle_command,
    instrumentation_command,
    instrumentation_succeeded,
    navigation_switch_command,
    parse_browser_role_holders,
    parse_navigation_state,
    parse_show_taps_state,
    require_active_navigation,
    run_supervised,
    select_device,
    show_taps_state,
    show_taps_update_command,
)
from aasg.errors import CaptureError, PrerequisiteError
from aasg.models import AndroidConfig, CaptureConfig, DirectInstrumentationConfig


def test_android_testkit_wrapper_resolves_java_from_path(tmp_path: Path) -> None:
    java_directory = tmp_path / "bin"
    java_directory.mkdir()
    java = java_directory / "java"
    java.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    java.chmod(0o755)
    environment = os.environ | {"PATH": str(java_directory)}
    environment.pop("JAVA_HOME", None)

    result = subprocess.run(
        [str(Path(__file__).parents[1] / "android-testkit" / "gradlew"), "sentinel"],
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )

    assert result.returncode == 0
    assert "org.gradle.wrapper.GradleWrapperMain" in result.stdout
    assert "sentinel" in result.stdout


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
    monkeypatch.setattr(android, "_run_text", lambda command, **kwargs: "0\n")
    assert active_user("adb", "ABC") == 0

    monkeypatch.setattr(android, "_run_text", lambda command, **kwargs: "-2\n")
    with pytest.raises(PrerequisiteError, match="invalid active user"):
        active_user("adb", "ABC")


def test_parses_show_taps_state_and_builds_active_user_commands() -> None:
    assert parse_show_taps_state("null\n") == ShowTapsState(False, None)
    assert parse_show_taps_state("0\r\n") == ShowTapsState(True, False)
    assert parse_show_taps_state("1\n") == ShowTapsState(True, True)
    assert show_taps_update_command("adb", "ABC", 10, True) == [
        "adb",
        "-s",
        "ABC",
        "shell",
        "settings --user 10 put system show_touches 1",
    ]
    assert show_taps_update_command("adb", "ABC", 10, None)[-1] == (
        "settings --user 10 delete system show_touches"
    )


def test_reads_show_taps_for_active_user(monkeypatch: pytest.MonkeyPatch) -> None:
    commands: list[list[str]] = []

    def run(command, **kwargs):  # type: ignore[no-untyped-def]
        commands.append(list(command))
        return "1\n"

    monkeypatch.setattr(android, "_run_text", run)

    assert show_taps_state("adb", "ABC", 10) == ShowTapsState(True, True)
    assert commands == [
        [
            "adb",
            "-s",
            "ABC",
            "shell",
            "settings --user 10 get system show_touches",
        ]
    ]


def test_rejects_invalid_show_taps_state() -> None:
    with pytest.raises(PrerequisiteError, match="invalid Show taps value"):
        parse_show_taps_state("enabled")


def test_parses_browser_role_holders_and_builds_commands() -> None:
    assert parse_browser_role_holders("com.browser\n") == BrowserRoleState(("com.browser",))
    assert browser_role_update_command("adb", "ABC", 10, "add-role-holder", "app.altsea")[-1] == (
        "cmd role add-role-holder --user 10 android.app.role.BROWSER app.altsea"
    )
    with pytest.raises(PrerequisiteError, match="invalid browser role holder"):
        parse_browser_role_holders("not a package\n")


def test_browser_role_controller_restores_original_holders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    states = iter(
        [
            BrowserRoleState(("com.browser",)),
            BrowserRoleState(("app.altsea",)),
            BrowserRoleState(("app.altsea",)),
            BrowserRoleState(("com.browser",)),
        ]
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(android, "browser_role_state", lambda *args: next(states))
    monkeypatch.setattr(
        android,
        "run_supervised",
        lambda command, **kwargs: commands.append(list(command)) or CommandResult(0, 0.1),
    )
    controller = BrowserRoleController(
        adb="adb",
        serial="ABC",
        user=10,
        cwd=tmp_path,
        log_path=tmp_path / "browser-role.log",
        original_state=BrowserRoleState(("com.browser",)),
    )

    assert controller.ensure("app.altsea")["status"] == "succeeded"
    assert controller.restore()["status"] == "succeeded"
    assert [command[-1] for command in commands] == [
        "cmd role remove-role-holder --user 10 android.app.role.BROWSER com.browser",
        "cmd role add-role-holder --user 10 android.app.role.BROWSER app.altsea",
        "cmd role remove-role-holder --user 10 android.app.role.BROWSER app.altsea",
        "cmd role add-role-holder --user 10 android.app.role.BROWSER com.browser",
    ]


def test_show_taps_controller_enables_and_restores_unset_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    states = iter(
        [
            ShowTapsState(False, None),
            ShowTapsState(True, True),
            ShowTapsState(True, True),
            ShowTapsState(False, None),
        ]
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(android, "show_taps_state", lambda *args: next(states))

    def run(command, **kwargs):  # type: ignore[no-untyped-def]
        commands.append(list(command))
        return CommandResult(0, 0.1)

    monkeypatch.setattr(android, "run_supervised", run)
    controller = ShowTapsController(
        adb="adb",
        serial="ABC",
        user=10,
        cwd=tmp_path,
        log_path=tmp_path / "show-taps.log",
        original_state=ShowTapsState(False, None),
    )

    assert controller.ensure(True)["status"] == "succeeded"
    assert controller.current_state.effective is True
    assert controller.restore()["status"] == "succeeded"
    assert commands[0][-1].endswith("put system show_touches 1")
    assert commands[1][-1].endswith("delete system show_touches")
    assert "<device-serial>" in controller.manual_restore_guidance()


def test_show_taps_controller_skips_matching_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        android,
        "show_taps_state",
        lambda *args: ShowTapsState(True, False),
    )
    controller = ShowTapsController(
        adb="adb",
        serial="ABC",
        user=0,
        cwd=tmp_path,
        log_path=tmp_path / "show-taps.log",
        original_state=ShowTapsState(True, False),
    )

    assert controller.ensure(False)["status"] == "unchanged"
    assert not (tmp_path / "show-taps.log").exists()


def test_show_taps_controller_reports_verification_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        android,
        "show_taps_state",
        lambda *args: ShowTapsState(True, False),
    )
    monkeypatch.setattr(
        android,
        "run_supervised",
        lambda *args, **kwargs: CommandResult(0, 0.1),
    )
    controller = ShowTapsController(
        adb="adb",
        serial="ABC",
        user=0,
        cwd=tmp_path,
        log_path=tmp_path / "show-taps.log",
        original_state=ShowTapsState(True, False),
        verify_timeout_seconds=0,
    )

    with pytest.raises(PrerequisiteError, match="Timed out"):
        controller.ensure(True)
    assert controller.events[-1]["status"] == "failed"


def test_parses_android_navigation_overlays() -> None:
    state = parse_navigation_state(
        "android\n"
        "[x] com.android.internal.systemui.navbar.threebutton\n"
        "[ ] com.android.internal.systemui.navbar.gestural\n"
    )

    assert state.available == ("gestural", "three-button")
    assert state.active == "three-button"
    assert navigation_switch_command("adb", "ABC", 10, "gestural") == [
        "adb",
        "-s",
        "ABC",
        "shell",
        "cmd overlay enable-exclusive --user 10 --category "
        "com.android.internal.systemui.navbar.gestural",
    ]


@pytest.mark.parametrize(
    "state",
    [
        NavigationState(("gestural", "three-button"), ()),
        NavigationState(("gestural", "three-button"), ("gestural", "three-button")),
    ],
)
def test_requires_exactly_one_active_navigation_mode(state: NavigationState) -> None:
    with pytest.raises(PrerequisiteError, match="exactly one active"):
        require_active_navigation(state)


def test_navigation_controller_switches_and_restores(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    states = iter(
        [
            NavigationState(("gestural", "three-button"), ("three-button",)),
            NavigationState(("gestural", "three-button"), ("gestural",)),
            NavigationState(("gestural", "three-button"), ("gestural",)),
            NavigationState(("gestural", "three-button"), ("three-button",)),
        ]
    )
    commands: list[list[str]] = []
    monkeypatch.setattr(android, "navigation_state", lambda *args: next(states))

    def run(command, **kwargs):  # type: ignore[no-untyped-def]
        commands.append(list(command))
        return CommandResult(0, 0.1)

    monkeypatch.setattr(android, "run_supervised", run)
    controller = NavigationController(
        adb="adb",
        serial="ABC",
        user=0,
        cwd=tmp_path,
        log_path=tmp_path / "navigation.log",
        available=("gestural", "three-button"),
        original_mode="three-button",
        settle_seconds=0,
    )

    assert controller.ensure("gestural")["status"] == "succeeded"
    assert controller.restore()["status"] == "succeeded"
    assert controller.current_mode == "three-button"
    assert len(commands) == 2
    assert controller.events[-1]["action"] == "restore"


def test_navigation_controller_rejects_missing_mode(tmp_path: Path) -> None:
    controller = NavigationController(
        adb="adb",
        serial="ABC",
        user=0,
        cwd=tmp_path,
        log_path=tmp_path / "navigation.log",
        available=("gestural",),
        original_mode="gestural",
    )

    with pytest.raises(PrerequisiteError, match="three-button"):
        controller.require_modes({"gestural", "three-button"})


def test_navigation_controller_skips_an_already_active_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        android,
        "navigation_state",
        lambda *args: NavigationState(("gestural", "three-button"), ("gestural",)),
    )
    controller = NavigationController(
        adb="adb",
        serial="ABC",
        user=0,
        cwd=tmp_path,
        log_path=tmp_path / "navigation.log",
        available=("gestural", "three-button"),
        original_mode="gestural",
    )

    assert controller.ensure("gestural")["status"] == "unchanged"
    assert not (tmp_path / "navigation.log").exists()


def test_navigation_controller_reports_verification_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        android,
        "navigation_state",
        lambda *args: NavigationState(("gestural", "three-button"), ("three-button",)),
    )
    monkeypatch.setattr(
        android,
        "run_supervised",
        lambda *args, **kwargs: CommandResult(0, 0.1),
    )
    controller = NavigationController(
        adb="adb",
        serial="ABC",
        user=0,
        cwd=tmp_path,
        log_path=tmp_path / "navigation.log",
        available=("gestural", "three-button"),
        original_mode="three-button",
        verify_timeout_seconds=0,
        settle_seconds=0,
    )

    with pytest.raises(PrerequisiteError, match="Timed out"):
        controller.ensure("gestural")
    assert controller.events[-1]["status"] == "failed"


def test_navigation_controller_redacts_failed_event_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    serial = "device-serial-9876"
    monkeypatch.setattr(
        android,
        "navigation_state",
        lambda *args: NavigationState(("gestural", "three-button"), ("three-button",)),
    )

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise CaptureError(f"Command timed out: adb -s {serial} token=secret-value")

    monkeypatch.setattr(android, "run_supervised", fail)
    controller = NavigationController(
        adb="adb",
        serial=serial,
        user=0,
        cwd=tmp_path,
        log_path=tmp_path / "navigation.log",
        available=("gestural", "three-button"),
        original_mode="three-button",
        settle_seconds=0,
    )

    with pytest.raises(PrerequisiteError, match="Could not switch") as error:
        controller.ensure("gestural")

    assert serial not in str(error.value)
    assert serial not in controller.events[-1]["error"]
    assert "…9876" in controller.events[-1]["error"]
    assert "token=<redacted>" in controller.events[-1]["error"]


def test_show_taps_controller_redacts_failed_event_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    serial = "device-serial-9876"
    monkeypatch.setattr(
        android,
        "show_taps_state",
        lambda *args: ShowTapsState(True, False),
    )

    def fail(*args, **kwargs):  # type: ignore[no-untyped-def]
        raise CaptureError(f"Command timed out: adb -s {serial} token=secret-value")

    monkeypatch.setattr(android, "run_supervised", fail)
    controller = ShowTapsController(
        adb="adb",
        serial=serial,
        user=0,
        cwd=tmp_path,
        log_path=tmp_path / "show-taps.log",
        original_state=ShowTapsState(True, False),
    )

    with pytest.raises(PrerequisiteError, match="Could not update") as error:
        controller.ensure(True)

    assert serial not in str(error.value)
    assert serial not in controller.events[-1]["error"]
    assert "…9876" in controller.events[-1]["error"]
    assert "token=<redacted>" in controller.events[-1]["error"]


def test_recognizes_instrumentation_result() -> None:
    assert instrumentation_succeeded(
        CommandResult(0, 1.0, ("OK (1 test)", "INSTRUMENTATION_CODE: -1"))
    )
    assert not instrumentation_succeeded(
        CommandResult(0, 1.0, ("FAILURES!!!", "INSTRUMENTATION_CODE: -1"))
    )


def test_supervised_command_times_out_even_without_output(tmp_path: Path) -> None:
    serial = "device-serial-9876"
    with pytest.raises(CaptureError, match="timed out") as error:
        run_supervised(
            [sys.executable, "-c", "import time; time.sleep(5)", serial],
            cwd=tmp_path,
            timeout_seconds=1,
            log_path=tmp_path / "command.log",
            serial=serial,
        )

    assert serial not in str(error.value)
    assert "…9876" in str(error.value)
