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

Interactive capture remembers the last successful device, captures, locales, and themes outside the
project directory. For automation, make every choice explicit:

```shell
aasg capture home --device emulator-5554 --locale en --theme light --non-interactive
aasg capture --all --locale all --theme all --device emulator-5554 --non-interactive
```

Use `--dry-run` to resolve the capture matrix and commands without invoking Android tooling. Every
real run writes a manifest and command logs under the configured run-log root. On completion, AASG
prints each generated raw asset and rendition as a path relative to the configuration directory;
`--json` includes the same ordered paths in its `assets` array.

When an interactive run offers to reuse the previous selection, it first shows the saved device,
captures, locales, and themes in subdued text so the default choice is explicit.

## Android test contract

The app remains responsible for navigation, fixtures, permissions, UI synchronization, locale and
theme application, and deciding when to capture. It writes output through
`PlatformTestStorageRegistry`:

```kotlin
PlatformTestStorageRegistry.getInstance()
  .openOutputFile("screenshots/en/home-light.png")
  .use { output -> bitmap.compress(Bitmap.CompressFormat.PNG, 100, output) }
```

AASG runs one capture/locale/theme combination per instrumentation invocation and immediately
copies the fresh AndroidX Test Storage output. The default path delegates execution and collection
to Gradle. Projects affected by an Android/AGP user-selection incompatibility can opt into direct
instrumentation: Gradle still builds both APKs, while AASG resolves the active numeric Android user,
installs the APKs, launches `am instrument --user <id>`, and pulls only the declared Test Storage
directory. AASG never reads app-private files.

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

`aasg.yaml` is strict and versioned. Unknown fields, missing references, unsafe paths, and invalid
pipeline combinations fail before a test starts. All relative paths resolve from the configuration
file.

```yaml
schema: 1
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
    arguments: {screenshot: home, notAnnotation: ""}
    artifacts:
      - id: home
        type: image
        source: screenshots/{locale}/home-{theme}.png
        publish: screenshots/raw/{locale}/home-{theme}.png
        renditions:
          - publish: screenshots/framed/{locale}/home-{theme}.png
            pipeline: pixel-8

pipelines:
  pixel-8:
    steps:
      - type: device_frame
        source: community
        frame: android-phone/pixel-8/hazel
        fit: cover

frame_sources:
  community:
    kind: device-frames-media
    allow_unlicensed_downloads: true
```

Artifact `source` is an exact suffix inside the AGP additional-output tree. `publish` and rendition
paths stay under `project.artifact_root`. Available typed operations are `resize`, `crop`, `pad`,
`background`, `blur`, `redact`, `device_frame`, `edge_fade`, `feather`, `trim`, and
`temporal_fade`.

Process an existing file through any named pipeline:

```shell
aasg process setup-card raw.png --metadata raw.metadata.json --theme light --output card.png
```

Pass `--theme` when a pipeline uses a theme-keyed background color.

## Output safety and diagnostics

A variant is first collected and rendered in its run staging directory. AASG validates the media,
hashes it, and only then atomically updates stable output paths. A failed variant leaves earlier
valid outputs intact. The run manifest records configuration, selected device model/API, timings,
checksums, renderer commands, and frame provenance; device serials and common credential patterns
are redacted.

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

AASG follows [Semantic Versioning 2.0.0](https://semver.org/). Until version 1.0.0, incompatible
changes may be released in a new minor version. Patch releases remain reserved for
backwards-compatible fixes. The `feat`, `fix`, and breaking-change markers in Conventional Commit
messages record the intended release impact; before 1.0.0, breaking markers follow the minor-version
policy above.

## Author

AASG was created and is maintained by Pedro Veloso. Author information is also included in the
Python package metadata.

## License

AASG source code and documentation are licensed under the Apache License 2.0. Third-party media
downloaded through a frame provider retains its own terms.
