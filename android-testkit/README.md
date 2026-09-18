# AASG Android Testkit

`aasg-testkit` records deterministic gesture timelines and adds readable holds around existing
Android instrumentation actions. It does not navigate the app or replace Compose, UIAutomator, or
another test driver.

```kotlin
androidTestImplementation("io.github.pedronveloso:aasg-testkit:0.10.1")
```

Browse published versions on [Maven Central](https://central.sonatype.com/artifact/io.github.pedronveloso/aasg-testkit).

Open an AndroidX Test Storage output stream, start the app's screen recorder, and then start the
timeline clock:

```kotlin
PlatformTestStorageRegistry.getInstance()
  .openOutputFile("recordings/onboarding.metadata.json")
  .use { output ->
    GestureTimeline(
      media = "onboarding.mp4",
      width = 1080,
      height = 2400,
      output = output,
      synchronize = { composeRule.waitForIdle() },
    ).start().use { journey ->
      journey.tap(GesturePoint(540, 1800)) {
        composeRule.onNodeWithTag("continue").performClick()
      }
    }
  }
```

Call `start()` only after recording is active. Coordinates are source-video pixels with a top-left
origin. The helper rejects coordinates outside that source space. Swipe and drag durations must
match the duration used by the caller-owned test action.

`GesturePacing()` defaults to a 700 ms pre-action hold, a 120 ms visual cue lead, and a 900 ms
post-action hold. Pass a different pacing value when the product needs longer reading time, while
keeping the same values throughout a capture series for consistent rhythm.

The recording dimensions, orientation, display scaling, and system-bar treatment must remain fixed
for a journey. If the recorder crops or rotates its output, transform coordinates before passing
them to the timeline. Avoid placing gestures under captions or near store-safe-area edges. AASG
validates the sidecar against the decoded video and rejects timing drift that would push an animation
past the end of the clip.

## Publishing

The module is a Kotlin/JVM library so it can be consumed by Android instrumentation tests without
imposing an Android Gradle Plugin or minimum-SDK version. A non-prerelease GitHub release tagged
with the shared AASG version publishes signed artifacts to Maven Central. The repository must first
have the `io.github.pedronveloso` namespace verified in the Central Portal and these Actions secrets:

- `MAVEN_CENTRAL_USERNAME`
- `MAVEN_CENTRAL_PASSWORD`
- `MAVEN_SIGNING_KEY`
- `MAVEN_SIGNING_PASSWORD`
