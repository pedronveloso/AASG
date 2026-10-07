# AASG Android Studio plugin

The AASG plugin adds configuration completion, documentation, structural validation,
and Android class/method navigation to `aasg.yaml` and `aasg.yml`, using Studio's YAML
editor. Files can be anywhere inside the opened project.

## Install

The first release targets **Android Studio Quail 4 2026.1.4 Patch 1**, platform build
261.26222.65. Compatibility is restricted to branch 261, starting at that build.
The plugin's version is independently maintained at **0.1.0**.

1. Build the ZIP using the instructions below, or download the artifact from the
   repository's **Android Studio plugin** GitHub Actions workflow.
2. Open **Settings → Plugins → gear menu → Install Plugin from Disk** and select
   `build/distributions/aasg-android-studio-0.1.0.zip`.
3. Restart Studio if requested. Open and sync the Android project, then open its
   `aasg.yaml` or `aasg.yml`.

Java, Kotlin, YAML and JSON support must be enabled. These are bundled with the
target Studio installation. No Python or AASG installation is needed for editor
assistance. This release is distributed as a ZIP rather than through Marketplace.

## Editor behavior

```yaml
captures:
  home:
    label: Home
    test: 'com.example.CaptureTest#captureHome, com.example.OtherTest'
```

Use **Cmd-click** on macOS or **Ctrl-click** on Windows/Linux to open a class or
method declaration. **Go to Declaration** works too (Cmd-B / Ctrl-B with the
default keymaps). Classes and methods are separate references. Kotlin references
open Kotlin source declarations; nested classes use JVM notation such as
`com.example.Outer$Nested`. Multiple targets use the IDE's normal target chooser.

Class and method completion is available in `captures.<id>.test`. Classes are
also completed and navigable in `android.direct_instrumentation.runner`, including
runners provided by dependencies. Class resolution prefers project sources across
all imported modules, including instrumentation-test source roots.

Selectors can be plain, single-quoted or double-quoted single-line YAML scalars.
Completion preserves quotes, method suffixes and neighboring selectors. Navigation
does not interpret block scalars, YAML aliases or nonstandard selector syntax.
Unrelated YAML files and similarly named keys elsewhere in the document receive
no AASG Android references.

The bundled schema provides key and enum completion, field documentation, and
diagnostics for required/unknown fields, types, numeric bounds and schema versions.
It supports configuration **schema 9**. Older schemas are flagged, but class
navigation remains available. Missing classes and methods produce warnings after
indexing finishes; sync the project if instrumentation sources are unavailable.

Run `aasg config validate` for the complete validation, including cross-references,
publication templates, pipeline compatibility and filesystem paths. The plugin
does not execute captures or AASG commands.

## Build and verify

Use JDK 21 as the Gradle JVM. From this directory:

```shell
./gradlew checkKotlinFormat test buildPlugin verifyPluginProjectConfiguration verifyPlugin
```

The build downloads pinned Android Studio `2026.1.4.8`. To use an installed copy:

```shell
./gradlew checkKotlinFormat test buildPlugin verifyPluginProjectConfiguration verifyPlugin \
  -PstudioLocalPath="/path/to/Android Studio.app"
```

`./gradlew runIde -PstudioLocalPath="/path/to/Android Studio.app"` launches an
isolated Studio sandbox with the plugin installed. Its settings and plugin
directory live in `.intellijPlatform/sandbox/`; it does not install the plugin
into your regular Studio profile.

Use `./gradlew formatKotlin` to format plugin sources and Gradle Kotlin scripts.

Optional pilot smoke tests read actual Android project configurations and Kotlin
capture sources into isolated IDE fixtures without changing those projects:

```shell
./gradlew test -PstudioLocalPath="/path/to/Android Studio.app" \
  -PaltSeaPath="/path/to/AltSea" -PlazulitePath="/path/to/lazulite-android"
```

These are navigation integration checks against Studio's Java/Kotlin indexes,
not a full Gradle sync or Android instrumentation run.

## Maintain the schema

The JSON Schema is generated from AASG's Python models; field explanations are
maintained in `schema-descriptions.json`. Every field must have a description.
The generator fails on stale field names. From the repository root:

```shell
uv run python tools/generate_ide_schema.py
uv run python tools/generate_ide_schema.py --check
```

Commit the regenerated schema alongside model or description changes. CI checks
that the bundled schema matches the models. Gradle builds consume the checked-in
file and do not require Python. Python model validators are intentionally not
reimplemented in Kotlin.

Source and bundled schema are licensed under the repository's Apache-2.0 license.
