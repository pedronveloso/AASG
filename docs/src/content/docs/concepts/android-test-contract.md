---
title: Android test contract
description: Keep app behavior inside instrumentation tests and hand off only media to AASG.
---

## The app owns the journey

An AASG capture is not a replacement for your test stack. Compose tests, Espresso, UI
Automator, and your test fixtures continue to own navigation, permissions, state,
synchronization, locale/theme behavior, and deciding precisely when a frame is ready.

AASG sets up the requested capture variant, runs the configured test, and collects only
the declared AndroidX Test Storage output. It never reads app-private files.

## Write output through AndroidX Test Storage

Use `PlatformTestStorageRegistry` for every artifact. Keep paths deterministic and
relative to the configured additional-output tree:

```kotlin
PlatformTestStorageRegistry.getInstance()
  .openOutputFile("recordings/en/onboarding-light.mp4")
  .use { output -> recorder.writeTo(output.fileDescriptor) }
```

The artifact `source` in `aasg.yaml` is an exact suffix within that tree. AASG rejects
undeclared or stale output rather than guessing which file belongs to a capture.

## System settings AASG may manage

For captures that request it, AASG temporarily switches Android navigation between
gestural and three-button modes. For video captures it can also control Android's
**Show taps** setting. It restores each changed setting even after an interrupted run.

Choose `show_taps: false` when a video pipeline uses `gesture_overlay`; otherwise both
native Android circles and rendered gesture cues would appear.

## Record gesture metadata without a second automation layer

`aasg-testkit` records a timeline around test actions you already perform. Start it
after the app-owned screen recorder begins, then write JSON sidecar metadata through
AndroidX Test Storage. The helper does not navigate the app.

```kotlin
GestureTimeline(
  media = "onboarding-light.mp4",
  width = 1080,
  height = 2400,
  output = output,
  synchronize = { composeRule.waitForIdle() },
).start().use { journey ->
  journey.tap(GesturePoint(540, 1800)) {
    composeRule.onNodeWithTag("continue").performClick()
  }
}
```

See [Semantic metadata](../reference/semantic-metadata/) for the sidecar contract and
[Rendering pipelines](../guides/rendering/) for `gesture_overlay`.
