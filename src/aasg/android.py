"""ADB discovery and supervised subprocess execution."""

from __future__ import annotations

import os
import queue
import re
import shlex
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from aasg.errors import CaptureError, PrerequisiteError
from aasg.models import AndroidConfig, CaptureConfig, NavigationMode

SECRET_PATTERN = re.compile(r"(?i)(password|token|secret|api[_-]?key)=([^\s]+)")
NAVIGATION_OVERLAYS: dict[NavigationMode, str] = {
    "gestural": "com.android.internal.systemui.navbar.gestural",
    "three-button": "com.android.internal.systemui.navbar.threebutton",
}
NAVIGATION_MODES: tuple[NavigationMode, ...] = ("gestural", "three-button")


@dataclass(frozen=True)
class Device:
    serial: str
    state: str
    model: str | None = None
    product: str | None = None
    api: int | None = None

    @property
    def label(self) -> str:
        details = self.model or self.product or "Android device"
        api = f", API {self.api}" if self.api else ""
        return f"{details}{api} ({redact_serial(self.serial)})"


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    duration_seconds: float
    output: tuple[str, ...] = ()


@dataclass(frozen=True)
class NavigationState:
    available: tuple[NavigationMode, ...]
    enabled: tuple[NavigationMode, ...]

    @property
    def active(self) -> NavigationMode | None:
        return self.enabled[0] if len(self.enabled) == 1 else None


@dataclass(frozen=True)
class ShowTapsState:
    present: bool
    value: bool | None

    @property
    def effective(self) -> bool:
        return bool(self.value) if self.present else False


def redact_serial(serial: str) -> str:
    return f"…{serial[-4:]}" if len(serial) > 4 else "…"


def redact_line(line: str, serial: str | None = None) -> str:
    redacted = line.replace(serial, redact_serial(serial)) if serial else line
    return SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=<redacted>", redacted)


def redact_error(error: Exception, serial: str | None = None) -> str:
    return redact_line(str(error), serial)


def _run_text(command: Sequence[str], timeout: float = 10, *, serial: str | None = None) -> str:
    try:
        return subprocess.run(
            list(command),
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        ).stdout
    except FileNotFoundError as error:
        raise PrerequisiteError(f"Executable not found: {command[0]}") from error
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        raise PrerequisiteError(
            f"Command failed: {redact_line(' '.join(command), serial)}"
        ) from error


def discover_devices(adb: str) -> list[Device]:
    output = _run_text([adb, "devices", "-l"])
    devices: list[Device] = []
    for line in output.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 2:
            continue
        properties = dict(part.split(":", 1) for part in parts[2:] if ":" in part)
        devices.append(
            Device(
                serial=parts[0],
                state=parts[1],
                model=properties.get("model", "").replace("_", " ") or None,
                product=properties.get("product"),
            )
        )
    return devices


def enrich_device(adb: str, device: Device) -> Device:
    raw_api = _run_text(
        [adb, "-s", device.serial, "shell", "getprop", "ro.build.version.sdk"],
        serial=device.serial,
    )
    try:
        api = int(raw_api.strip().replace("\r", ""))
    except ValueError as error:
        raise PrerequisiteError(f"Could not read API level from {device.label}") from error
    return Device(device.serial, device.state, device.model, device.product, api)


def active_user(adb: str, serial: str) -> int:
    raw_user = _run_text([adb, "-s", serial, "shell", "am", "get-current-user"], serial=serial)
    try:
        user = int(raw_user.strip().replace("\r", ""))
    except ValueError as error:
        raise PrerequisiteError(
            f"Could not resolve the active Android user on {redact_serial(serial)}"
        ) from error
    if user < 0:
        raise PrerequisiteError(f"Android returned an invalid active user: {user}")
    return user


def parse_navigation_state(output: str) -> NavigationState:
    statuses: dict[NavigationMode, bool] = {}
    for line in output.splitlines():
        match = re.fullmatch(r"\s*\[(?P<state>[ x])\]\s+(?P<package>\S+)\s*", line)
        if match is None:
            continue
        for mode, package in NAVIGATION_OVERLAYS.items():
            if match.group("package") == package:
                statuses[mode] = match.group("state") == "x"
                break
    available = tuple(mode for mode in NAVIGATION_MODES if mode in statuses)
    enabled = tuple(mode for mode in NAVIGATION_MODES if statuses.get(mode))
    return NavigationState(available, enabled)


def navigation_state(adb: str, serial: str, user: int) -> NavigationState:
    output = _run_text(
        [adb, "-s", serial, "shell", "cmd", "overlay", "list", "--user", str(user), "android"],
        serial=serial,
    )
    return parse_navigation_state(output)


def require_active_navigation(state: NavigationState) -> NavigationMode:
    if state.active is None:
        detected = ", ".join(state.enabled) or "none"
        raise PrerequisiteError(
            "Could not identify exactly one active Android navigation mode "
            f"(enabled recognized modes: {detected})"
        )
    return state.active


def navigation_switch_command(adb: str, serial: str, user: int, mode: NavigationMode) -> list[str]:
    return adb_shell_command(
        adb,
        serial,
        [
            "cmd",
            "overlay",
            "enable-exclusive",
            "--user",
            str(user),
            "--category",
            NAVIGATION_OVERLAYS[mode],
        ],
    )


def parse_show_taps_state(output: str) -> ShowTapsState:
    value = output.strip().replace("\r", "")
    if value == "null":
        return ShowTapsState(False, None)
    if value == "0":
        return ShowTapsState(True, False)
    if value == "1":
        return ShowTapsState(True, True)
    raise PrerequisiteError(f"Android returned an invalid Show taps value: {value!r}")


def show_taps_state(adb: str, serial: str, user: int) -> ShowTapsState:
    try:
        return parse_show_taps_state(
            _run_text(
                adb_shell_command(
                    adb,
                    serial,
                    ["settings", "--user", str(user), "get", "system", "show_touches"],
                ),
                serial=serial,
            )
        )
    except PrerequisiteError as error:
        raise PrerequisiteError("Could not read Android Show taps for the active user") from error


def show_taps_update_command(adb: str, serial: str, user: int, value: bool | None) -> list[str]:
    operation = ["delete", "system", "show_touches"]
    if value is not None:
        operation = ["put", "system", "show_touches", "1" if value else "0"]
    return adb_shell_command(adb, serial, ["settings", "--user", str(user), *operation])


def select_device(devices: list[Device], requested: str | None) -> Device:
    online = [device for device in devices if device.state == "device"]
    if requested:
        matching = [device for device in online if device.serial == requested]
        if not matching:
            raise PrerequisiteError(f"Device {requested!r} is not online and authorized")
        return matching[0]
    if len(online) == 1:
        return online[0]
    if not online:
        raise PrerequisiteError("No ADB-authorized devices or emulators are online")
    raise PrerequisiteError("More than one device is online; select one with --device")


def gradle_command(
    android: AndroidConfig,
    capture: CaptureConfig,
    locale: str,
    theme: str,
) -> list[str]:
    command = [android.gradle_wrapper, android.test_task]
    arguments = instrumentation_arguments(android, capture, locale, theme)
    command.extend(
        f"-Pandroid.testInstrumentationRunnerArguments.{key}={value}"
        for key, value in arguments.items()
    )
    return command


def instrumentation_arguments(
    android: AndroidConfig,
    capture: CaptureConfig,
    locale: str,
    theme: str,
) -> dict[str, str]:
    return {
        "class": capture.test,
        android.locale_argument: locale,
        android.theme_argument: theme,
        **capture.arguments,
    }


def adb_shell_command(adb: str, serial: str, remote: Sequence[str]) -> list[str]:
    return [adb, "-s", serial, "shell", shlex.join(remote)]


def instrumentation_command(
    android: AndroidConfig,
    capture: CaptureConfig,
    locale: str,
    theme: str,
    *,
    serial: str,
    user: int,
) -> list[str]:
    direct = android.direct_instrumentation
    if direct is None:
        raise ValueError("direct_instrumentation is not configured")
    remote = ["am", "instrument", "--user", str(user), "-r", "-w"]
    for key, value in instrumentation_arguments(android, capture, locale, theme).items():
        remote.extend(["-e", key, value])
    remote.extend(["-e", "additionalTestOutputDir", direct.device_output_dir])
    remote.append(f"{direct.test_application_id}/{direct.runner}")
    return adb_shell_command(android.adb, serial, remote)


def instrumentation_succeeded(result: CommandResult) -> bool:
    output = "\n".join(result.output)
    return (
        result.returncode == 0
        and "INSTRUMENTATION_CODE: -1" in output
        and "INSTRUMENTATION_FAILED" not in output
        and "FAILURES!!!" not in output
    )


def run_supervised(
    command: Sequence[str],
    *,
    cwd: Path,
    timeout_seconds: int,
    log_path: Path,
    env: Mapping[str, str] | None = None,
    serial: str | None = None,
    on_line: Callable[[str], None] | None = None,
    append: bool = False,
) -> CommandResult:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            env=merged_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
    except FileNotFoundError as error:
        raise PrerequisiteError(f"Executable not found: {command[0]}") from error

    try:
        captured: list[str] = []
        with log_path.open("a" if append else "w", encoding="utf-8") as log:
            assert process.stdout is not None
            lines: queue.Queue[str | None] = queue.Queue()

            def read_output() -> None:
                assert process.stdout is not None
                try:
                    for output_line in process.stdout:
                        lines.put(output_line)
                finally:
                    lines.put(None)

            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            while True:
                remaining = timeout_seconds - (time.monotonic() - started)
                if remaining <= 0:
                    _terminate_process_group(process)
                    raise CaptureError(
                        f"Command timed out after {timeout_seconds}s: "
                        f"{redact_line(' '.join(command), serial)}"
                    )
                try:
                    line = lines.get(timeout=min(0.1, remaining))
                except queue.Empty:
                    continue
                if line is None:
                    break
                if line:
                    clean = redact_line(line.rstrip("\n"), serial)
                    captured.append(clean)
                    log.write(clean + "\n")
                    log.flush()
                    if on_line:
                        on_line(clean)
            reader.join(timeout=1)
    except KeyboardInterrupt:
        _terminate_process_group(process)
        raise
    return CommandResult(process.wait(), time.monotonic() - started, tuple(captured))


class NavigationController:
    def __init__(
        self,
        *,
        adb: str,
        serial: str,
        user: int,
        cwd: Path,
        log_path: Path,
        available: tuple[NavigationMode, ...],
        original_mode: NavigationMode,
        verbose: bool = False,
        verify_timeout_seconds: float = 10,
        settle_seconds: float = 0.5,
    ) -> None:
        self.adb = adb
        self.serial = serial
        self.user = user
        self.cwd = cwd
        self.log_path = log_path
        self.available = available
        self.original_mode = original_mode
        self.current_mode = original_mode
        self.verbose = verbose
        self.verify_timeout_seconds = verify_timeout_seconds
        self.settle_seconds = settle_seconds
        self.events: list[dict[str, object]] = []

    @classmethod
    def inspect(
        cls,
        *,
        adb: str,
        serial: str,
        user: int,
        cwd: Path,
        log_path: Path,
        verbose: bool = False,
    ) -> NavigationController:
        state = navigation_state(adb, serial, user)
        original = require_active_navigation(state)
        return cls(
            adb=adb,
            serial=serial,
            user=user,
            cwd=cwd,
            log_path=log_path,
            available=state.available,
            original_mode=original,
            verbose=verbose,
        )

    def require_modes(self, modes: set[NavigationMode]) -> None:
        missing = modes - set(self.available)
        if missing:
            raise PrerequisiteError(
                "Device does not expose the required Android navigation overlay(s): "
                + ", ".join(sorted(missing))
            )

    def ensure(self, mode: NavigationMode, *, action: str = "switch") -> dict[str, object]:
        if mode not in self.available:
            raise PrerequisiteError(f"Device does not expose Android navigation mode {mode!r}")
        observed = navigation_state(self.adb, self.serial, self.user)
        current = require_active_navigation(observed)
        self.current_mode = current
        if current == mode:
            event: dict[str, object] = {
                "action": action,
                "mode": mode,
                "status": "unchanged",
            }
            self.events.append(event)
            return event

        command = navigation_switch_command(self.adb, self.serial, self.user, mode)
        event = {
            "action": action,
            "mode": mode,
            "status": "failed",
            "command": [
                redact_serial(self.serial) if value == self.serial else value for value in command
            ],
        }
        started = time.monotonic()
        try:
            result = run_supervised(
                command,
                cwd=self.cwd,
                timeout_seconds=max(1, int(self.verify_timeout_seconds)),
                log_path=self.log_path,
                serial=self.serial,
                on_line=print if self.verbose else None,
                append=self.log_path.exists(),
            )
            if result.returncode:
                raise PrerequisiteError(
                    f"Android navigation switch returned {result.returncode} for {mode!r}"
                )
            deadline = time.monotonic() + self.verify_timeout_seconds
            while time.monotonic() < deadline:
                verified = navigation_state(self.adb, self.serial, self.user)
                if verified.active == mode:
                    self.current_mode = mode
                    if self.settle_seconds:
                        time.sleep(self.settle_seconds)
                    event["status"] = "succeeded"
                    event["duration_seconds"] = time.monotonic() - started
                    self.events.append(event)
                    return event
                time.sleep(0.1)
            raise PrerequisiteError(
                f"Timed out waiting for Android navigation mode {mode!r} to become active"
            )
        except CaptureError as error:
            event["error"] = redact_error(error, self.serial)
            self.events.append(event)
            raise PrerequisiteError(
                f"Could not switch Android navigation mode to {mode!r}"
            ) from error
        except Exception as error:
            event["error"] = redact_error(error, self.serial)
            self.events.append(event)
            raise

    def restore(self) -> dict[str, object]:
        return self.ensure(self.original_mode, action="restore")

    def manual_restore_guidance(self) -> str:
        command = navigation_switch_command(
            self.adb, "<device-serial>", self.user, self.original_mode
        )
        return shlex.join(command)


class ShowTapsController:
    def __init__(
        self,
        *,
        adb: str,
        serial: str,
        user: int,
        cwd: Path,
        log_path: Path,
        original_state: ShowTapsState,
        verbose: bool = False,
        verify_timeout_seconds: float = 10,
    ) -> None:
        self.adb = adb
        self.serial = serial
        self.user = user
        self.cwd = cwd
        self.log_path = log_path
        self.original_state = original_state
        self.current_state = original_state
        self.verbose = verbose
        self.verify_timeout_seconds = verify_timeout_seconds
        self.events: list[dict[str, object]] = []

    @classmethod
    def inspect(
        cls,
        *,
        adb: str,
        serial: str,
        user: int,
        cwd: Path,
        log_path: Path,
        verbose: bool = False,
    ) -> ShowTapsController:
        return cls(
            adb=adb,
            serial=serial,
            user=user,
            cwd=cwd,
            log_path=log_path,
            original_state=show_taps_state(adb, serial, user),
            verbose=verbose,
        )

    def ensure(
        self,
        value: bool | None,
        *,
        action: str = "set",
    ) -> dict[str, object]:
        target = ShowTapsState(value is not None, value)
        observed = show_taps_state(self.adb, self.serial, self.user)
        self.current_state = observed
        if observed == target:
            event: dict[str, object] = {
                "action": action,
                "value": value,
                "status": "unchanged",
            }
            self.events.append(event)
            return event

        command = show_taps_update_command(self.adb, self.serial, self.user, value)
        event = {
            "action": action,
            "value": value,
            "status": "failed",
            "command": [
                redact_serial(self.serial) if item == self.serial else item for item in command
            ],
        }
        started = time.monotonic()
        try:
            result = run_supervised(
                command,
                cwd=self.cwd,
                timeout_seconds=max(1, int(self.verify_timeout_seconds)),
                log_path=self.log_path,
                serial=self.serial,
                on_line=print if self.verbose else None,
                append=self.log_path.exists(),
            )
            if result.returncode:
                raise PrerequisiteError(f"Android Show taps update returned {result.returncode}")
            deadline = time.monotonic() + self.verify_timeout_seconds
            while True:
                verified = show_taps_state(self.adb, self.serial, self.user)
                if verified == target:
                    self.current_state = target
                    event["status"] = "succeeded"
                    event["duration_seconds"] = time.monotonic() - started
                    self.events.append(event)
                    return event
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.1)
            raise PrerequisiteError("Timed out waiting for Android Show taps to change")
        except CaptureError as error:
            event["error"] = redact_error(error, self.serial)
            self.events.append(event)
            raise PrerequisiteError("Could not update Android Show taps") from error
        except Exception as error:
            event["error"] = redact_error(error, self.serial)
            self.events.append(event)
            raise

    def restore(self) -> dict[str, object]:
        return self.ensure(self.original_state.value, action="restore")

    def manual_restore_guidance(self) -> str:
        return shlex.join(
            show_taps_update_command(
                self.adb,
                "<device-serial>",
                self.user,
                self.original_state.value,
            )
        )


def _terminate_process_group(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        process.wait()


def capture_logcat(adb: str, serial: str, destination: Path) -> None:
    try:
        output = _run_text(
            [
                adb,
                "-s",
                serial,
                "logcat",
                "-d",
                "-t",
                "150",
                "-v",
                "brief",
                "AndroidRuntime:E",
                "TestRunner:I",
                "*:S",
            ],
            timeout=15,
            serial=serial,
        )
    except PrerequisiteError as error:
        output = f"Could not collect logcat: {error}\n"
    destination.write_text(
        "\n".join(redact_line(line, serial) for line in output.splitlines()) + "\n",
        encoding="utf-8",
    )
