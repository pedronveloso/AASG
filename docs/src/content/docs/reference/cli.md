---
title: CLI reference
description: Commands for configuring, capturing, processing, and managing frames.
---

Commands that load an existing configuration accept `--config` or `-c` for an
`aasg.yaml` path. `aasg init` instead takes an optional destination path. Run `aasg
--help` or `aasg <command> --help` to see Typer's current option descriptions.

## `aasg init [PATH]`

Writes the starter configuration to `PATH`, defaulting to `aasg.yaml`. It refuses to overwrite an existing file.

## `aasg config validate`

Loads and validates the strict YAML contract without connecting to Android. It prints the
schema version plus capture and pipeline counts.

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

## `aasg frames`

| Command | Behavior |
| --- | --- |
| `aasg frames list SOURCE` | Lists IDs exposed by one remote source. |
| `aasg frames fetch SOURCE FRAME_ID` | Resolves and verifies one frame. Remote sources download it into the cache; local sources read the declared local pack. |
| `aasg frames refresh [SOURCE]` | Refreshes one remote source, or every remote source when `SOURCE` is omitted. |
