package com.pedronveloso.aasg.testkit

import java.io.ByteArrayOutputStream
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith
import kotlin.test.assertTrue

class GestureTimelineTest {
    @Test
    fun `paces actions and writes deterministic gesture metadata`() {
        var nowNanos = 1_000_000_000L
        val output = ByteArrayOutputStream()
        val actionTimes = mutableListOf<Long>()
        val clock = MonotonicClock { nowNanos }
        val sleeper = GestureSleeper { milliseconds -> nowNanos += milliseconds * 1_000_000 }

        GestureTimeline(
            media = "demo.mp4",
            width = 1080,
            height = 2400,
            output = output,
            clock = clock,
            sleeper = sleeper,
        ).start().use { timeline ->
            timeline.tap(GesturePoint(500, 1800)) { actionTimes += nowNanos }
            timeline.swipe(
                from = GesturePoint(900, 1200),
                to = GesturePoint(200, 1200),
                durationMs = 450,
            ) {
                actionTimes += nowNanos
            }
            timeline.drag(
                points = listOf(
                    TimedGesturePoint(0, 200, 1600),
                    TimedGesturePoint(400, 400, 1300),
                    TimedGesturePoint(900, 700, 900),
                ),
            ) {
                actionTimes += nowNanos
            }
        }

        assertEquals(
            listOf(1_820_000_000L, 3_540_000_000L, 5_260_000_000L),
            actionTimes,
        )
        val json = output.toString(Charsets.UTF_8)
        assertTrue(json.contains("\"schema\": 2"))
        assertTrue(json.contains("\"type\": \"tap\", \"at_ms\": 700, \"cue_lead_ms\": 120"))
        assertTrue(json.contains("\"type\": \"swipe\", \"at_ms\": 2420"))
        assertTrue(json.contains("\"duration_ms\": 450"))
        assertTrue(json.contains("\"type\": \"drag\", \"at_ms\": 4140"))
        assertTrue(json.contains("\"offset_ms\": 900, \"x\": 700, \"y\": 900"))
    }

    @Test
    fun `requires recording start before gestures`() {
        val timeline = GestureTimeline(
            media = "demo.mp4",
            width = 100,
            height = 200,
            output = ByteArrayOutputStream(),
        )

        assertFailsWith<IllegalStateException> {
            timeline.tap(GesturePoint(10, 20)) {}
        }
    }

    @Test
    fun `rejects unordered drag points`() {
        val timeline = GestureTimeline(
            media = "demo.mp4",
            width = 100,
            height = 200,
            output = ByteArrayOutputStream(),
        ).start()

        assertFailsWith<IllegalArgumentException> {
            timeline.drag(
                listOf(
                    TimedGesturePoint(0, 10, 10),
                    TimedGesturePoint(0, 20, 20),
                ),
            ) {}
        }
    }

    @Test
    fun `rejects coordinates outside the source video`() {
        val timeline = GestureTimeline(
            media = "demo.mp4",
            width = 100,
            height = 200,
            output = ByteArrayOutputStream(),
        ).start()

        assertFailsWith<IllegalArgumentException> {
            timeline.tap(GesturePoint(100, 20)) {}
        }
    }

    @Test
    fun `rejects timed drag coordinates outside the source video`() {
        val timeline = GestureTimeline(
            media = "demo.mp4",
            width = 100,
            height = 200,
            output = ByteArrayOutputStream(),
        ).start()

        assertFailsWith<IllegalArgumentException> {
            timeline.drag(
                listOf(
                    TimedGesturePoint(0, 10, 10),
                    TimedGesturePoint(100, 20, 200),
                ),
            ) {}
        }
    }
}
