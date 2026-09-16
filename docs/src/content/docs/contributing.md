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

Run the Android testkit checks from `android-testkit` when changing it. Build the documentation independently with `npm ci --prefix docs` and `npm run build --prefix docs`.

## Keep public contracts synchronized

Configuration schemas, semantic metadata, run manifests, CLI behavior, and documented Python interfaces are public APIs. A change to YAML meaning requires a schema-version bump plus model, starter configuration, docs, migration guidance, and tests together.

Every completed feature increments AASG's minor version before 1.0.0; compatible fixes increment the patch version. Keep `pyproject.toml`, `src/aasg/__init__.py`, and `uv.lock` synchronized. Update the testkit's shared release version when its published artifact changes with AASG.

Use Conventional Commits and validate a local range with:

```shell
npm run commitlint -- --from HEAD~1 --to HEAD
```

Documentation is source code: update the relevant guide and, when appropriate, the canonical configuration example in the same change as the behavior it describes.
