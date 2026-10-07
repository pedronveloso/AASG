# Android Studio plugin guidance

Read the [repository guidance](../AGENTS.md) first. Its shared engineering, versioning,
verification, and no-commit rules also apply here. This file adds plugin-specific requirements.
For schema tooling or CI changes outside this directory, also consult this guidance when
the change affects the plugin.

## Product boundary

The companion plugin owns editor assistance for `aasg.yaml` and `aasg.yml`: YAML completion,
documentation, structural validation, and Android class/method navigation. Reuse Studio's
YAML editor and Java/Kotlin indexes. Full semantic and filesystem validation remains in
`aasg config validate`; do not duplicate Python semantic validators in Kotlin or execute
capture commands from the plugin.

## Project map

- `src/main/kotlin/` contains schema attachment, references, completion, and inspections.
- `src/main/resources/META-INF/plugin.xml` declares plugin extensions and dependencies.
- `src/main/resources/schemas/aasg.schema.json` is generated and checked in.
- `schema-descriptions.json` maintains documentation for every configuration field.
- `src/test/kotlin/` contains IDE fixtures, including optional maintained-pilot checks.
- `gradle.properties` pins the independent plugin version and Android Studio dependency.
- `build/distributions/` contains the installable ZIP; `build/reports/` contains check reports.
- `../tools/generate_ide_schema.py` generates the bundled schema from the Python models.
- `../.github/workflows/android-studio-plugin.yml` defines plugin CI verification.

## Engineering rules

- Restrict assistance to the supported filenames and exact YAML field paths. Unrelated
  `test` and `runner` keys must retain normal YAML behavior.
- Preserve quoting and neighboring selectors during completion. Keep classes and methods
  separately navigable, including comma-separated selectors and nested classes using JVM `$`.
- Prefer project sources, include instrumentation-test roots, and allow dependency runners.
  Navigate Kotlin references to source declarations and retain the IDE's target chooser.
- Defer index-dependent assistance while Studio is indexing. Tolerate incomplete YAML.
- Keep IDE dependencies and compatibility bounds explicit. The initial target is Studio
  `2026.1.4.8`, platform branch 261 starting at build 261.26222.65. Verify compatibility
  before changing the supported IDE range; use the local installation override for development.
- Build against the checked-in schema without requiring Python on plugin users' machines.
  Regenerate the schema when models or descriptions change; never edit generated schema by hand.
  Keep configuration schema 9 unless the repository's YAML contract rules require a migration.

## Versioning

Version the plugin independently using `pluginVersion` in `gradle.properties`. The initial
version is 0.1.0. Apply the repository's SemVer rules to shipped plugin code, bundled-schema
behavior, editor interfaces, and runtime dependencies. Plugin-only changes do not bump the
shared AASG/testkit version. Documentation, tests, CI, and build tooling alone do not bump
the plugin version.

## Commands

Use JDK 21 as the Gradle JVM. From this directory, run:

```shell
./gradlew checkKotlinFormat test buildPlugin verifyPluginProjectConfiguration verifyPlugin
```

Add `-PstudioLocalPath="/path/to/Android Studio.app"` to use an installed Studio instead
of downloading the pinned release. Format Kotlin sources and Gradle scripts with
`./gradlew formatKotlin`. Launch an isolated Studio sandbox with:

```shell
./gradlew runIde -PstudioLocalPath="/path/to/Android Studio.app"
```

When both maintained Android pilot projects are available, run navigation smoke tests:

```shell
./gradlew test -PstudioLocalPath="/path/to/Android Studio.app" \
  -PaltSeaPath="/path/to/AltSea" -PlazulitePath="/path/to/lazulite-android"
```

The fixtures read those projects without modifying them. They verify navigation through
Studio indexes; they do not perform a full Android Gradle sync or instrumentation run.

From the repository root, maintain and check the bundled schema:

```shell
uv run python tools/generate_ide_schema.py
uv run python tools/generate_ide_schema.py --check
```

Leave regenerated schema changes alongside model or description changes for review.
See [README.md](README.md) for installation and sandbox details.

## Definition of done

- Document public behavior in the root README, plugin README, and documentation site.
- Shipped plugin changes include the appropriate independent plugin-version bump.
- Model or description changes include regenerated schema and passing drift/coverage checks.
- Relevant fixtures cover navigation, completion, documentation, structural diagnostics,
  quoting, ambiguity, missing symbols, indexing, and isolation from unrelated YAML.
- Plugin formatting, tests, ZIP packaging, configuration, and compatibility checks pass,
  along with the repository's complete verification gate.
- Leave an installable ZIP and verification reports. Run pilot navigation smoke tests
  when both maintained Android projects are available.
