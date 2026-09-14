# AASG Android Testkit

`aasg-testkit` records deterministic gesture timelines and adds readable holds around existing
Android instrumentation actions. It does not navigate the app or replace Compose, UIAutomator, or
another test driver.

```kotlin
androidTestImplementation("com.pedronveloso.aasg:aasg-testkit:0.5.0")
```

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
origin. Swipe and drag durations must match the duration used by the caller-owned test action.
