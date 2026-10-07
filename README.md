# AASG

AASG is a deterministic, code-first Android capture-to-publish tool. It runs capture
journeys that already live in Android instrumentation tests, collects AndroidX Test
Storage output, and turns it into repeatable screenshots, cut-outs, and framed video.

AASG deliberately does not replace Compose testing, UI Automator, Gradle, ADB, or
FFmpeg. The app owns navigation and state; AASG owns the capture matrix, collection,
metadata, rendering recipes, and stable output.

## Documentation

The full guide covers first capture, the Android test contract, rendering, device-frame
licensing, the complete `aasg.yaml` schema, semantic metadata, and every CLI command:

- [AASG documentation](https://pedronveloso.github.io/AASG/)
- [Agent-readable Markdown index](https://pedronveloso.github.io/AASG/llms.txt)

The site is initially served from GitHub Pages. It will move to
`https://aasg.pedronveloso.com/` once the custom-domain DNS record is configured.

## Requirements

- Python 3.12 or newer
- An Android project using AGP 8+ and AndroidX Test Storage
- ADB from Android SDK Platform Tools
- A project Gradle wrapper
- FFmpeg and FFprobe

## Install and run

```shell
uv tool install android-automated-screengrabs
# or: pipx install android-automated-screengrabs
aasg init
aasg config validate
aasg doctor
aasg capture
```

When `--device` is omitted, capture uses the only online ADB-authorized device or emulator.
If several are online, an interactive run lists them for selection; a non-interactive run
requires `--device` in that case. A previous capture selection never pins the device.

For source development, run `uv sync` and then `uv run aasg --help`.

Configuration schema 9 infers AndroidX Test Storage source paths from capture IDs, locale,
theme, and artifact type. Instrumentation tests can use `aasg-testkit` path builders to
write those files. Publication directories still use `publish_dir`; AASG generates
published filenames from capture IDs and selected variants. See the configuration
reference for migration from schema 8.

Released versions are published to
[PyPI](https://pypi.org/project/android-automated-screengrabs/). AASG still requires the Android
SDK Platform Tools, a Gradle wrapper, FFmpeg, and FFprobe; run `aasg doctor` after installation to
check the local prerequisites and encoders needed by configured renditions.

## Android Studio plugin

The optional **AASG** plugin adds YAML completion, field documentation, structural
validation, and Cmd/Ctrl-click navigation to Java and Kotlin capture classes,
methods, and instrumentation runners in `aasg.yaml` and `aasg.yml`. Version 0.1.0
targets Android Studio Quail 4 2026.1.4 Patch 1 (platform branch 261, starting at
build 261.26222.65). Keep Studio's bundled Java, Kotlin, YAML, and JSON support enabled.

For example, Cmd-click on macOS or Ctrl-click on Windows/Linux on the class name
in this capture entry opens its Kotlin or Java declaration:

```yaml
captures:
  advanced-link-cleanup:
    label: Advanced Mode link cleanup
    test: app.altsea.feature.screenshots.PlayStoreScreenshotCaptureTest
```

Navigation also supports `Class#method`, comma-separated selectors, nested classes
using JVM `$` notation, and `android.direct_instrumentation.runner`. Class lookup
includes imported instrumentation-test roots and dependencies. Unresolved classes
and methods produce warnings after indexing finishes.

Build the installable ZIP with JDK 21 as the Gradle JVM, from the repository root:

```shell
./android-studio-plugin/gradlew -p android-studio-plugin buildPlugin
```

The ZIP is written to `android-studio-plugin/build/distributions/`. It is also
available as an artifact of the **Android Studio plugin** CI workflow. Install it
through **Settings → Plugins → gear menu → Install Plugin from Disk**. See
the [plugin build and installation guide](android-studio-plugin/README.md) and
[editor documentation](https://pedronveloso.github.io/AASG/guides/android-studio/).
Editor assistance uses a bundled schema and needs no Python installation. It
supports configuration schema 9; older schemas are flagged while class navigation
remains available. Use `aasg config validate` for complete semantic and filesystem
validation. The plugin is distributed as a ZIP and versioned independently from
the CLI and Android testkit.

## Development

Run the Python package checks from the repository root:

```shell
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build
npm ci
npm run commitlint -- --from HEAD~1 --to HEAD
```

Check the Android testkit with JDK 17 as the Gradle JVM:

```shell
./android-testkit/gradlew -p android-testkit \
  checkKotlinAbi test build generatePomFileForMavenPublication
```

Check the Android Studio plugin with JDK 21 as the Gradle JVM:

```shell
uv run python tools/generate_ide_schema.py --check
./android-studio-plugin/gradlew -p android-studio-plugin \
  checkKotlinFormat test buildPlugin verifyPluginProjectConfiguration verifyPlugin
```

The plugin build downloads pinned Studio `2026.1.4.8`. Add
`-PstudioLocalPath="/path/to/Android Studio.app"` to use an installed copy. The
[plugin guide](android-studio-plugin/README.md) also covers sandbox launches and
optional AltSea/Lazulite navigation smoke tests.

When configuration models or editor field descriptions change, run
`uv run python tools/generate_ide_schema.py` and include the regenerated schema.
Maintain descriptions in `android-studio-plugin/schema-descriptions.json`; CI checks
schema drift and documentation coverage. Python remains the source of truth for
the YAML contract and semantic validation.

Build the documentation with `npm ci --prefix docs` and `npm run build --prefix docs`.
See [AGENTS.md](AGENTS.md) for shared repository guidance and
[android-studio-plugin/AGENTS.md](android-studio-plugin/AGENTS.md) for plugin-specific rules.

## License

AASG source code and documentation are licensed under the Apache License 2.0.
Third-party device-frame media retains its own license and provenance. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
