from __future__ import annotations

import itertools
import os
import sys
import time
from pathlib import Path

import pytest
from pydantic import ValidationError

from aasg.errors import PrerequisiteError, ProcessingError
from aasg.gestures import execute_gesture_overlay, render_gesture_frame, validate_gesture_metadata
from aasg.models import GestureOverlayStep, SemanticMetadata


def metadata_with_gestures() -> SemanticMetadata:
    return SemanticMetadata.model_validate(
        {
            "schema": 2,
            "media": "demo.mp4",
            "coordinate_space": {"width": 320, "height": 640, "origin": "top-left"},
            "gestures": [
                {"type": "tap", "at_ms": 200, "cue_lead_ms": 100, "x": 160, "y": 500},
                {
                    "type": "swipe",
                    "at_ms": 900,
                    "cue_lead_ms": 100,
                    "duration_ms": 400,
                    "from": {"x": 260, "y": 320},
                    "to": {"x": 60, "y": 320},
                },
                {
                    "type": "drag",
                    "at_ms": 1600,
                    "cue_lead_ms": 100,
                    "points": [
                        {"offset_ms": 0, "x": 80, "y": 500},
                        {"offset_ms": 300, "x": 160, "y": 420},
                        {"offset_ms": 700, "x": 240, "y": 300},
                    ],
                },
            ],
        }
    )


def test_tap_expands_a_ring_after_the_action_cue() -> None:
    metadata = metadata_with_gestures()
    step = GestureOverlayStep(type="gesture_overlay", radius_px=40)

    before = render_gesture_frame(metadata, step, width=320, height=640, time_ms=199)
    pressed = render_gesture_frame(metadata, step, width=320, height=640, time_ms=300)
    expanded = render_gesture_frame(metadata, step, width=320, height=640, time_ms=470)

    assert before.getbbox() is None
    assert pressed.getpixel((160, 500))[3] > 0
    assert expanded.getpixel((190, 500))[3] > 0


def test_swipe_uses_eased_travel_and_a_fading_trail() -> None:
    metadata = metadata_with_gestures()
    step = GestureOverlayStep(type="gesture_overlay", radius_px=40)

    halfway = render_gesture_frame(metadata, step, width=320, height=640, time_ms=1200)

    assert halfway.getpixel((160, 320))[3] > 0
    assert halfway.getpixel((185, 320))[3] > 0


def test_drag_follows_sampled_path() -> None:
    metadata = metadata_with_gestures()
    step = GestureOverlayStep(type="gesture_overlay", radius_px=40)

    frame = render_gesture_frame(metadata, step, width=320, height=640, time_ms=2100)

    assert frame.getpixel((160, 420))[3] > 0
    assert frame.getpixel((180, 390))[3] > 0


def test_reduced_motion_uses_a_static_path() -> None:
    metadata = metadata_with_gestures()
    step = GestureOverlayStep(type="gesture_overlay", radius_px=40, motion="reduced")

    frame = render_gesture_frame(metadata, step, width=320, height=640, time_ms=1100)

    assert frame.getpixel((260, 320))[3] > 0
    assert frame.getpixel((60, 320))[3] > 0
    assert frame.getpixel((160, 320))[3] > 0


@pytest.mark.parametrize(
    ("time_ms", "path_point", "endpoint"),
    [
        pytest.param(1100, (160, 320), (260, 320), id="swipe"),
        pytest.param(1900, (160, 420), (80, 500), id="drag"),
    ],
)
def test_reduced_motion_respects_disabled_trail(
    time_ms: int,
    path_point: tuple[int, int],
    endpoint: tuple[int, int],
) -> None:
    metadata = metadata_with_gestures()
    with_trail = GestureOverlayStep(
        type="gesture_overlay", radius_px=40, motion="reduced", trail=True
    )
    without_trail = GestureOverlayStep(
        type="gesture_overlay", radius_px=40, motion="reduced", trail=False
    )

    trail_frame = render_gesture_frame(metadata, with_trail, width=320, height=640, time_ms=time_ms)
    no_trail_frame = render_gesture_frame(
        metadata, without_trail, width=320, height=640, time_ms=time_ms
    )

    assert trail_frame.getpixel(path_point)[3] > 0
    assert no_trail_frame.getpixel(path_point)[3] == 0
    assert no_trail_frame.getpixel(endpoint)[3] > 0


def test_gesture_metadata_validates_dimensions_bounds_and_duration() -> None:
    metadata = metadata_with_gestures()
    step = GestureOverlayStep(type="gesture_overlay")

    with pytest.raises(ProcessingError, match="does not match"):
        validate_gesture_metadata(metadata, step, width=640, height=320, duration=3.0)
    with pytest.raises(ProcessingError, match="outside"):
        validate_gesture_metadata(metadata, step, width=320, height=640, duration=2.0)


def test_semantic_metadata_rejects_unordered_events_and_drag_points() -> None:
    base = {
        "schema": 2,
        "media": "demo.mp4",
        "coordinate_space": {"width": 100, "height": 200, "origin": "top-left"},
    }
    with pytest.raises(ValidationError, match="sorted by at_ms"):
        SemanticMetadata.model_validate(
            {
                **base,
                "gestures": [
                    {"type": "tap", "at_ms": 200, "x": 10, "y": 10},
                    {"type": "tap", "at_ms": 100, "x": 20, "y": 20},
                ],
            }
        )
    with pytest.raises(ValidationError, match="exceeds coordinate_space"):
        SemanticMetadata.model_validate(
            {
                **base,
                "gestures": [{"type": "tap", "at_ms": 100, "x": 100, "y": 20}],
            }
        )
    with pytest.raises(ValidationError, match="strictly increasing"):
        SemanticMetadata.model_validate(
            {
                **base,
                "gestures": [
                    {
                        "type": "drag",
                        "at_ms": 100,
                        "points": [
                            {"offset_ms": 0, "x": 10, "y": 10},
                            {"offset_ms": 0, "x": 20, "y": 20},
                        ],
                    }
                ],
            }
        )


def test_schema_one_keeps_its_original_region_contract() -> None:
    with pytest.raises(ValidationError, match="schema 1 requires regions"):
        SemanticMetadata.model_validate({"schema": 1, "media": "still.png"})
    with pytest.raises(ValidationError, match="does not support gesture timelines"):
        SemanticMetadata.model_validate(
            {"schema": 1, "media": "still.png", "regions": {}, "gestures": []}
        )


def test_gesture_renderer_reports_missing_and_failed_processes() -> None:
    with pytest.raises(PrerequisiteError, match="Executable not found"):
        execute_gesture_overlay(["aasg-missing-gesture-renderer"], [])

    with pytest.raises(ProcessingError, match="renderer failed"):
        execute_gesture_overlay(
            [sys.executable, "-c", "import sys; sys.stderr.write('renderer failed'); sys.exit(2)"],
            [],
        )


def test_gesture_renderer_times_out_while_frame_writes_are_blocked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pid_path = tmp_path / "renderer.pid"
    monkeypatch.setattr("aasg.gestures.GESTURE_OVERLAY_TIMEOUT_SECONDS", 0.5)
    command = [
        sys.executable,
        "-c",
        (
            "import os, time; from pathlib import Path; "
            f"Path({str(pid_path)!r}).write_text(str(os.getpid())); time.sleep(60)"
        ),
    ]

    started = time.monotonic()
    with pytest.raises(ProcessingError, match="timed out"):
        execute_gesture_overlay(command, itertools.repeat(b"x" * 65_536))

    assert time.monotonic() - started < 2
    assert pid_path.is_file()
    with pytest.raises(ProcessLookupError):
        os.kill(int(pid_path.read_text()), 0)
