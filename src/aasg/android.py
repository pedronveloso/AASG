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
from aasg.models import AndroidConfig, CaptureConfig

SECRET_PATTERN = re.compile(r"(?i)(password|token|secret|api[_-]?key)=([^\s]+)")


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


def redact_serial(serial: str) -> str:
    return f"…{serial[-4:]}" if len(serial) > 4 else "…"


def redact_line(line: str, serial: str | None = None) -> str:
    redacted = line.replace(serial, redact_serial(serial)) if serial else line
    return SECRET_PATTERN.sub(lambda match: f"{match.group(1)}=<redacted>", redacted)


def _run_text(command: Sequence[str], timeout: float = 10) -> str:
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
        raise PrerequisiteError(f"Command failed: {' '.join(command)}") from error


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
    raw_api = _run_text([adb, "-s", device.serial, "shell", "getprop", "ro.build.version.sdk"])
    try:
        api = int(raw_api.strip().replace("\r", ""))
    except ValueError as error:
        raise PrerequisiteError(f"Could not read API level from {device.label}") from error
    return Device(device.serial, device.state, device.model, device.product, api)


def active_user(adb: str, serial: str) -> int:
    raw_user = _run_text([adb, "-s", serial, "shell", "am", "get-current-user"])
    try:
        user = int(raw_user.strip().replace("\r", ""))
    except ValueError as error:
        raise PrerequisiteError(f"Could not resolve the active Android user on {serial}") from error
    if user < 0:
        raise PrerequisiteError(f"Android returned an invalid active user: {user}")
    return user


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
                        f"Command timed out after {timeout_seconds}s: {' '.join(command)}"
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
        )
    except PrerequisiteError as error:
        output = f"Could not collect logcat: {error}\n"
    destination.write_text(
        "\n".join(redact_line(line, serial) for line in output.splitlines()) + "\n",
        encoding="utf-8",
    )
