# AASG Android Testkit

`aasg-testkit` records deterministic gesture timelines and adds readable holds around existing
Android instrumentation actions. It does not navigate the app or replace Compose, UIAutomator, or
another test driver.

```kotlin
androidTestImplementation("io.github.pedronveloso:aasg-testkit:0.15.0")
```

`CaptureOutputPaths` builds the schema 9 Test Storage paths from the capture ID, locale, and
theme. For example, `video("onboarding", "en", "light")` returns
`aasg/videos/en/onboarding-light.mp4`; `metadata(mediaPath)` returns
`aasg/videos/en/onboarding-light.metadata.json`. Record the video at `mediaPath`, then open the
sidecar output stream and start the timeline clock:

```kotlin
val mediaPath = CaptureOutputPaths.video("onboarding", "en", "light")
PlatformTestStorageRegistry.getInstance()
  .openOutputFile(CaptureOutputPaths.metadata(mediaPath))
  .use { output ->
    GestureTimeline(
      media = mediaPath.substringAfterLast('/'),
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

Use `CaptureOutputPaths.image()` and `CaptureOutputPaths.json()` for image and JSON artifacts.
Pass `artifactId` to a path builder only when the capture declares more than one artifact; AASG
adds the artifact ID to every source filename in that case. An image or video with `metadata: true`
must also write the sidecar path returned by `CaptureOutputPaths.metadata(mediaPath)`.

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

The module is a Kotlin/JVM library that targets Java 17 bytecode. Consuming Android projects need
build tooling that supports Java 17 class files; the library itself does not apply an Android Gradle
Plugin or set a minimum SDK version. A non-prerelease GitHub release tagged
with the shared AASG version publishes signed artifacts to Maven Central. The repository must first
have the `io.github.pedronveloso` namespace verified in the Central Portal and these Actions secrets:

- `MAVEN_CENTRAL_USERNAME`
- `MAVEN_CENTRAL_PASSWORD`
- `MAVEN_SIGNING_KEY`
- `MAVEN_SIGNING_PASSWORD`
