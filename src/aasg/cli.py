"""AASG command-line interface."""

from __future__ import annotations

import json
import shutil
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from aasg import __version__
from aasg.android import (
    NAVIGATION_MODES,
    Device,
    active_user,
    discover_devices,
    enrich_device,
    navigation_state,
    redact_serial,
    require_active_navigation,
)
from aasg.capture import (
    CaptureRunner,
    Selection,
    expand_capture_ids,
    expand_navigation_modes,
    expand_variant_ids,
    has_selectable_navigation,
)
from aasg.config import STARTER_CONFIG, load_config, project_path
from aasg.errors import (
    AasgError,
    CaptureError,
    ConfigurationError,
    ExitCode,
    PrerequisiteError,
)
from aasg.frames import (
    cache_root,
    frame_cache_available,
    list_frames,
    refresh_source,
    resolve_frame,
)
from aasg.media import MediaProcessor
from aasg.models import AasgConfig, DeviceFrameStep, NavigationMode, RemoteFrameSource
from aasg.state import load_selection, save_selection

app = typer.Typer(
    help="Deterministic Android capture-to-publish pipelines.",
    no_args_is_help=True,
    invoke_without_command=True,
)
config_app = typer.Typer(help="Validate and inspect project configuration.")
frames_app = typer.Typer(help="Inspect and cache device-frame assets.")
app.add_typer(config_app, name="config")
app.add_typer(frames_app, name="frames")
console = Console(stderr=True)
NAVIGATION_CHOICES = {
    "gestural": "Gesture navigation",
    "three-button": "Three-button navigation",
}

ConfigOption = Annotated[
    Path, typer.Option("--config", "-c", help="Path to aasg.yaml.", dir_okay=False)
]


def _previous_selection_summary(previous: dict[str, object], config: AasgConfig) -> str:
    def values(key: str) -> list[str]:
        value = previous.get(key)
        return [str(item) for item in value] if isinstance(value, list) else []

    def labeled(ids: list[str], labels: Mapping[str, str]) -> str:
        return (
            ", ".join(f"{labels[item]} ({item})" if item in labels else item for item in ids)
            or "none"
        )

    capture_labels = {capture_id: capture.label for capture_id, capture in config.captures.items()}
    device = previous.get("device")
    device_label = redact_serial(device) if isinstance(device, str) else "none"
    return (
        "Previous selection:\n"
        f"  Device: {device_label}\n"
        f"  Captures: {labeled(values('captures'), capture_labels)}\n"
        f"  Locales: {labeled(values('locales'), config.variants.locales)}\n"
        f"  Themes: {labeled(values('themes'), config.variants.themes)}\n"
        f"  Navigation for 'all' captures: "
        f"{labeled(values('navigation'), NAVIGATION_CHOICES)}"
    )


def _fail(error: Exception) -> None:
    if isinstance(error, AasgError):
        code = int(error.exit_code)
    elif isinstance(error, ValidationError):
        code = int(ExitCode.USAGE)
    else:
        code = int(ExitCode.PROCESSING_FAILED)
    console.print(f"[red]Error:[/red] {error}")
    raise typer.Exit(code) from error


@app.callback()
def root(
    version: Annotated[bool, typer.Option("--version", help="Show the AASG version.")] = False,
) -> None:
    if version:
        typer.echo(__version__)
        raise typer.Exit()


@app.command("init")
def initialize(
    destination: Annotated[
        Path, typer.Argument(help="Configuration file to create.", dir_okay=False)
    ] = Path("aasg.yaml"),
) -> None:
    """Create a commented starter configuration."""
    if destination.exists():
        _fail(ConfigurationError(f"Refusing to overwrite existing file: {destination}"))
    destination.write_text(STARTER_CONFIG, encoding="utf-8")
    console.print(f"Created [bold]{destination}[/bold]")


@config_app.command("validate")
def validate_config(config_path: ConfigOption = Path("aasg.yaml")) -> None:
    """Strictly validate a project configuration."""
    try:
        config = load_config(config_path)
    except Exception as error:
        _fail(error)
    console.print(
        f"Valid schema {config.schema_version}: {len(config.captures)} capture(s), "
        f"{len(config.pipelines)} pipeline(s)"
    )


@app.command()
def doctor(
    config_path: ConfigOption = Path("aasg.yaml"),
    json_output: Annotated[bool, typer.Option("--json", help="Print JSON results.")] = False,
) -> None:
    """Check host tools, project paths, configuration, and Android devices."""
    checks: list[dict[str, object]] = [
        {
            "check": "Python",
            "ok": sys.version_info >= (3, 12),
            "detail": sys.version.split()[0],
        }
    ]
    try:
        config = load_config(config_path)
        checks.append({"check": "configuration", "ok": True, "detail": str(config_path)})
        for name, executable in (
            ("adb", config.android.adb),
            ("ffmpeg", "ffmpeg"),
            ("ffprobe", "ffprobe"),
        ):
            path = shutil.which(executable)
            checks.append({"check": name, "ok": path is not None, "detail": path or "missing"})
        gradle = project_path(config_path, config.android.gradle_wrapper)
        checks.append({"check": "Gradle wrapper", "ok": gradle.is_file(), "detail": str(gradle)})
        if config.android.direct_instrumentation:
            direct = config.android.direct_instrumentation
            apk_paths = [
                project_path(config_path, direct.app_apk),
                project_path(config_path, direct.test_apk),
            ]
            checks.append(
                {
                    "check": "Instrumentation APKs",
                    "ok": True,
                    "detail": [
                        f"{path} ({'ready' if path.is_file() else 'built during preparation'})"
                        for path in apk_paths
                    ],
                }
            )
        output = project_path(config_path, config.android.additional_output_dir)
        checks.append(
            {
                "check": "Test Storage output",
                "ok": project_path(config_path, ".").is_dir(),
                "detail": f"configured at {output}",
            }
        )
        try:
            devices = discover_devices(config.android.adb)
            online = [
                enrich_device(config.android.adb, device)
                for device in devices
                if device.state == "device"
            ]
            checks.append(
                {
                    "check": "Android devices",
                    "ok": bool(online),
                    "detail": [f"{device.label}: {device.state}" for device in devices],
                }
            )
            checks.append(
                {
                    "check": "Device authorization",
                    "ok": bool(devices) and all(device.state == "device" for device in devices),
                    "detail": [
                        f"{device.label}: {device.state}"
                        for device in devices
                        if device.state != "device"
                    ]
                    or "all connected devices authorized",
                }
            )
            checks.append(
                {
                    "check": "Minimum API",
                    "ok": bool(online)
                    and all((device.api or 0) >= config.android.min_api for device in online),
                    "detail": f"requires API {config.android.min_api}+",
                }
            )
            required_navigation: set[NavigationMode] = set()
            for capture_config in config.captures.values():
                if capture_config.navigation == "all":
                    required_navigation.update(NAVIGATION_MODES)
                elif capture_config.navigation == "gestural":
                    required_navigation.add("gestural")
                elif capture_config.navigation == "three-button":
                    required_navigation.add("three-button")
            navigation_details: list[str] = []
            navigation_ok = True
            if required_navigation:
                for online_device in online:
                    try:
                        user = active_user(config.android.adb, online_device.serial)
                        state = navigation_state(config.android.adb, online_device.serial, user)
                        active = require_active_navigation(state)
                        missing = required_navigation - set(state.available)
                        navigation_ok = navigation_ok and not missing
                        detail = (
                            f"{online_device.label}: active {active}; available "
                            f"{', '.join(state.available) or 'none'}"
                        )
                        if missing:
                            detail += f"; missing {', '.join(sorted(missing))}"
                        navigation_details.append(detail)
                    except AasgError as error:
                        navigation_ok = False
                        navigation_details.append(f"{online_device.label}: {error}")
            checks.append(
                {
                    "check": "System navigation",
                    "ok": not required_navigation or (bool(online) and navigation_ok),
                    "detail": navigation_details
                    if required_navigation
                    else "all captures ignore system navigation",
                }
            )
        except AasgError as error:
            checks.append({"check": "Android devices", "ok": False, "detail": str(error)})
        frame_requirements = {
            (step.source, step.frame)
            for pipeline in config.pipelines.values()
            for step in pipeline.steps
            if isinstance(step, DeviceFrameStep)
        }
        frame_statuses = [
            (source, frame, *frame_cache_available(config, config_path, source, frame))
            for source, frame in sorted(frame_requirements)
        ]
        checks.append(
            {
                "check": "Frame cache",
                "ok": all(status[2] for status in frame_statuses),
                "detail": [
                    f"{source}/{frame}: {'ready' if ready else detail}"
                    for source, frame, ready, detail in frame_statuses
                ]
                or f"no frames required ({cache_root()})",
            }
        )
    except Exception as error:
        checks.append({"check": "configuration", "ok": False, "detail": str(error)})

    if json_output:
        typer.echo(json.dumps(checks, indent=2))
    else:
        table = Table("Check", "Status", "Detail")
        for check in checks:
            table.add_row(
                str(check["check"]),
                "OK" if check["ok"] else "FAIL",
                str(check["detail"]),
            )
        console.print(table)
    if not all(bool(check["ok"]) for check in checks):
        raise typer.Exit(int(ExitCode.UNAVAILABLE))


@app.command()
def capture(
    capture_ids: Annotated[
        list[str] | None, typer.Argument(help="Capture IDs or group names.")
    ] = None,
    config_path: ConfigOption = Path("aasg.yaml"),
    device_serial: Annotated[str | None, typer.Option("--device")] = None,
    locales: Annotated[list[str] | None, typer.Option("--locale")] = None,
    themes: Annotated[list[str] | None, typer.Option("--theme")] = None,
    navigation_modes: Annotated[
        list[str] | None,
        typer.Option(
            "--navigation",
            help="Navigation mode for captures configured with navigation: all.",
        ),
    ] = None,
    all_captures: Annotated[bool, typer.Option("--all")] = False,
    non_interactive: Annotated[bool, typer.Option("--non-interactive")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Run configured capture variants and publish their artifacts."""
    try:
        config = load_config(config_path)
        requested_captures = list(capture_ids or [])
        requested_locales = list(locales or [])
        requested_themes = list(themes or [])
        requested_navigation = list(navigation_modes or [])
        navigation_was_explicit = bool(requested_navigation)
        previous = load_selection(config_path)
        can_reuse_previous = (
            not requested_captures
            and not all_captures
            and not requested_locales
            and not requested_themes
            and not requested_navigation
            and previous
            and not non_interactive
        )
        reuse_previous = False
        if can_reuse_previous:
            assert previous is not None
            console.print(_previous_selection_summary(previous, config), style="dim", markup=False)
            reuse_previous = typer.confirm("Use the previous capture selection?", default=True)
        if reuse_previous:
            assert previous is not None
            requested_captures = list(previous.get("captures", []))
            requested_locales = list(previous.get("locales", []))
            requested_themes = list(previous.get("themes", []))
            requested_navigation = list(previous.get("navigation", []))
            previous_device = previous.get("device")
            if device_serial is None and isinstance(previous_device, str):
                device_serial = previous_device

        if not requested_captures and not all_captures:
            if non_interactive:
                raise CaptureError("Choose captures or pass --all in non-interactive mode")
            requested_captures = _prompt_many(
                "Captures", config.captures, allow_groups=True, config=config
            )
        selected_captures = expand_capture_ids(config, requested_captures, all_captures)
        if not requested_locales:
            requested_locales = (
                ["all"] if non_interactive else _prompt_many("Locales", config.variants.locales)
            )
        if not requested_themes:
            requested_themes = (
                ["all"] if non_interactive else _prompt_many("Themes", config.variants.themes)
            )
        selected_locales = expand_variant_ids(
            requested_locales, config.variants.locales, name="locales"
        )
        selected_themes = expand_variant_ids(
            requested_themes, config.variants.themes, name="themes"
        )
        navigation_is_selectable = has_selectable_navigation(config, selected_captures)
        if navigation_is_selectable:
            if not requested_navigation:
                requested_navigation = (
                    ["all"] if non_interactive else _prompt_many("Navigation", NAVIGATION_CHOICES)
                )
            selected_navigation = expand_navigation_modes(requested_navigation)
        else:
            if navigation_was_explicit:
                raise ConfigurationError(
                    "--navigation only applies to captures configured with navigation: all"
                )
            selected_navigation = []

        if dry_run:
            device = Device(device_serial or "dry-run", "device")
        else:
            discovered = discover_devices(config.android.adb)
            device = _choose_device(discovered, device_serial, non_interactive)
            device = enrich_device(config.android.adb, device)
            if (device.api or 0) < config.android.min_api:
                raise PrerequisiteError(
                    f"{device.label} does not meet API {config.android.min_api}+"
                )
        selection = Selection(
            selected_captures,
            selected_locales,
            selected_themes,
            selected_navigation,
        )
        outcome = CaptureRunner().run(
            config=config,
            config_path=config_path,
            device=device,
            selection=selection,
            dry_run=dry_run,
            verbose=verbose,
        )
        if not dry_run and outcome.exit_code == 0:
            save_selection(
                config_path,
                {
                    "device": device.serial,
                    "captures": selection.captures,
                    "locales": selection.locales,
                    "themes": selection.themes,
                    "navigation": selection.navigation_modes,
                },
            )
        summary = {
            "run": str(outcome.run_root),
            "succeeded": outcome.succeeded,
            "failed": outcome.failed,
            "assets": outcome.manifest.get("assets", []),
        }
        if json_output:
            typer.echo(json.dumps(summary))
        else:
            console.print(
                f"Run complete: [green]{outcome.succeeded} succeeded[/green], "
                f"[red]{outcome.failed} failed[/red]\nManifest: {outcome.run_root / 'run.json'}"
            )
            assets = summary["assets"]
            if isinstance(assets, list) and assets:
                label = "Planned assets" if dry_run else "Generated assets"
                console.print(f"{label}:")
                for asset in assets:
                    console.print(f"  {asset}", markup=False)
        restoration = outcome.manifest.get("navigation", {}).get("restoration", {})
        if isinstance(restoration, dict) and restoration.get("status") == "failed":
            console.print(
                "[red]Device navigation restoration failed.[/red] "
                f"{restoration.get('manual_command', '')}"
            )
        show_taps_restoration = outcome.manifest.get("show_taps", {}).get("restoration", {})
        if (
            isinstance(show_taps_restoration, dict)
            and show_taps_restoration.get("status") == "failed"
        ):
            console.print(
                "[red]Android Show taps restoration failed.[/red] "
                f"{show_taps_restoration.get('manual_command', '')}"
            )
        if outcome.exit_code:
            raise typer.Exit(outcome.exit_code)
    except typer.Exit:
        raise
    except KeyboardInterrupt as error:
        console.print("[yellow]Interrupted[/yellow]")
        raise typer.Exit(int(ExitCode.INTERRUPTED)) from error
    except Exception as error:
        _fail(error)


@app.command("process")
def process_media(
    pipeline_id: Annotated[str, typer.Argument(help="Configured pipeline ID.")],
    source: Annotated[Path, typer.Argument(exists=True, dir_okay=False)],
    output: Annotated[Path, typer.Option("--output", "-o", dir_okay=False)],
    config_path: ConfigOption = Path("aasg.yaml"),
    metadata: Annotated[Path | None, typer.Option("--metadata", dir_okay=False)] = None,
    theme: Annotated[str | None, typer.Option("--theme")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
    json_output: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Apply a configured media pipeline to an existing file."""
    try:
        config = load_config(config_path)
        if pipeline_id not in config.pipelines:
            raise CaptureError(f"Unknown pipeline: {pipeline_id}")
        result = MediaProcessor().process(
            source,
            output,
            config.pipelines[pipeline_id],
            config=config,
            config_path=config_path,
            metadata_path=metadata,
            variables={"theme": theme} if theme else None,
            dry_run=dry_run,
        )
        payload = {"output": str(output), "commands": result.commands, "frames": result.frames}
        if json_output:
            typer.echo(json.dumps(payload, indent=2))
        else:
            for command in result.commands:
                if dry_run:
                    console.print(command, markup=False)
                else:
                    console.print(command, style="dim", markup=False)
            if not dry_run:
                console.print(f"Wrote [bold]{output}[/bold]")
    except Exception as error:
        _fail(error)


@frames_app.command("list")
def frames_list(
    source_name: Annotated[str, typer.Argument()],
    config_path: ConfigOption = Path("aasg.yaml"),
) -> None:
    """List frame IDs exposed by a remote source."""
    try:
        config = load_config(config_path)
        source = config.frame_sources.get(source_name)
        if not isinstance(source, RemoteFrameSource):
            raise CaptureError(f"Remote frame source not found: {source_name}")
        for frame_id in list_frames(source_name, source):
            typer.echo(frame_id)
    except Exception as error:
        _fail(error)


@frames_app.command("fetch")
def frames_fetch(
    source_name: Annotated[str, typer.Argument()],
    frame_id: Annotated[str, typer.Argument()],
    config_path: ConfigOption = Path("aasg.yaml"),
) -> None:
    """Fetch and cache one device frame."""
    try:
        config = load_config(config_path)
        asset = resolve_frame(config, config_path, source_name, frame_id)
        console.print(f"Cached [bold]{asset.frame_id}[/bold] at {asset.frame_path.parent}")
    except Exception as error:
        _fail(error)


@frames_app.command("refresh")
def frames_refresh(
    source_name: Annotated[str | None, typer.Argument()] = None,
    config_path: ConfigOption = Path("aasg.yaml"),
) -> None:
    """Explicitly refresh one or all remote frame indexes."""
    try:
        config = load_config(config_path)
        refreshed = 0
        for name, source in config.frame_sources.items():
            if source_name and name != source_name:
                continue
            if isinstance(source, RemoteFrameSource):
                refresh_source(name, source)
                refreshed += 1
                console.print(f"Refreshed [bold]{name}[/bold]")
        if not refreshed:
            raise CaptureError("No matching remote frame source")
    except Exception as error:
        _fail(error)


def _prompt_many(
    title: str,
    choices: Mapping[str, object],
    *,
    allow_groups: bool = False,
    config: AasgConfig | None = None,
) -> list[str]:
    options = list(choices)
    if allow_groups and config is not None:
        options.extend(config.variants.groups)
    console.print(f"[bold]{title}[/bold]")
    for index, key in enumerate(options, start=1):
        label = getattr(choices.get(key), "label", choices.get(key, key))
        console.print(f"  {index}) {key} — {label}")
    response = typer.prompt("Choose comma-separated numbers or 'all'", default="all")
    if response.strip().lower() == "all":
        return list(choices)
    try:
        indexes = [int(value.strip()) - 1 for value in response.split(",")]
        selected = [options[index] for index in indexes if 0 <= index < len(options)]
    except (ValueError, IndexError) as error:
        raise CaptureError(f"Invalid {title.lower()} selection") from error
    if not selected or len(selected) != len(indexes):
        raise CaptureError(f"Invalid {title.lower()} selection")
    return selected


def _choose_device(devices: list[Device], requested: str | None, non_interactive: bool) -> Device:
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
    if non_interactive:
        raise PrerequisiteError("More than one device is online; pass --device")
    console.print("[bold]Devices[/bold]")
    for index, device in enumerate(online, start=1):
        console.print(f"  {index}) {device.label}")
    choice = int(typer.prompt("Choose a device", type=int))
    if choice < 1 or choice > len(online):
        raise PrerequisiteError("Invalid device selection")
    return online[choice - 1]


if __name__ == "__main__":
    app()
