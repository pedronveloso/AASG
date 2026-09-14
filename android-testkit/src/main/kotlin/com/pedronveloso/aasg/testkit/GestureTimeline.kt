package com.pedronveloso.aasg.testkit

import java.io.Closeable
import java.io.OutputStream
import java.nio.charset.StandardCharsets

/** Source-video pixel coordinates with a top-left origin. */
public data class GesturePoint(
    public val x: Int,
    public val y: Int,
) {
    init {
        require(x >= 0) { "x must not be negative" }
        require(y >= 0) { "y must not be negative" }
    }
}

/** A point sampled during a drag, relative to the start of that drag. */
public data class TimedGesturePoint(
    public val offsetMs: Long,
    public val x: Int,
    public val y: Int,
) {
    init {
        require(offsetMs >= 0) { "offsetMs must not be negative" }
        require(x >= 0) { "x must not be negative" }
        require(y >= 0) { "y must not be negative" }
    }
}

/** Default holds make each state readable before the next interaction. */
public data class GesturePacing(
    public val beforeActionMs: Long = 700,
    public val cueLeadMs: Long = 120,
    public val afterActionMs: Long = 900,
) {
    init {
        require(beforeActionMs >= 0) { "beforeActionMs must not be negative" }
        require(cueLeadMs >= 0) { "cueLeadMs must not be negative" }
        require(afterActionMs >= 0) { "afterActionMs must not be negative" }
    }
}

public fun interface MonotonicClock {
    public fun nowNanos(): Long
}

public fun interface GestureSleeper {
    public fun sleep(milliseconds: Long)
}

private sealed interface GestureEvent {
    val atMs: Long
    val cueLeadMs: Long

    data class Tap(
        override val atMs: Long,
        override val cueLeadMs: Long,
        val point: GesturePoint,
    ) : GestureEvent

    data class Swipe(
        override val atMs: Long,
        override val cueLeadMs: Long,
        val durationMs: Long,
        val from: GesturePoint,
        val to: GesturePoint,
    ) : GestureEvent

    data class Drag(
        override val atMs: Long,
        override val cueLeadMs: Long,
        val points: List<TimedGesturePoint>,
    ) : GestureEvent
}

/**
 * Records paced gestures beside an app-owned screen recording.
 *
 * Call [start] immediately after the recorder is active. Existing Compose, UIAutomator, or custom
 * actions remain caller-owned and are supplied as lambdas. Closing the timeline writes semantic
 * metadata schema 2 and closes [output].
 */
public class GestureTimeline(
    private val media: String,
    private val width: Int,
    private val height: Int,
    private val output: OutputStream,
    private val pacing: GesturePacing = GesturePacing(),
    private val synchronize: () -> Unit = {},
    private val clock: MonotonicClock = MonotonicClock(System::nanoTime),
    private val sleeper: GestureSleeper = GestureSleeper { milliseconds ->
        Thread.sleep(milliseconds)
    },
) : Closeable {
    private val events: MutableList<GestureEvent> = mutableListOf()
    private var startedAtNanos: Long? = null
    private var closed: Boolean = false

    init {
        require(media.isNotBlank()) { "media must not be blank" }
        require(width > 0) { "width must be positive" }
        require(height > 0) { "height must be positive" }
    }

    public fun start(): GestureTimeline {
        check(!closed) { "timeline is closed" }
        check(startedAtNanos == null) { "timeline has already started" }
        startedAtNanos = clock.nowNanos()
        return this
    }

    public fun tap(
        point: GesturePoint,
        action: () -> Unit,
    ) {
        perform(
            event = { atMs -> GestureEvent.Tap(atMs, pacing.cueLeadMs, point) },
            action = action,
        )
    }

    public fun swipe(
        from: GesturePoint,
        to: GesturePoint,
        durationMs: Long,
        action: () -> Unit,
    ) {
        require(durationMs > 0) { "durationMs must be positive" }
        perform(
            event = { atMs ->
                GestureEvent.Swipe(atMs, pacing.cueLeadMs, durationMs, from, to)
            },
            action = action,
        )
    }

    public fun drag(
        points: List<TimedGesturePoint>,
        action: () -> Unit,
    ) {
        require(points.size >= 2) { "drag needs at least two points" }
        require(points.first().offsetMs == 0L) { "drag must start at offsetMs 0" }
        require(points.zipWithNext().all { (first, second) -> first.offsetMs < second.offsetMs }) {
            "drag point offsets must be strictly increasing"
        }
        perform(
            event = { atMs -> GestureEvent.Drag(atMs, pacing.cueLeadMs, points.toList()) },
            action = action,
        )
    }

    override fun close() {
        if (closed) return
        closed = true
        try {
            check(startedAtNanos != null) { "timeline was not started" }
            output.write(toJson().toByteArray(StandardCharsets.UTF_8))
            output.flush()
        } finally {
            output.close()
        }
    }

    private fun perform(
        event: (Long) -> GestureEvent,
        action: () -> Unit,
    ) {
        check(!closed) { "timeline is closed" }
        check(startedAtNanos != null) { "call start() after recording begins" }
        synchronize()
        sleeper.sleep(pacing.beforeActionMs)
        events += event(elapsedMs())
        sleeper.sleep(pacing.cueLeadMs)
        action()
        synchronize()
        sleeper.sleep(pacing.afterActionMs)
    }

    private fun elapsedMs(): Long {
        val started = checkNotNull(startedAtNanos)
        return (clock.nowNanos() - started) / NANOS_PER_MILLISECOND
    }

    private fun toJson(): String = buildString {
        append("{\n")
        append("  \"schema\": 2,\n")
        append("  \"media\": \"").append(jsonEscape(media)).append("\",\n")
        append("  \"coordinate_space\": {\"width\": ").append(width)
        append(", \"height\": ").append(height).append(", \"origin\": \"top-left\"},\n")
        append("  \"gestures\": [")
        if (events.isNotEmpty()) append('\n')
        events.forEachIndexed { index, event ->
            append("    ").append(event.toJson())
            if (index != events.lastIndex) append(',')
            append('\n')
        }
        append("  ]\n")
        append("}\n")
    }

    private fun GestureEvent.toJson(): String = when (this) {
        is GestureEvent.Tap -> buildString {
            append("{\"type\": \"tap\", \"at_ms\": ").append(atMs)
            append(", \"cue_lead_ms\": ").append(cueLeadMs)
            append(", \"x\": ").append(point.x).append(", \"y\": ").append(point.y).append('}')
        }
        is GestureEvent.Swipe -> buildString {
            append("{\"type\": \"swipe\", \"at_ms\": ").append(atMs)
            append(", \"cue_lead_ms\": ").append(cueLeadMs)
            append(", \"duration_ms\": ").append(durationMs)
            append(", \"from\": ").append(from.toJson())
            append(", \"to\": ").append(to.toJson()).append('}')
        }
        is GestureEvent.Drag -> buildString {
            append("{\"type\": \"drag\", \"at_ms\": ").append(atMs)
            append(", \"cue_lead_ms\": ").append(cueLeadMs)
            append(", \"points\": [")
            points.forEachIndexed { index, point ->
                if (index > 0) append(", ")
                append(point.toJson())
            }
            append("]}")
        }
    }

    private fun GesturePoint.toJson(): String = "{\"x\": $x, \"y\": $y}"

    private fun TimedGesturePoint.toJson(): String =
        "{\"offset_ms\": $offsetMs, \"x\": $x, \"y\": $y}"

    private fun jsonEscape(value: String): String = buildString {
        value.forEach { character ->
            when (character) {
                '\\' -> append("\\\\")
                '"' -> append("\\\"")
                '\b' -> append("\\b")
                '\u000C' -> append("\\f")
                '\n' -> append("\\n")
                '\r' -> append("\\r")
                '\t' -> append("\\t")
                else -> if (character.code < 0x20) {
                    append("\\u").append(character.code.toString(16).padStart(4, '0'))
                } else {
                    append(character)
                }
            }
        }
    }

    private companion object {
        private const val NANOS_PER_MILLISECOND: Long = 1_000_000
    }
}
