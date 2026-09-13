# AASG

AASG is a deterministic, code-first Android capture-to-publish tool. It runs capture journeys that
already live in an Android app's instrumentation tests, collects their AndroidX Test Storage output,
and turns the raw media into repeatable screenshots, cut-outs, and framed videos.

AASG deliberately does not replace UI Automator, Compose testing, Gradle, ADB, or FFmpeg. It provides
the declarative layer that connects them.

## Status

AASG is under active pre-1.0 development. macOS is the supported host; Linux should work but is not
yet a release target.

## Requirements

- Python 3.12 or newer
- An Android project using AGP 8+ and AndroidX Test Storage
- ADB from Android SDK Platform Tools
- A project Gradle wrapper
- FFmpeg and FFprobe

Locale capture can use Android's per-app language support on an API 33+ device or emulator. Apps
that implement their own language override can instead apply the requested locale in their
instrumentation tests, so API 33+ is not a general capture requirement.

Install a local checkout with:

```shell
uv tool install .
aasg --version
```

For development:

```shell
uv sync
uv run aasg --help
```

## Quick start

From an Android project root:

```shell
aasg init
aasg config validate
aasg doctor
aasg capture
```

Interactive capture remembers the last successful device, captures, locales, themes, and navigation
modes outside the project directory. For automation, make every choice explicit:

```shell
aasg capture home --device emulator-5554 --locale en --theme light --navigation gestural --non-interactive
aasg capture --all --locale all --theme all --navigation all --device emulator-5554 --non-interactive
```

Use `--dry-run` to resolve the capture matrix and commands without invoking Android tooling. Every
real run writes a manifest and command logs under the configured run-log root. On completion, AASG
prints each generated raw asset and rendition as a path relative to the configuration directory;
`--json` includes the same ordered paths in its `assets` array.

When an interactive run offers to reuse the previous selection, it first shows the saved device,
captures, locales, themes, and navigation modes in subdued text so the default choice is explicit.

## Android test contract

The app remains responsible for in-app navigation, fixtures, permissions, UI synchronization,
locale and theme application, and deciding when to capture. AASG can manage the Android system's
gesture or three-button navigation mode and Show taps setting around a capture. The test writes
output through
`PlatformTestStorageRegistry`:

```kotlin
PlatformTestStorageRegistry.getInstance()
  .openOutputFile("screenshots/en/home-light.png")
  .use { output -> bitmap.compress(Bitmap.CompressFormat.PNG, 100, output) }
```

AASG runs one capture/locale/theme/navigation combination per instrumentation invocation and
immediately copies the fresh AndroidX Test Storage output. The default path delegates execution and
collection to Gradle. Projects affected by an Android/AGP user-selection incompatibility can opt
into direct instrumentation: Gradle still builds both APKs, while AASG resolves the active numeric
Android user, installs the APKs, launches `am instrument --user <id>`, and pulls only the declared
Test Storage directory. AASG never reads app-private files.

Tests can attach named UI regions to captured media:

```json
{
  "schema": 1,
  "media": "home-setup-tips-light.png",
  "regions": {
    "setup-tips": {"x": 42, "y": 560, "width": 996, "height": 480}
  }
}
```

Coordinates use integer pixels relative to the media with a top-left origin. Recipes can crop or
redact a named region without duplicating UI coordinates on the host.

## Configuration

`aasg.yaml` is strict and versioned. Unknown fields, missing references, unsafe paths, incompatible
schema versions, and invalid pipeline combinations fail before a test starts. All relative paths
resolve from the configuration file.

AASG 0.4 uses configuration schema 4. To migrate a schema 3 configuration, change its top-level
`schema` value to `4`. Video captures default to `show_taps: true`; set it to `false` when touch
feedback should be hidden. A video capture may also declare JSON artifacts, but it cannot mix video
and image artifacts. Split mixed visual output into separate captures before migrating.

```yaml
schema: 4
project:
  artifact_root: artifacts
  run_log_root: artifacts/aasg/runs
  default_timeout_seconds: 90

android:
  min_api: 33
  adb: adb
  gradle_wrapper: ./gradlew
  prepare_tasks: [":app:assembleDebug", ":app:assembleDebugAndroidTest"]
  test_task: ":app:connectedDebugAndroidTest"
  additional_output_dir: app/build/outputs/connected_android_test_additional_output
  locale_argument: screenshotLocale
  theme_argument: screenshotTheme
  # Optional. Omit this block when connectedDebugAndroidTest works on target devices.
  direct_instrumentation:
    application_id: com.example.app
    test_application_id: com.example.app.test
    runner: com.example.TestRunner
    app_apk: app/build/outputs/apk/debug/app-debug.apk
    test_apk: app/build/outputs/apk/androidTest/debug/app-debug-androidTest.apk
    device_output_dir: /sdcard/Android/media/com.example.app/additional_test_output

variants:
  locales: {en: English, es: Spanish}
  themes: {light: Light, dark: Dark}
  groups: {store-screenshots: [home]}

captures:
  home:
    label: Home screenshot
    test: com.example.HomeScreenshotCaptureTest
    navigation: all
    arguments: {screenshot: home, notAnnotation: ""}
    artifacts:
      - id: home
        type: image
        source: screenshots/{locale}/home-{theme}.png
        publish: screenshots/raw/{locale}/home-{theme}-{navigation}.png
        renditions:
          - publish: screenshots/framed/{locale}/home-{theme}-{navigation}.png
            pipeline: pixel-8
  walkthrough:
    label: Onboarding walkthrough
    test: com.example.OnboardingVideoCaptureTest
    show_taps: true
    arguments: {recording: onboarding}
    artifacts:
      - id: walkthrough
        type: video
        source: recordings/{locale}/onboarding-{theme}.mp4
        publish: videos/raw/{locale}/onboarding-{theme}.mp4

pipelines:
  pixel-8:
    steps:
      - type: device_frame
        source: community
        frame: android-phone/pixel-8/hazel
        fit: cover
        crop_to_frame: true

frame_sources:
  community:
    kind: device-frames-media
    allow_unlicensed_downloads: true
```

Artifact `source` is an exact suffix inside the AGP additional-output tree. `publish` and rendition
paths stay under `project.artifact_root`. Captures accept `navigation: gestural`, `three-button`,
`all`, or `ignore` (the default). Only `all` captures use the repeatable `--navigation` selection;
their publication paths must contain `{navigation}` so modes cannot overwrite each other. AASG
restores the device's original mode after the run. Captures containing a video artifact accept
`show_taps: true` or `false`; the default is `true`. AASG applies the active Android user's setting
only during the recording capture and restores the original value before publishing artifacts,
including after failures and interruptions. Video captures may include JSON artifacts but not image
artifacts. Show taps is entirely YAML-controlled and is never an interactive capture choice.
Available typed operations are `resize`, `crop`, `pad`,
`background`, `blur`, `redact`, `device_frame`, `edge_fade`, `feather`, `trim`, and
`temporal_fade`. A `device_frame` step can set `crop_to_frame: true` to remove fully transparent
canvas margins while preserving every non-zero alpha pixel in the frame artwork. It defaults to
`false`.

Process an existing file through any named pipeline:

```shell
aasg process setup-card raw.png --metadata raw.metadata.json --theme light --output card.png
```

Pass `--theme` when a pipeline uses a theme-keyed background color.

## Output safety and diagnostics

A variant is first collected and rendered in its run staging directory. AASG validates the media,
hashes it, and only then atomically updates stable output paths. A failed variant leaves earlier
valid outputs intact. Run-manifest schema 3 records configuration, selected device model/API,
navigation and Show taps changes and restoration, timings, checksums, renderer commands, and frame
provenance; device serials and common credential patterns are redacted.

## Device frames and licensing

AASG can read the index, frame, mask, and geometry published by
[`device-frames-media`](https://github.com/jonnyjackson26/device-frames-media). It downloads only a
selected frame and caches it in the operating system cache directory; it never clones or bundles
the catalog.

That repository currently has no recognized license. Remote access therefore requires the explicit
`allow_unlicensed_downloads: true` acknowledgement. Downloaded artwork is not covered by AASG's
Apache-2.0 license, and users are responsible for determining whether their use is permitted.
Project-local frame packs are also supported and must declare their license.
Their `template.json` uses the same `frame`, `mask`, `screen`, and `frameSize` geometry fields as the
remote catalog, plus mandatory `sha256.frame` and `sha256.mask` values. AASG verifies both files
before use.

Cached indexes are not silently refreshed:

```shell
aasg frames list community
aasg frames fetch community android-phone/pixel-8/hazel
aasg frames refresh community
```

## Development

```shell
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/) and are checked
with commitlint in CI. The commit-message tooling requires Node.js 22.12 or newer. Install it with
`npm ci`, then check a local commit range with:

```shell
npm run commitlint -- --from HEAD~1 --to HEAD
```

Use a type such as `feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`, or `chore`, followed by a
short imperative description; for example, `feat: add WebM rendering`. Mark breaking changes with
`!` before the colon or a `BREAKING CHANGE:` footer.

See [AGENTS.md](AGENTS.md) for repository conventions.

## Versioning

AASG follows [Semantic Versioning 2.0.0](https://semver.org/). Every completed feature increments
the application version; feature releases increment the minor version and backwards-compatible
fixes increment the patch version. Until version 1.0.0, incompatible changes also increment the
minor version.

The YAML schema has its own integer version. Adding, removing, renaming, or changing the meaning of
any YAML definition increments that schema version in the model, starter configuration,
documentation, tests, and pilot project configurations. This gives older AASG releases an explicit
migration signal instead of leaving them to report an unknown-field error.

## Author

AASG was created and is maintained by Pedro Veloso. Author information is also included in the
Python package metadata.

## License

AASG source code and documentation are licensed under the Apache License 2.0. Third-party media
downloaded through a frame provider retains its own terms.
