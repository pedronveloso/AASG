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

## Selective CI validation

Both pull requests and pushes to `main` select checks from changed files:

| Changed files | Validation |
| --- | --- |
| `src/`, `tests/`, `tools/`, `pyproject.toml`, `uv.lock` | Python formatting, lint, types, tests, and packaging on Ubuntu and macOS |
| `android-testkit/` | Android testkit ABI, tests, build, and publication metadata |
| `android-studio-plugin/` | IDE plugin schema contract/documentation, formatting, tests, ZIP, and compatibility |
| `src/aasg/models.py`, schema generator/tests, `pyproject.toml`, `uv.lock` | Also IDE plugin validation |
| `docs/`, documentation deployment workflow | Documentation build |
| Canonical `reference/examples/aasg.yaml` | Also Python validation |
| Root README, license, third-party notices | Python packaging validation through the Python gate |
| Root `LICENSE` | Also IDE plugin validation, since the plugin packages it |
| Shared detector/action/tests or either primary validation workflow | All components |

Commitlint always runs. PR comparisons use the merge base of the base and head revisions,
including fork PRs; pushes compare the previous revision with the new revision across all
pushed commits. Deleted paths and both sides of renames participate in selection. Unknown
paths or unavailable history run all checks rather than silently skipping validation.

Repository guidance (`AGENTS.md`, `CLAUDE.md`), `.opencode/`, the automated review workflow,
`.husky/`, root commitlint/npm configuration, `.gitignore`, funding, and Dependabot configuration
do not trigger component checks. Plugin-only changes still run focused Python schema tests
but skip the full Python matrix and testkit. Manual plugin runs always validate the plugin.

Unrelated jobs are skipped through job conditions; the workflows themselves remain triggered.
The **CI result** and **Plugin result** checks always run and require successful detection and
successful selected checks. Failures, cancellations, and unexpected skips fail these result
checks. They can be configured as required checks in branch protection; repository settings
are not changed by the workflows. Publishing, documentation deployment, and automated review
keep their existing triggers. Selective CI does not replace the complete local verification
gate required by `AGENTS.md`.

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
