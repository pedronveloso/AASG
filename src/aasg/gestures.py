"""Deterministic gesture-overlay rasterization for video pipelines."""

from __future__ import annotations

import math
import shlex
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterable, Iterator, Sequence
from itertools import pairwise
from pathlib import Path
from typing import cast

from PIL import Image, ImageColor, ImageDraw

from aasg.errors import PrerequisiteError, ProcessingError
from aasg.models import (
    DragGesture,
    GestureEvent,
    GestureOverlayStep,
    GesturePoint,
    SemanticMetadata,
    SwipeGesture,
    TapGesture,
    TimedGesturePoint,
)

Color = tuple[int, int, int, int]
Position = tuple[float, float]

TAP_RELEASE_MS = 480
GESTURE_RELEASE_MS = 200
GESTURE_OVERLAY_TIMEOUT_SECONDS = 300
GESTURE_WRITER_JOIN_TIMEOUT_SECONDS = 5


def gesture_overlay_command(
    ffmpeg: str,
    source: Path,
    output: Path,
    *,
    width: int,
    height: int,
    duration: float,
    frame_rate: int,
) -> list[str]:
    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgba",
        "-video_size",
        f"{width}x{height}",
        "-framerate",
        str(frame_rate),
        "-i",
        "pipe:0",
        "-filter_complex",
        f"[0:v]fps={frame_rate},setpts=PTS-STARTPTS[base];"
        "[1:v]setpts=PTS-STARTPTS[gestures];"
        "[base][gestures]overlay=0:0:format=auto:shortest=1[out]",
        "-map",
        "[out]",
        "-t",
        f"{duration:.6f}",
        "-an",
        "-c:v",
        "ffv1",
        "-pix_fmt",
        "bgra",
        str(output),
    ]


def validate_gesture_metadata(
    metadata: SemanticMetadata | None,
    step: GestureOverlayStep,
    *,
    width: int,
    height: int,
    duration: float | None,
) -> SemanticMetadata:
    if metadata is None:
        raise ProcessingError("gesture_overlay requires semantic metadata")
    if metadata.schema_version != 2 or metadata.coordinate_space is None:
        raise ProcessingError("gesture_overlay requires semantic metadata schema 2")
    if duration is None:
        raise ProcessingError("gesture_overlay requires a video with a known duration")
    space = metadata.coordinate_space
    if (space.width, space.height) != (width, height):
        raise ProcessingError(
            "gesture coordinate_space does not match the source video dimensions: "
            f"{space.width}x{space.height} != {width}x{height}"
        )
    duration_ms = round(duration * 1000)
    for event in metadata.gestures:
        for point in _event_points(event):
            if point.x >= width or point.y >= height:
                raise ProcessingError(
                    f"gesture point ({point.x}, {point.y}) exceeds {width}x{height}"
                )
        start_ms = event.at_ms + step.timing_offset_ms
        end_ms = start_ms + gesture_duration_ms(event)
        if start_ms < 0 or end_ms > duration_ms:
            raise ProcessingError(
                f"gesture at {event.at_ms}ms falls outside the {duration_ms}ms video "
                f"after timing_offset_ms={step.timing_offset_ms}"
            )
    return metadata


def gesture_duration_ms(event: GestureEvent) -> int:
    if isinstance(event, TapGesture):
        return event.cue_lead_ms + TAP_RELEASE_MS
    if isinstance(event, SwipeGesture):
        return event.cue_lead_ms + event.duration_ms + GESTURE_RELEASE_MS
    return event.cue_lead_ms + event.points[-1].offset_ms + GESTURE_RELEASE_MS


def render_gesture_frame(
    metadata: SemanticMetadata,
    step: GestureOverlayStep,
    *,
    width: int,
    height: int,
    time_ms: float,
) -> Image.Image:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    primary = cast(Color, ImageColor.getcolor(step.color, "RGBA"))
    halo = cast(Color, ImageColor.getcolor(step.halo_color, "RGBA"))
    for event in metadata.gestures:
        local_ms = time_ms - (event.at_ms + step.timing_offset_ms)
        if local_ms < 0 or local_ms > gesture_duration_ms(event):
            continue
        if isinstance(event, TapGesture):
            _draw_tap(image, event, local_ms, step, primary, halo)
        elif isinstance(event, SwipeGesture):
            _draw_swipe(image, event, local_ms, step, primary, halo)
        else:
            _draw_drag(image, event, local_ms, step, primary, halo)
    return image


def gesture_frames(
    metadata: SemanticMetadata,
    step: GestureOverlayStep,
    *,
    width: int,
    height: int,
    duration: float,
    frame_rate: int,
) -> Iterator[bytes]:
    frame_count = math.ceil(duration * frame_rate)
    for frame_index in range(frame_count):
        image = render_gesture_frame(
            metadata,
            step,
            width=width,
            height=height,
            time_ms=frame_index * 1000 / frame_rate,
        )
        yield image.tobytes("raw", "RGBA")


def execute_gesture_overlay(command: list[str], frames: Iterable[bytes]) -> None:
    with tempfile.TemporaryFile() as error_stream:
        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=error_stream,
            )
        except FileNotFoundError as error:
            raise PrerequisiteError(f"Executable not found: {command[0]}") from error
        stdin = process.stdin
        assert stdin is not None
        started = time.monotonic()
        write_error: BrokenPipeError | None = None
        producer_error: Exception | None = None

        def write_frames() -> None:
            nonlocal write_error, producer_error
            try:
                for frame in frames:
                    stdin.write(frame)
            except BrokenPipeError as error:
                write_error = error
            except Exception as error:
                producer_error = error
            finally:
                try:
                    stdin.close()
                except BrokenPipeError as error:
                    if write_error is None:
                        write_error = error

        writer = threading.Thread(target=write_frames, daemon=True)
        writer.start()
        try:
            remaining = GESTURE_OVERLAY_TIMEOUT_SECONDS - (time.monotonic() - started)
            return_code = process.wait(timeout=max(0, remaining))
        except subprocess.TimeoutExpired as error:
            process.kill()
            process.wait()
            writer.join(timeout=GESTURE_WRITER_JOIN_TIMEOUT_SECONDS)
            raise ProcessingError(f"Media command timed out: {shlex.join(command)}") from error
        writer.join(timeout=GESTURE_WRITER_JOIN_TIMEOUT_SECONDS)
        if writer.is_alive():
            raise ProcessingError(f"Media command frame writer did not stop: {shlex.join(command)}")
        if producer_error is not None:
            raise producer_error
        error_stream.seek(0)
        stderr = error_stream.read().decode("utf-8", errors="replace").strip()
        if return_code or write_error is not None:
            detail = f": {stderr}" if stderr else ""
            raise ProcessingError(f"Media command failed: {shlex.join(command)}{detail}")


def _draw_tap(
    image: Image.Image,
    event: TapGesture,
    local_ms: float,
    step: GestureOverlayStep,
    primary: Color,
    halo: Color,
) -> None:
    center = (float(event.x), float(event.y))
    radius = float(step.radius_px)
    if step.motion == "reduced":
        alpha = _fade_after(local_ms, event.cue_lead_ms + 220, 180)
        _circle(image, center, radius * 0.34, primary, halo, alpha)
        return
    if local_ms < event.cue_lead_ms:
        lead_progress = local_ms / max(1, event.cue_lead_ms)
        _circle(image, center, radius * 0.34, primary, halo, min(1.0, lead_progress * 3))
        return
    action_ms = local_ms - event.cue_lead_ms
    press_progress = min(1.0, action_ms / 120)
    dot_radius = radius * 0.34 * (1 - 0.14 * _ease_out_quart(press_progress))
    dot_alpha = _fade_after(action_ms, 300, 180)
    _circle(image, center, dot_radius, primary, halo, dot_alpha)
    ring_progress = min(1.0, action_ms / TAP_RELEASE_MS)
    if ring_progress > 0:
        ring_radius = radius * (0.34 + 0.66 * _ease_out_quart(ring_progress))
        _ring(image, center, ring_radius, primary, halo, 1 - ring_progress)


def _draw_swipe(
    image: Image.Image,
    event: SwipeGesture,
    local_ms: float,
    step: GestureOverlayStep,
    primary: Color,
    halo: Color,
) -> None:
    start = _position(event.from_)
    end = _position(event.to)
    alpha = _gesture_alpha(local_ms, event.cue_lead_ms, event.duration_ms)
    if step.motion == "reduced":
        _static_path(image, [start, end], step, primary, halo, alpha)
        return
    progress = _motion_progress(local_ms, event.cue_lead_ms, event.duration_ms, eased=True)
    current = _lerp(start, end, progress)
    if step.trail:
        for index in range(4, 0, -1):
            trail_progress = max(0.0, progress - index * 0.075)
            trail = _lerp(start, end, trail_progress)
            _circle(
                image,
                trail,
                step.radius_px * 0.23 * (1 - index * 0.1),
                primary,
                halo,
                alpha * 0.45 * (1 - index / 5),
            )
    _circle(image, current, step.radius_px * 0.27, primary, halo, alpha)


def _draw_drag(
    image: Image.Image,
    event: DragGesture,
    local_ms: float,
    step: GestureOverlayStep,
    primary: Color,
    halo: Color,
) -> None:
    duration_ms = event.points[-1].offset_ms
    alpha = _gesture_alpha(local_ms, event.cue_lead_ms, duration_ms)
    all_positions = [_position(point) for point in event.points]
    if step.motion == "reduced":
        _static_path(image, all_positions, step, primary, halo, alpha)
        return
    movement_ms = max(0.0, min(duration_ms, local_ms - event.cue_lead_ms))
    completed, current = _drag_path(event.points, movement_ms)
    if step.trail and len(completed) > 1:
        draw = ImageDraw.Draw(image, "RGBA")
        halo_width = max(5, round(step.radius_px * 0.18))
        line_width = max(2, round(step.radius_px * 0.08))
        draw.line(completed, fill=_alpha(halo, alpha * 0.45), width=halo_width, joint="curve")
        draw.line(completed, fill=_alpha(primary, alpha * 0.55), width=line_width, joint="curve")
    _circle(image, current, step.radius_px * 0.27, primary, halo, alpha)


def _static_path(
    image: Image.Image,
    positions: Sequence[Position],
    step: GestureOverlayStep,
    primary: Color,
    halo: Color,
    alpha: float,
) -> None:
    draw = ImageDraw.Draw(image, "RGBA")
    if step.trail:
        halo_width = max(6, round(step.radius_px * 0.2))
        line_width = max(3, round(step.radius_px * 0.09))
        draw.line(positions, fill=_alpha(halo, alpha * 0.65), width=halo_width, joint="curve")
        draw.line(positions, fill=_alpha(primary, alpha * 0.85), width=line_width, joint="curve")
    endpoint_radius = step.radius_px * 0.2
    _circle(image, positions[0], endpoint_radius, primary, halo, alpha)
    _ring(image, positions[-1], step.radius_px * 0.3, primary, halo, alpha * 0.9)


def _circle(
    image: Image.Image,
    center: Position,
    radius: float,
    primary: Color,
    halo: Color,
    alpha: float,
) -> None:
    if alpha <= 0:
        return
    draw = ImageDraw.Draw(image, "RGBA")
    halo_radius = radius + max(3, radius * 0.22)
    draw.ellipse(_bounds(center, halo_radius), fill=_alpha(halo, alpha))
    draw.ellipse(_bounds(center, radius), fill=_alpha(primary, alpha))


def _ring(
    image: Image.Image,
    center: Position,
    radius: float,
    primary: Color,
    halo: Color,
    alpha: float,
) -> None:
    if alpha <= 0:
        return
    draw = ImageDraw.Draw(image, "RGBA")
    line_width = max(2, round(radius * 0.1))
    draw.ellipse(
        _bounds(center, radius),
        outline=_alpha(halo, alpha),
        width=line_width + max(2, line_width // 2),
    )
    draw.ellipse(
        _bounds(center, radius),
        outline=_alpha(primary, alpha),
        width=line_width,
    )


def _drag_path(
    points: Sequence[TimedGesturePoint], elapsed_ms: float
) -> tuple[list[Position], Position]:
    completed: list[Position] = [_position(points[0])]
    for first, second in pairwise(points):
        if elapsed_ms >= second.offset_ms:
            completed.append(_position(second))
            continue
        span = second.offset_ms - first.offset_ms
        progress = (elapsed_ms - first.offset_ms) / span
        current = _lerp(_position(first), _position(second), max(0.0, min(1.0, progress)))
        completed.append(current)
        return completed, current
    return completed, _position(points[-1])


def _motion_progress(local_ms: float, lead_ms: int, duration_ms: int, *, eased: bool) -> float:
    progress = max(0.0, min(1.0, (local_ms - lead_ms) / duration_ms))
    return _ease_in_out_quadratic(progress) if eased else progress


def _gesture_alpha(local_ms: float, lead_ms: int, duration_ms: int) -> float:
    return _fade_after(local_ms, lead_ms + duration_ms, GESTURE_RELEASE_MS)


def _fade_after(local_ms: float, hold_until_ms: float, fade_ms: float) -> float:
    if local_ms <= hold_until_ms:
        return 1.0
    return max(0.0, 1 - (local_ms - hold_until_ms) / fade_ms)


def _ease_out_quart(progress: float) -> float:
    return 1 - (1 - progress) ** 4


def _ease_in_out_quadratic(progress: float) -> float:
    if progress < 0.5:
        return 2 * progress * progress
    return 1 - (-2 * progress + 2) ** 2 / 2


def _lerp(start: Position, end: Position, progress: float) -> Position:
    return (
        start[0] + (end[0] - start[0]) * progress,
        start[1] + (end[1] - start[1]) * progress,
    )


def _position(point: GesturePoint | TimedGesturePoint) -> Position:
    return float(point.x), float(point.y)


def _event_points(event: GestureEvent) -> Sequence[GesturePoint | TimedGesturePoint]:
    if isinstance(event, TapGesture):
        return [GesturePoint(x=event.x, y=event.y)]
    if isinstance(event, SwipeGesture):
        return [event.from_, event.to]
    return event.points


def _bounds(center: Position, radius: float) -> tuple[float, float, float, float]:
    return (
        center[0] - radius,
        center[1] - radius,
        center[0] + radius,
        center[1] + radius,
    )


def _alpha(color: Color, multiplier: float) -> Color:
    return color[0], color[1], color[2], round(color[3] * max(0.0, min(1.0, multiplier)))
