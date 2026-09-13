# Repository Guidance

`AGENTS.md` is the canonical instruction source for coding agents. Tool-specific files should point
here rather than repeat it.

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

## Versioning and commits

- Follow Semantic Versioning 2.0.0 for releases. Before 1.0.0, incompatible public-interface
  changes increment the minor version; backwards-compatible fixes increment the patch version.
- Treat configuration schemas, semantic metadata, run manifests, CLI behavior, and documented
  Python interfaces as the public API when deciding version impact.
- Use Conventional Commit messages that pass commitlint. Prefer the types `feat`, `fix`, `docs`,
  `refactor`, `test`, `build`, `ci`, `chore`, `perf`, and `revert`.
- Mark incompatible changes with `!` in the type/scope or a `BREAKING CHANGE:` footer, and explain
  the affected public interface in the commit body or footer.
- Keep the versions in `pyproject.toml` and `src/aasg/__init__.py` synchronized when preparing a
  release.

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
```

Run focused tests during development and the complete gate before finishing. Media tests should
assert properties such as dimensions, duration, pixel alpha, and stream format rather than encoded
file bytes.

## Definition of done

- Public behavior is documented in `README.md`.
- Schema changes include validation and compatibility tests.
- New FFmpeg operations include dry-run output and media-property tests.
- Capture failures preserve successful outputs and leave a useful run manifest/log.
- Ruff formatting/lint, mypy, pytest, and package build pass.
