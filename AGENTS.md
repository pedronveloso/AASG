# Repository Guidance

`AGENTS.md` files are the canonical instruction sources for coding agents. This file applies
throughout the repository; nested files add guidance for their directory trees. Tool-specific
files should point to the applicable guidance rather than repeat it. For Android Studio plugin
work, also read [android-studio-plugin/AGENTS.md](android-studio-plugin/AGENTS.md).

## Product boundary

AASG is an Android capture-to-publish orchestrator. Android instrumentation tests own app-specific
navigation and state. AASG owns the capture matrix, supervised execution, AndroidX Test Storage
collection, semantic metadata, stable artifacts, frame providers, typed FFmpeg recipes, and
verification.

Do not add a new UI automation engine, arbitrary shell hooks, a GUI, device-farm management, store
upload, or bundled FFmpeg/device artwork without an explicit product decision.

## Project map

- `src/aasg/models.py` defines the public YAML and semantic-metadata contracts.
- `src/aasg/cli.py` contains user-facing commands and interaction.
- Android orchestration, artifact collection, frame providers, and media rendering are isolated in
  their corresponding modules under `src/aasg/`.
- `tests/` mirrors behavior at module and CLI boundaries.
- `android-testkit/` contains the Kotlin testkit and its checked-in public ABI baseline.
- `android-studio-plugin/` is the independently versioned Android Studio editor plugin.
- `tools/generate_ide_schema.py` generates the plugin's bundled JSON Schema from the Python
  configuration models, with field documentation from
  `android-studio-plugin/schema-descriptions.json`.

## Engineering rules

- Support Python 3.12+ and keep mypy in strict mode.
- Keep configuration strict, versioned, and free of executable shell snippets.
- Execute external commands as argument arrays with no shell.
- Resolve project paths from `aasg.yaml`; reject traversal outside declared roots.
- Preserve existing stable artifacts until a full replacement variant has been captured, validated,
  and rendered successfully.
- Treat semantic metadata and run manifests as versioned public interfaces.
- Redact device serials and likely credentials from persisted logs.
- Do not silently refresh remote frame assets. Record URLs, hashes, and license provenance.
- Never imply that third-party frame assets inherit AASG's Apache-2.0 license.
- Keep the plugin's bundled schema generated from `AasgConfig.model_json_schema(by_alias=True)`.
  Regenerate it when configuration models or field descriptions change; never hand-edit the
  generated schema. Maintain descriptions for every schema field in the documentation overlay.
  See the plugin's guidance for editor behavior and schema maintenance commands.

## Versioning and commits

- Do not create Git commits unless the user explicitly asks. Leave completed changes uncommitted
  for review; implementing or finishing a task does not authorize a commit.
- Follow Semantic Versioning 2.0.0 for releases. Before 1.0.0, incompatible public-interface
  changes increment the minor version; backwards-compatible fixes increment the patch version.
- Bump the shared application version only when shipped AASG or Android testkit code, or a
  dependency used by either artifact, changes. Features increment the minor version; compatible
  fixes and dependency updates increment the patch version unless they are incompatible before
  1.0.0. Documentation, tests, CI workflows, and build tooling alone do not trigger a version bump.
- Plugin-only changes do not bump the shared AASG/testkit version. Plugin versioning rules
  live in [android-studio-plugin/AGENTS.md](android-studio-plugin/AGENTS.md).
- Treat configuration schemas, semantic metadata, run manifests, CLI behavior, and documented
  Python interfaces as the public API when deciding version impact.
- Increment the top-level `aasg.yaml` schema version only when a YAML definition is added, removed,
  renamed, or changes meaning. Update the model, starter configuration, documentation, tests, and
  maintained pilot configurations together, and document the migration from the previous schema.
- Use Conventional Commit messages that pass commitlint. Prefer the types `feat`, `fix`, `docs`,
  `refactor`, `test`, `build`, `ci`, `chore`, `perf`, and `revert`.
- Mark incompatible changes with `!` in the type/scope or a `BREAKING CHANGE:` footer, and explain
  the affected public interface in the commit body or footer.
- Keep the shared versions in `pyproject.toml`, `src/aasg/__init__.py`, `uv.lock`, and
  `android-testkit/gradle.properties` synchronized.

## Commands

```shell
uv sync
uv run ruff format .
uv run ruff check .
uv run mypy
uv run pytest
uv build
npm ci
npm run commitlint -- --from HEAD~1 --to HEAD
uv run python tools/generate_ide_schema.py --check
```

Use JDK 17 as the Gradle JVM for the Android testkit, and run from the repository root:

```shell
./android-testkit/gradlew -p android-testkit \
  checkKotlinAbi test build generatePomFileForMavenPublication
```

Run the plugin verification commands in
[android-studio-plugin/AGENTS.md](android-studio-plugin/AGENTS.md) as part of the complete gate.

Build and verify documentation with `npm ci --prefix docs` and `npm run build --prefix docs`.

Run focused tests during development and the complete gate before finishing. Media tests should
assert properties such as dimensions, duration, pixel alpha, and stream format rather than encoded
file bytes.

## Definition of done

- Public behavior is documented in `README.md`.
- Every change to shipped AASG or Android testkit code or dependencies includes the appropriate
  application-version bump; documentation, tests, CI, and build tooling changes alone do not.
- Model or editor-description changes include a regenerated bundled schema and passing
  drift/coverage checks. Plugin changes also satisfy its nested definition of done.
- YAML contract changes include a schema-version bump, migration documentation, validation and
  compatibility tests, and updates to maintained pilot configurations.
- New FFmpeg operations include dry-run output and media-property tests.
- Capture failures preserve successful outputs and leave a useful run manifest/log.
- Before completing a task, run the local equivalents of every CI verification, including
  `uv run ruff format --check .`, `uv run ruff check .`, `uv run mypy`, `uv run pytest`, and
  `uv build`.
  Include Android testkit ABI/tests/build, plugin formatting/tests/ZIP/configuration/compatibility
  verification, schema drift, documentation build verification, and commitlint checks above.
- All required checks pass.
