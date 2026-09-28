---
title: Contributing
description: Develop, validate, document, and release AASG safely.
---

Use Python 3.12 or newer and keep mypy strict. After cloning:

```shell
uv sync
npm ci
```

Run the complete Python package gate before finishing a change:

```shell
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build
```

Run the Android testkit checks from `android-testkit` when changing it:

```shell
./gradlew checkKotlinAbi test build generatePomFileForMavenPublication
```

The testkit uses Kotlin explicit API mode and keeps a checked-in ABI baseline. If an API change is
intentional, review its compatibility and version impact, run `./gradlew updateKotlinAbi` from
`android-testkit`, and include the updated baseline in the change. Do not update the baseline merely
to make a failed check pass. Build the documentation independently with `npm ci --prefix docs` and
`npm run build --prefix docs`.

## Keep public contracts synchronized

Configuration schemas, semantic metadata, run manifests, CLI behavior, documented Python
interfaces, and the Android testkit ABI are public APIs. Only a change to a YAML definition or its
meaning requires a schema-version bump, plus model, starter configuration, docs, migration guidance,
and tests together.

Bump the shared application version only for changes to shipped AASG or testkit code or dependencies
used by shipped artifacts. Before 1.0.0, features increment the minor version; compatible fixes and
dependency updates increment the patch version unless incompatible. Documentation, tests, CI
workflows, and build tooling alone do not trigger a version bump. Keep `pyproject.toml`,
`src/aasg/__init__.py`, `uv.lock`, and the testkit's shared release version synchronized when the
version changes.

Use Conventional Commits and validate a local range with:

```shell
npm run commitlint -- --from HEAD~1 --to HEAD
```

Documentation is source code: update the relevant guide and, when appropriate, the canonical configuration example in the same change as the behavior it describes.

## Publishing a release

Publishing a non-prerelease GitHub Release tagged `v<version>` publishes the Python CLI to PyPI and the Android testkit to Maven Central. The tag must match the shared AASG version. PyPI publication uses GitHub Actions Trusted Publishing and does not use a stored PyPI token.
