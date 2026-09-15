---
title: Capture workflow
description: Expand a capture matrix, collect fresh media, and publish stable artifacts safely.
---

## Expand the configured matrix

Each selected capture can run across a declared set of locales, themes, and navigation
modes. AASG invokes instrumentation once per combination so app-owned tests see one
unambiguous requested state at a time.

Use `--all` to select every capture, `--locale all`, `--theme all`, and `--navigation
all` to expand variants. `--navigation` applies only to captures configured with
`navigation: all`.

```shell
aasg capture --all --locale all --theme all --navigation all \
  --device emulator-5554 --non-interactive
```

## Collect only fresh declared output

The normal execution path delegates to the configured Gradle test task and reads its
AndroidX Test Storage additional-output directory. A direct-instrumentation option is
available for Android/AGP user-selection incompatibilities: AASG still builds both
APKs with `prepare_tasks`, resolves the numeric Android user, then launches `am
instrument --user` and pulls the declared Test Storage directory.

## Preserve valid output on failure

A variant is collected and rendered in a run staging directory. AASG validates media,
semantic metadata, and output paths, hashes the artifact, then atomically updates the
stable path. Failed or interrupted variants leave any earlier valid stable output in
place.

Each real run writes a versioned manifest and redacted logs under `project.run_log_root`.
The manifest records the configuration, selection, device model/API, setting changes,
checksums, renderer commands, and frame provenance.

## Use selection deliberately

Interactive runs remember the last successful device, capture, locale, theme, and
navigation selections outside the project. Automation should always include
`--non-interactive` and every relevant selection option. Use `--dry-run` before a
large matrix to inspect it without calling Android tooling.
