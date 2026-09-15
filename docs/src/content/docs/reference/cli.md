---
title: CLI reference
description: Commands for configuring, capturing, processing, and managing frames.
---

All commands accept `--config` or `-c` for an `aasg.yaml` path. Run `aasg --help` or
`aasg <command> --help` to see Typer's current option descriptions.

## `aasg init [PATH]`

Writes the starter configuration to `PATH`, defaulting to `aasg.yaml`. It refuses to overwrite an existing file.

## `aasg config validate`

Loads and validates the strict YAML contract without connecting to Android. It reports the schema version and declared captures, locales, and themes.

## `aasg doctor`

Checks required host programs, connected devices, configuration paths, and the local cache status of frames referenced by configured pipelines. Use `--json` for structured output.

## `aasg capture [CAPTURE_IDS...]`

Runs selected capture IDs or groups. Use `--all` to select every capture. Important options are:

| Option | Meaning |
| --- | --- |
| `--device` | ADB device serial or selector. |
| `--locale` | Declared locale ID, or `all`. |
| `--theme` | Declared theme ID, or `all`. |
| `--navigation` | `gestural`, `three-button`, or `all`; only for captures with `navigation: all`. |
| `--non-interactive` | Reject prompts and require explicit valid choices. |
| `--dry-run` | Resolve the matrix and commands without running tooling. |
| `--json` | Emit selected assets and run data as JSON. |

Without explicit arguments, an interactive run can reuse its previous successful selection. That state is outside the project directory.

## `aasg process PIPELINE INPUT`

Applies a named pipeline to an existing file. Use `--output` for the target, `--metadata` for semantic metadata, and `--theme` when a theme-keyed background requires it. `--dry-run` prints the planned renderer commands.

## `aasg frames list|fetch|refresh SOURCE`

`list` shows IDs exposed by a remote source. `fetch` caches one supplied frame ID. `refresh` updates the cached remote index only when requested. These commands do not operate on local sources.
