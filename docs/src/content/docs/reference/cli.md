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

Checks required host programs, connected devices, configuration paths, FFmpeg encoders needed by
configured renditions, and the local cache status of frames referenced by configured pipelines.
Use `--json` for structured output.

## `aasg capture [CAPTURE_IDS...]`

Runs selected capture IDs or groups. Use `--all` to select every capture. Important options are:

| Option | Meaning |
| --- | --- |
| `--device` | Optional ADB device serial. Without it, use the sole online device or prompt when several are online. |
| `--locale` | Declared locale ID, or `all`. |
| `--theme` | Declared theme ID, or `all`. |
| `--navigation` | `gestural`, `three-button`, or `all`; only for captures with `navigation: all`. |
| `--non-interactive` | Reject prompts; with multiple online devices, require `--device`. |
| `--dry-run` | Resolve the matrix and commands without running tooling. |
| `--json` | Emit selected assets and run data as JSON. |

Without explicit arguments, an interactive run can reuse its previous successful capture and variant selection. The device is always resolved from the current ADB list unless `--device` is supplied. That state is outside the project directory.

## `aasg process PIPELINE INPUT`

Applies a named pipeline to an existing file. Use `--output` for the target, `--metadata` for semantic metadata, and `--theme` when a theme-keyed background requires it. `--dry-run` prints the planned renderer commands.

The `--output` suffix must be `.png`, `.jpg`, or `.jpeg` for images, or `.mp4`, `.mov`, `.mkv`, or
`.webm` for videos. When encoding, PNG uses FFmpeg's `png` encoder, JPEG uses `mjpeg`, WebM uses
`libvpx-vp9`, and the other video containers use `libx264`. An ad hoc `aasg process --output`
destination may need an encoder that `aasg doctor` did not check, because doctor checks the
configured renditions. Pipelines with image steps also need `png` for intermediate files; pipelines
with video steps need `ffv1`.

## `aasg frames`

| Command | Behavior |
| --- | --- |
| `aasg frames list SOURCE` | Lists IDs exposed by one remote source. |
| `aasg frames fetch SOURCE FRAME_ID` | Resolves and verifies one frame. Remote sources download it into the cache; local sources read the declared local pack. |
| `aasg frames refresh [SOURCE]` | Refreshes one remote source, or every remote source when `SOURCE` is omitted. |
