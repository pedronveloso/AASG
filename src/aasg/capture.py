"""Capture matrix orchestration."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from aasg.android import (
    CommandResult,
    Device,
    NavigationController,
    ShowTapsController,
    active_user,
    adb_shell_command,
    capture_logcat,
    gradle_command,
    instrumentation_command,
    instrumentation_succeeded,
    redact_error,
    redact_serial,
    run_supervised,
)
from aasg.artifacts import (
    find_fresh_output,
    fingerprint_tree,
    publish_atomically,
    sha256,
    stage_copy,
)
from aasg.config import project_path, render_template, resolve_inside
from aasg.errors import AasgError, CaptureError, ConfigurationError, ExitCode, PrerequisiteError
from aasg.media import MediaProcessor, probe
from aasg.models import AasgConfig, ArtifactConfig, CaptureConfig, NavigationMode


@dataclass(frozen=True)
class Selection:
    captures: list[str]
    locales: list[str]
    themes: list[str]
    navigation_modes: list[NavigationMode] = field(default_factory=list)


@dataclass(frozen=True)
class CaptureOutcome:
    run_root: Path
    succeeded: int
    failed: int
    exit_code: int
    manifest: dict[str, Any]


def published_asset_paths(manifest: dict[str, Any], project_root: Path) -> list[str]:
    paths: list[str] = []
    for variant in manifest.get("variants", []):
        if variant.get("status") != "succeeded":
            continue
        for artifact in variant.get("artifacts", []):
            publications = [artifact.get("publish")]
            publications.extend(
                rendition.get("publish") for rendition in artifact.get("renditions", [])
            )
            for publication in publications:
                if not isinstance(publication, str):
                    continue
                path = Path(publication).resolve().relative_to(project_root.resolve())
                relative = path.as_posix()
                if relative not in paths:
                    paths.append(relative)
    return paths


def expand_capture_ids(config: AasgConfig, requested: list[str], all_captures: bool) -> list[str]:
    if all_captures:
        return list(config.captures)
    expanded: list[str] = []
    for item in requested:
        values = config.variants.groups.get(item, [item])
        for value in values:
            if value not in config.captures:
                raise CaptureError(f"Unknown capture or group: {item}")
            if value not in expanded:
                expanded.append(value)
    return expanded


def expand_variant_ids(requested: list[str], available: dict[str, str], *, name: str) -> list[str]:
    if not requested or requested == ["all"]:
        return list(available)
    unknown = set(requested) - available.keys()
    if unknown:
        raise CaptureError(f"Unknown {name}: {', '.join(sorted(unknown))}")
    return list(dict.fromkeys(requested))


def expand_navigation_modes(requested: list[str]) -> list[NavigationMode]:
    available = {"gestural": "Gesture navigation", "three-button": "Three-button navigation"}
    if not requested or requested == ["all"]:
        return ["gestural", "three-button"]
    unknown = set(requested) - available.keys()
    if unknown:
        raise ConfigurationError(f"Unknown navigation mode: {', '.join(sorted(unknown))}")
    return [cast(NavigationMode, mode) for mode in dict.fromkeys(requested)]


def has_selectable_navigation(config: AasgConfig, capture_ids: list[str]) -> bool:
    return any(config.captures[capture_id].navigation == "all" for capture_id in capture_ids)


def required_navigation_modes(config: AasgConfig, selection: Selection) -> set[NavigationMode]:
    required: set[NavigationMode] = set()
    for capture_id in selection.captures:
        policy = config.captures[capture_id].navigation
        if policy == "all":
            if not selection.navigation_modes:
                raise CaptureError(
                    f"Capture {capture_id!r} requires at least one selected navigation mode"
                )
            required.update(selection.navigation_modes)
        elif policy == "gestural":
            required.add("gestural")
        elif policy == "three-button":
            required.add("three-button")
    return required


def capture_navigation_modes(
    capture: CaptureConfig, selection: Selection
) -> list[NavigationMode | None]:
    if capture.navigation == "all":
        return list(selection.navigation_modes)
    if capture.navigation == "gestural":
        return ["gestural"]
    if capture.navigation == "three-button":
        return ["three-button"]
    return [None]


def is_video_capture(capture: CaptureConfig) -> bool:
    return any(artifact.type == "video" for artifact in capture.artifacts)


def required_show_taps_values(config: AasgConfig, selection: Selection) -> set[bool]:
    return {
        capture.show_taps
        for capture_id in selection.captures
        if is_video_capture(capture := config.captures[capture_id])
    }


class CaptureRunner:
    def __init__(self, processor: MediaProcessor | None = None) -> None:
        self.processor = processor or MediaProcessor()

    def run(
        self,
        *,
        config: AasgConfig,
        config_path: Path,
        device: Device,
        selection: Selection,
        dry_run: bool = False,
        verbose: bool = False,
    ) -> CaptureOutcome:
        project_root = config_path.resolve().parent
        artifact_root = project_path(config_path, config.project.artifact_root)
        run_log_root = project_path(config_path, config.project.run_log_root)
        run_id = f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid.uuid4().hex[:8]}"
        run_root = run_log_root / run_id
        run_root.mkdir(parents=True, exist_ok=True)
        additional_output = project_path(config_path, config.android.additional_output_dir)
        manifest: dict[str, Any] = {
            "schema": 3,
            "run_id": run_id,
            "started_at": datetime.now(UTC).isoformat(),
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "device": {
                "serial": redact_serial(device.serial),
                "model": device.model,
                "product": device.product,
                "api": device.api,
            },
            "selection": {
                "captures": selection.captures,
                "locales": selection.locales,
                "themes": selection.themes,
                "navigation": selection.navigation_modes,
            },
            "variants": [],
        }
        succeeded = 0
        failed = 0
        env = {"ANDROID_SERIAL": device.serial}
        required_modes = required_navigation_modes(config, selection)
        required_show_taps = required_show_taps_values(config, selection)
        navigation: NavigationController | None = None
        navigation_manifest: dict[str, Any]
        if required_modes and dry_run:
            navigation_manifest = {
                "status": "planned",
                "required": sorted(required_modes),
                "restoration": {"status": "planned"},
                "events": [],
            }
        elif required_modes:
            try:
                user = active_user(config.android.adb, device.serial)
                navigation = NavigationController.inspect(
                    adb=config.android.adb,
                    serial=device.serial,
                    user=user,
                    cwd=project_root,
                    log_path=run_root / "commands" / "navigation.log",
                    verbose=verbose,
                )
                navigation.require_modes(required_modes)
                navigation_manifest = {
                    "status": "managed",
                    "available": list(navigation.available),
                    "original": navigation.original_mode,
                    "required": sorted(required_modes),
                    "events": navigation.events,
                    "restoration": {"status": "pending"},
                }
            except Exception as error:
                code = self._error_code(error)
                navigation_manifest = {
                    "status": "failed",
                    "required": sorted(required_modes),
                    "error": redact_error(error, device.serial),
                    "events": [],
                    "restoration": {"status": "not-needed"},
                }
                manifest["navigation"] = navigation_manifest
                manifest["show_taps"] = {
                    "status": "not-started" if required_show_taps else "ignored",
                    "required": sorted(required_show_taps),
                    "events": [],
                    "restoration": {"status": "not-needed"},
                }
                manifest["completed_at"] = datetime.now(UTC).isoformat()
                manifest["assets"] = []
                manifest["result"] = {"succeeded": 0, "failed": 1, "exit_code": code}
                self._write_manifest(run_root, manifest)
                return CaptureOutcome(run_root, 0, 1, code, manifest)
        else:
            navigation_manifest = {
                "status": "ignored",
                "required": [],
                "events": [],
                "restoration": {"status": "not-needed"},
            }
        manifest["navigation"] = navigation_manifest

        show_taps: ShowTapsController | None = None
        show_taps_manifest: dict[str, Any]
        if required_show_taps and dry_run:
            show_taps_manifest = {
                "status": "planned",
                "required": sorted(required_show_taps),
                "events": [],
                "restoration": {"status": "planned"},
            }
        elif required_show_taps:
            try:
                user = (
                    navigation.user
                    if navigation is not None
                    else active_user(config.android.adb, device.serial)
                )
                show_taps = ShowTapsController.inspect(
                    adb=config.android.adb,
                    serial=device.serial,
                    user=user,
                    cwd=project_root,
                    log_path=run_root / "commands" / "show-taps.log",
                    verbose=verbose,
                )
                show_taps_manifest = {
                    "status": "managed",
                    "required": sorted(required_show_taps),
                    "original": {
                        "present": show_taps.original_state.present,
                        "value": show_taps.original_state.value,
                    },
                    "events": show_taps.events,
                    "restoration": {"status": "pending"},
                }
            except Exception as error:
                code = self._error_code(error)
                show_taps_manifest = {
                    "status": "failed",
                    "required": sorted(required_show_taps),
                    "error": redact_error(error, device.serial),
                    "events": [],
                    "restoration": {"status": "not-needed"},
                }
                if navigation is not None:
                    navigation_manifest["restoration"] = {"status": "unchanged"}
                manifest["show_taps"] = show_taps_manifest
                manifest["completed_at"] = datetime.now(UTC).isoformat()
                manifest["assets"] = []
                manifest["result"] = {"succeeded": 0, "failed": 1, "exit_code": code}
                self._write_manifest(run_root, manifest)
                return CaptureOutcome(run_root, 0, 1, code, manifest)
        else:
            show_taps_manifest = {
                "status": "ignored",
                "required": [],
                "events": [],
                "restoration": {"status": "not-needed"},
            }
        manifest["show_taps"] = show_taps_manifest

        if config.android.prepare_tasks:
            command = [config.android.gradle_wrapper, *config.android.prepare_tasks]
            manifest["prepare_command"] = command
            if not dry_run:
                try:
                    result = run_supervised(
                        command,
                        cwd=project_root,
                        timeout_seconds=max(config.project.default_timeout_seconds, 300),
                        log_path=run_root / "prepare.log",
                        env=env,
                        serial=device.serial,
                        on_line=print if verbose else None,
                    )
                    manifest["prepare_duration_seconds"] = result.duration_seconds
                    if result.returncode:
                        raise CaptureError("Gradle preparation failed; see prepare.log")
                except Exception as error:
                    code = self._error_code(error)
                    manifest["prepare_error"] = redact_error(error, device.serial)
                    if navigation is not None:
                        navigation_manifest["restoration"] = {"status": "unchanged"}
                    if show_taps is not None:
                        show_taps_manifest["restoration"] = {"status": "unchanged"}
                    manifest["completed_at"] = datetime.now(UTC).isoformat()
                    manifest["assets"] = []
                    manifest["result"] = {"succeeded": 0, "failed": 1, "exit_code": code}
                    self._write_manifest(run_root, manifest)
                    return CaptureOutcome(run_root, 0, 1, code, manifest)

        interruption: KeyboardInterrupt | None = None
        restoration_error: Exception | None = None
        try:
            for capture_id in selection.captures:
                capture = config.captures[capture_id]
                locales = self._restricted(selection.locales, capture.locales)
                themes = self._restricted(selection.themes, capture.themes)
                for navigation_mode in capture_navigation_modes(capture, selection):
                    for locale in locales:
                        for theme in themes:
                            variant = self._run_variant(
                                config=config,
                                config_path=config_path,
                                artifact_root=artifact_root,
                                additional_output=additional_output,
                                run_root=run_root,
                                device=device,
                                capture_id=capture_id,
                                capture=capture,
                                locale=locale,
                                theme=theme,
                                navigation_mode=navigation_mode,
                                navigation=navigation,
                                show_taps=show_taps,
                                dry_run=dry_run,
                                verbose=verbose,
                            )
                            manifest["variants"].append(variant)
                            if variant["status"] == "succeeded":
                                succeeded += 1
                            else:
                                failed += 1
        except KeyboardInterrupt as error:
            interruption = error
        finally:
            if navigation is not None:
                try:
                    navigation_manifest["restoration"] = navigation.restore()
                except Exception as error:
                    restoration_error = error
                    navigation_manifest["restoration"] = {
                        "status": "failed",
                        "error": redact_error(error, device.serial),
                        "manual_command": navigation.manual_restore_guidance(),
                    }
                navigation_manifest["events"] = navigation.events
            if show_taps is not None:
                try:
                    show_taps_manifest["restoration"] = show_taps.restore()
                except Exception as error:
                    restoration_error = restoration_error or error
                    show_taps_manifest["restoration"] = {
                        "status": "failed",
                        "error": redact_error(error, device.serial),
                        "manual_command": show_taps.manual_restore_guidance(),
                    }
                show_taps_manifest["events"] = show_taps.events

        exit_code = max(
            (int(variant.get("exit_code", 0)) for variant in manifest["variants"]),
            default=0,
        )
        if interruption is not None:
            exit_code = int(ExitCode.INTERRUPTED)
            manifest["interrupted"] = True
        elif restoration_error is not None and exit_code == 0:
            exit_code = int(ExitCode.UNAVAILABLE)
        manifest["completed_at"] = datetime.now(UTC).isoformat()
        manifest["assets"] = published_asset_paths(manifest, project_root)
        manifest["result"] = {
            "succeeded": succeeded,
            "failed": failed,
            "exit_code": exit_code,
        }
        self._write_manifest(run_root, manifest)
        if interruption is not None:
            raise interruption
        return CaptureOutcome(run_root, succeeded, failed, exit_code, manifest)

    def _run_variant(
        self,
        *,
        config: AasgConfig,
        config_path: Path,
        artifact_root: Path,
        additional_output: Path,
        run_root: Path,
        device: Device,
        capture_id: str,
        capture: CaptureConfig,
        locale: str,
        theme: str,
        navigation_mode: NavigationMode | None,
        navigation: NavigationController | None,
        show_taps: ShowTapsController | None,
        dry_run: bool,
        verbose: bool,
    ) -> dict[str, Any]:
        navigation_id = navigation_mode or "ignore"
        name = f"{capture_id}-{navigation_id}-{locale}-{theme}"
        variant: dict[str, Any] = {
            "capture": capture_id,
            "locale": locale,
            "theme": theme,
            "navigation_policy": capture.navigation,
            "navigation": navigation_id,
            "effective_navigation": navigation.current_mode if navigation is not None else None,
            "show_taps": capture.show_taps if is_video_capture(capture) else None,
            "effective_show_taps": None,
            "status": "failed",
            "artifacts": [],
        }
        command = gradle_command(config.android, capture, locale, theme)
        direct = config.android.direct_instrumentation
        variant["command"] = (
            "direct ADB instrumentation (active user resolved at runtime)" if direct else command
        )
        before = fingerprint_tree(additional_output)
        try:
            if navigation_mode is not None:
                if navigation is not None:
                    variant["navigation_event"] = navigation.ensure(navigation_mode)
                    variant["effective_navigation"] = navigation.current_mode
                elif dry_run:
                    variant["effective_navigation"] = navigation_mode
                else:
                    raise PrerequisiteError("Android navigation control was not initialized")
            recording = is_video_capture(capture)
            if recording and dry_run:
                variant["effective_show_taps"] = capture.show_taps
            if not dry_run:
                command_error: Exception | None = None
                interruption: KeyboardInterrupt | None = None
                show_taps_restoration_error: Exception | None = None
                try:
                    if recording:
                        if show_taps is None:
                            raise PrerequisiteError("Android Show taps control was not initialized")
                        variant["show_taps_event"] = show_taps.ensure(capture.show_taps)
                        variant["effective_show_taps"] = show_taps.current_state.effective
                    if direct:
                        result, commands = self._run_direct_instrumentation(
                            config=config,
                            config_path=config_path,
                            additional_output=additional_output,
                            device=device,
                            capture=capture,
                            locale=locale,
                            theme=theme,
                            log_path=run_root / "commands" / f"{name}.log",
                            timeout_seconds=capture.timeout_seconds
                            or config.project.default_timeout_seconds,
                            verbose=verbose,
                        )
                        variant["commands"] = commands
                    else:
                        result = run_supervised(
                            command,
                            cwd=config_path.resolve().parent,
                            timeout_seconds=capture.timeout_seconds
                            or config.project.default_timeout_seconds,
                            log_path=run_root / "commands" / f"{name}.log",
                            env={"ANDROID_SERIAL": device.serial},
                            serial=device.serial,
                            on_line=print if verbose else None,
                        )
                    variant["duration_seconds"] = result.duration_seconds
                    if result.returncode:
                        capture_logcat(
                            config.android.adb,
                            device.serial,
                            run_root / "commands" / f"{name}-logcat.log",
                        )
                        raise CaptureError(f"Instrumentation returned {result.returncode}")
                except KeyboardInterrupt as error:
                    interruption = error
                except Exception as error:
                    command_error = error
                finally:
                    if recording and show_taps is not None:
                        try:
                            variant["show_taps_restoration"] = show_taps.restore()
                        except Exception as error:
                            show_taps_restoration_error = error
                            variant["show_taps_restoration"] = {
                                "status": "failed",
                                "error": redact_error(error, device.serial),
                                "manual_command": show_taps.manual_restore_guidance(),
                            }
                if interruption is not None:
                    raise interruption
                if command_error is not None:
                    if show_taps_restoration_error is not None:
                        variant["show_taps_restoration_error"] = redact_error(
                            show_taps_restoration_error, device.serial
                        )
                    raise command_error
                if show_taps_restoration_error is not None:
                    raise show_taps_restoration_error
            staged, publications = self._collect_variant(
                config,
                config_path,
                artifact_root,
                additional_output,
                run_root,
                capture_id,
                capture,
                locale,
                theme,
                navigation_id,
                before,
                dry_run,
            )
            variant["artifacts"] = staged
            if not dry_run:
                for source, destination in publications:
                    publish_atomically(source, destination)
            variant["status"] = "succeeded"
        except Exception as error:  # continue the requested capture matrix
            variant["error"] = redact_error(error, device.serial)
            variant["exit_code"] = self._error_code(error)
        return variant

    @staticmethod
    def _run_direct_instrumentation(
        *,
        config: AasgConfig,
        config_path: Path,
        additional_output: Path,
        device: Device,
        capture: CaptureConfig,
        locale: str,
        theme: str,
        log_path: Path,
        timeout_seconds: int,
        verbose: bool,
    ) -> tuple[CommandResult, list[list[str]]]:
        direct = config.android.direct_instrumentation
        if direct is None:
            raise ValueError("direct_instrumentation is not configured")
        project_root = config_path.resolve().parent
        user = active_user(config.android.adb, device.serial)
        app_apk = project_path(config_path, direct.app_apk)
        test_apk = project_path(config_path, direct.test_apk)
        for apk in (app_apk, test_apk):
            if not apk.is_file():
                raise CaptureError(f"Prepared APK was not found: {apk}")
        additional_output.mkdir(parents=True, exist_ok=True)
        commands = [
            [
                config.android.adb,
                "-s",
                device.serial,
                "install",
                "-r",
                "-t",
                "--user",
                str(user),
                str(app_apk),
            ],
            [
                config.android.adb,
                "-s",
                device.serial,
                "install",
                "-r",
                "-t",
                "-g",
                "--user",
                str(user),
                str(test_apk),
            ],
            adb_shell_command(
                config.android.adb,
                device.serial,
                ["rm", "-rf", direct.device_output_dir],
            ),
            adb_shell_command(
                config.android.adb,
                device.serial,
                ["mkdir", "-p", direct.device_output_dir],
            ),
            instrumentation_command(
                config.android,
                capture,
                locale,
                theme,
                serial=device.serial,
                user=user,
            ),
        ]
        last_result = CommandResult(0, 0.0)
        total_duration = 0.0
        for index, command in enumerate(commands):
            last_result = run_supervised(
                command,
                cwd=project_root,
                timeout_seconds=timeout_seconds,
                log_path=log_path,
                serial=device.serial,
                on_line=print if verbose else None,
                append=index > 0,
            )
            total_duration += last_result.duration_seconds
            if last_result.returncode:
                raise CaptureError(f"Android command returned {last_result.returncode}")
        if not instrumentation_succeeded(last_result):
            raise CaptureError("Instrumentation did not report a successful test run")
        pull_command = [
            config.android.adb,
            "-s",
            device.serial,
            "pull",
            f"{direct.device_output_dir}/.",
            str(additional_output),
        ]
        commands.append(pull_command)
        pull_result = run_supervised(
            pull_command,
            cwd=project_root,
            timeout_seconds=timeout_seconds,
            log_path=log_path,
            serial=device.serial,
            on_line=print if verbose else None,
            append=True,
        )
        total_duration += pull_result.duration_seconds
        if pull_result.returncode:
            raise CaptureError(f"Test Storage collection returned {pull_result.returncode}")
        return CommandResult(0, total_duration, last_result.output), commands

    def _collect_variant(
        self,
        config: AasgConfig,
        config_path: Path,
        artifact_root: Path,
        additional_output: Path,
        run_root: Path,
        capture_id: str,
        capture: CaptureConfig,
        locale: str,
        theme: str,
        navigation: str,
        before: dict[str, tuple[int, int]],
        dry_run: bool,
    ) -> tuple[list[dict[str, Any]], list[tuple[Path, Path]]]:
        staged_records: list[dict[str, Any]] = []
        publications: list[tuple[Path, Path]] = []
        values = {
            "capture": capture_id,
            "locale": locale,
            "theme": theme,
            "navigation": navigation,
        }
        staging_root = run_root / "staging" / capture_id / navigation / locale / theme
        for artifact in capture.artifacts:
            artifact_values = {**values, "artifact": artifact.id, "stem": artifact.id}
            source_suffix = render_template(artifact.source, **artifact_values)
            publish_relative = render_template(artifact.publish, **artifact_values)
            destination = resolve_inside(artifact_root, publish_relative)
            if dry_run:
                planned_renditions = []
                for rendition in artifact.renditions:
                    rendition_relative = render_template(rendition.publish, **artifact_values)
                    planned_renditions.append(
                        {
                            "pipeline": rendition.pipeline,
                            "publish": str(resolve_inside(artifact_root, rendition_relative)),
                            "status": "planned",
                        }
                    )
                staged_records.append(
                    {
                        "id": artifact.id,
                        "source": source_suffix,
                        "publish": str(destination),
                        "status": "planned",
                        "renditions": planned_renditions,
                    }
                )
                continue
            source = find_fresh_output(additional_output, source_suffix, before)
            staged_source = staging_root / "raw" / source.name
            stage_copy(source, staged_source)
            self._validate(staged_source, artifact)
            metadata_path = self._stage_metadata(
                artifact,
                artifact_values,
                additional_output,
                before,
                staging_root,
            )
            record: dict[str, Any] = {
                "id": artifact.id,
                "source": str(source),
                "publish": str(destination),
                "sha256": sha256(staged_source),
                "renditions": [],
            }
            publications.append((staged_source, destination))
            for rendition_index, rendition in enumerate(artifact.renditions):
                rendition_relative = render_template(rendition.publish, **artifact_values)
                rendition_destination = resolve_inside(artifact_root, rendition_relative)
                staged_rendition = (
                    staging_root
                    / "renditions"
                    / (f"{rendition_index:02d}-{rendition_destination.name}")
                )
                result = self.processor.process(
                    staged_source,
                    staged_rendition,
                    config.pipelines[rendition.pipeline],
                    config=config,
                    config_path=config_path,
                    metadata_path=metadata_path,
                    variables=values,
                )
                record["renditions"].append(
                    {
                        "pipeline": rendition.pipeline,
                        "publish": str(rendition_destination),
                        "sha256": sha256(staged_rendition),
                        "commands": result.commands,
                        "frames": result.frames,
                    }
                )
                publications.append((staged_rendition, rendition_destination))
            staged_records.append(record)
        return staged_records, publications

    @staticmethod
    def _stage_metadata(
        artifact: ArtifactConfig,
        values: dict[str, str],
        additional_output: Path,
        before: dict[str, tuple[int, int]],
        staging_root: Path,
    ) -> Path | None:
        if not artifact.metadata:
            return None
        suffix = render_template(artifact.metadata, **values)
        source = find_fresh_output(additional_output, suffix, before)
        destination = staging_root / "metadata" / source.name
        stage_copy(source, destination)
        return destination

    def _validate(self, path: Path, artifact: ArtifactConfig) -> None:
        if artifact.type in {"image", "video"}:
            info = probe(path, self.processor.ffprobe)
            if info.kind != artifact.type:
                raise CaptureError(
                    f"Expected {artifact.type} for {artifact.id}, detected {info.kind}"
                )
        elif artifact.type == "json":
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                raise CaptureError(f"Invalid JSON artifact: {path}") from error

    @staticmethod
    def _restricted(selected: list[str], allowed: list[str] | None) -> list[str]:
        return [value for value in selected if allowed is None or value in allowed]

    @staticmethod
    def _error_code(error: Exception) -> int:
        if isinstance(error, AasgError):
            return int(error.exit_code)
        return int(ExitCode.PROCESSING_FAILED)

    @staticmethod
    def _write_manifest(run_root: Path, manifest: dict[str, Any]) -> None:
        (run_root / "run.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
