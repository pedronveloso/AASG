---
title: Quickstart
description: Install AASG, connect it to an Android capture test, and run the first capture.
---

## Prerequisites

Use macOS for the supported host experience. Install Python 3.12 or newer, Android
SDK Platform Tools (including ADB), FFmpeg and FFprobe, and an Android project using
AGP 8+ with AndroidX Test Storage. The project also needs a Gradle wrapper.

Install the released command-line tool:

```shell
uv tool install android-automated-screengrabs
# Or: pipx install android-automated-screengrabs
aasg --version
```

Released versions are published on [PyPI](https://pypi.org/project/android-automated-screengrabs/). For a checkout under development, use `uv sync` and run `uv run aasg --help`.

## 1. Write a capture test

Navigate and synchronize inside your app's instrumentation test. When the screen is
ready, write the media to AndroidX Test Storage:

```kotlin
PlatformTestStorageRegistry.getInstance()
  .openOutputFile(CaptureOutputPaths.image("home", "en", "light"))
  .use { output -> bitmap.compress(Bitmap.CompressFormat.PNG, 100, output) }
```

The testkit helper writes `aasg/screenshots/en/home-light.png`, the source path AASG
infers from the capture ID and variant. Use its `video`, `json`, and `metadata` builders
for other artifact types and sidecars.

## 2. Create `aasg.yaml`

From the Android project root, run:

```shell
aasg init
```

The generated file is intentionally small. Update the Gradle task, AndroidX Test
Storage output directory, test class, and publication directories for your project. Read the
[canonical schema example](../../reference/configuration/#canonical-example) before
adding variants and pipelines.

## 3. Validate before running hardware

```shell
aasg config validate
aasg doctor
```

`config validate` catches unknown fields, unsafe paths, missing references, and invalid
recipe combinations. `doctor` checks host tools, devices, and required frame assets.

## 4. Capture one journey

```shell
aasg capture home
```

For CI or repeatable automation, make the selection explicit:

```shell
aasg capture home --device emulator-5554 --locale en --theme light --non-interactive
```

Add `--navigation gestural` or `--navigation three-button` only when the selected
capture uses `navigation: all`. AASG includes the navigation mode in each generated
filename, so variants publish separately.

Use `--dry-run` to inspect the selected matrix and commands without invoking Android
tooling. A real run creates a run manifest and command logs under the configured
run-log root, then prints the generated artifact paths.

Next, learn how [the Android test contract](../../concepts/android-test-contract/) and
the [capture workflow](../../guides/capture-workflow/) fit together.
