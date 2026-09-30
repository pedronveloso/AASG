---
title: aasg.yaml schema
description: Complete reference for the strict, versioned AASG configuration schema.
---

`aasg.yaml` is strict and versioned. Unknown fields, unsafe paths, unsupported schema
versions, missing references, and incompatible pipeline combinations fail before a test
starts. All project-relative paths are resolved from this file.

## Canonical example

The [full canonical configuration](https://github.com/pedronveloso/AASG/blob/main/docs/src/content/docs/reference/examples/aasg.yaml)
is validated through AASG's configuration loader in the Python test suite. It is a
complete, copyable file with an image capture, a video capture, direct instrumentation,
frame sources, and rendering pipelines.

## Top-level fields

| Field | Required | Description |
| --- | --- | --- |
| `schema` | Yes | Must be `9`. Change only when migrating an AASG schema release. |
| `project` | No | Output and timeout defaults. |
| `android` | Yes | Host commands and Android test output settings. |
| `variants` | Yes | Named locale, theme, and capture-group values. |
| `captures` | Yes | Named capture journeys. |
| `pipelines` | No | Named rendering recipes. Defaults to `{}`. |
| `frame_sources` | No | Named remote or local device-frame providers. Defaults to `{}`. |

IDs for locales, themes, groups, captures, pipelines, and frame sources must be
path-safe: they start alphanumeric and then use only letters, digits, `.`, `_`, or `-`.

## `project`

| Field | Default | Rules |
| --- | --- | --- |
| `artifact_root` | `artifacts` | Root for generated publication paths. |
| `run_log_root` | `artifacts/aasg/runs` | Root for manifests and redacted logs. |
| `default_timeout_seconds` | `90` | Positive integer. |

Every generated artifact and rendition path remains inside `artifact_root`.

## `android`

| Field | Required | Default / rules |
| --- | --- | --- |
| `min_api` | No | `33`; integer at least `1`. |
| `adb` | No | `adb`. |
| `gradle_wrapper` | No | `./gradlew`. |
| `prepare_tasks` | No | `[]`; Gradle tasks required before test execution. |
| `test_task` | Yes | Gradle connected-test task. |
| `additional_output_dir` | Yes | AndroidX Test Storage additional-output tree. |
| `locale_argument` | Yes | Instrumentation argument containing the locale value. |
| `theme_argument` | Yes | Instrumentation argument containing the theme value. |
| `direct_instrumentation` | No | Compatibility execution block described below. |

### `android.direct_instrumentation`

Omit this block unless Gradle launches instrumentation with an incompatible symbolic
Android user. `prepare_tasks` still builds both APKs first.

| Field | Required | Rules |
| --- | --- | --- |
| `application_id` | Yes | App package ID. |
| `test_application_id` | Yes | Test APK package ID. |
| `runner` | Yes | Instrumentation runner class. |
| `app_apk` | Yes | App APK path. |
| `test_apk` | Yes | Test APK path. |
| `device_output_dir` | Yes | Safe absolute Android device path; never `/` or a path containing `..`. |

## `variants`

| Field | Required | Description |
| --- | --- | --- |
| `locales` | Yes | Non-empty mapping of locale ID to a human-readable label. |
| `themes` | Yes | Non-empty mapping of theme ID to a human-readable label. |
| `groups` | No | Capture-group ID to capture IDs; defaults to `{}`. Every capture must exist. |

Capture-level `locales` and `themes` can narrow these declared values.

## `captures.<capture-id>`

| Field | Required | Default / rules |
| --- | --- | --- |
| `label` | Yes | Human-readable capture label. |
| `description` | No | Explanatory text shown below the bold label in the interactive picker. |
| `test` | Yes | Instrumentation test class or selector. |
| `arguments` | No | `{}`; string-to-string test arguments. |
| `timeout_seconds` | No | Falls back to `project.default_timeout_seconds`; positive when set. |
| `locales` | No | Selected locale IDs; each must exist in `variants.locales`. |
| `themes` | No | Selected theme IDs; each must exist in `variants.themes`. |
| `navigation` | No | `ignore`; one of `gestural`, `three-button`, `all`, `ignore`. |
| `defaults` | No | `[]`; ordered, typed Android defaults applied before each variant and restored after the run. |
| `show_taps` | No | `true`; controls Android's Show taps setting for video captures. |
| `artifacts` | Yes | Declared files produced by this test. |

Generated filenames contain the theme and, unless `navigation: ignore`, the navigation mode.
A capture containing a video artifact may contain JSON artifacts, but may not mix video
and image artifacts.

### Migrating schema 8 to 9

Set `schema: 9` and remove each artifact's `source`. AASG now infers the Test Storage
source path from the capture ID, artifact type, locale, and theme. Update instrumentation
to write to that path; the Android testkit's `CaptureOutputPaths` builds it for you.
Replace each metadata path with `metadata: true` and write its sidecar beside the media
using `CaptureOutputPaths.metadata(mediaPath)`. Remove `metadata` where no sidecar is
produced. Explicit `source` and metadata path strings are rejected. Publication paths
are unchanged, and previously published files are left in place.

### Migrating schema 7 to 8

Set `schema: 8`. Keep `label` short and move any explanatory text into optional
`description`. Replace each artifact and rendition `publish` file path with its parent
directory in `publish_dir`; keep `source` and `metadata` paths unchanged. Every
`publish_dir` must include `{locale}`. AASG generates the filename from the capture ID,
theme, navigation mode when used, and source extension. Renditions can set `extension`
when their format differs from the source. For example:

```yaml
# Schema 7
publish: screenshots/raw/{locale}/home-device-light-{navigation}.png
# Schema 8
publish_dir: screenshots/raw/{locale}
```

Old stable files are not renamed or deleted; new captures publish to the generated paths.

### `captures.<id>.defaults[]`

Defaults are declarative Android state prerequisites, targeted at the active Android
user. AASG snapshots every successfully inspected target once, applies this capture's
actions before each variant, and restores targets in reverse order after the run.
Warnings while inspecting, applying, or restoring a default are recorded in the run
manifest and do not prevent capture publication; AASG retries application for later
variants. Setting values are never persisted in the run manifest or its events.

| `type` | Required fields | Behavior |
| --- | --- | --- |
| `permission` | `package`, `permission`, `state` | Sets a runtime permission to `granted` or `revoked`. |
| `role` | `role`, `holders` | Sets the exact Android role-holder package list; `holders` may be empty. |
| `setting` | `namespace`, `key`, `value` | Sets a named `system`, `secure`, or `global` setting. `null` deletes it. |

Package, role, permission, and setting-key identifiers are validated. `system.show_touches`
is reserved for the video-aware `show_taps` field and cannot be declared as a default.
Unknown default action types are rejected until a future schema release supports them.

To migrate schema 6 browser routing, replace:

```yaml
browser_role_holder: com.example.app
```

with:

```yaml
defaults:
  - type: role
    role: android.app.role.BROWSER
    holders: [com.example.app]
```

### `captures.<id>.artifacts[]`

| Field | Required | Default / rules |
| --- | --- | --- |
| `id` | Yes | Path-safe artifact ID. |
| `type` | Yes | `image`, `video`, or `json`. |
| `publish_dir` | Yes | Directory below `project.artifact_root`; must contain `{locale}`. |
| `metadata` | No | `false`; set `true` to require a semantic metadata sidecar for an image or video. |
| `renditions` | No | `[]`; rendered publications. |

The inferred Test Storage source is `aasg/screenshots/{locale}/<capture-id>-<theme>.png`
for images, `aasg/videos/{locale}/<capture-id>-<theme>.mp4` for videos, and
`aasg/json/{locale}/<capture-id>-<theme>.json` for JSON. For a capture with multiple
artifacts, insert `-<artifact-id>` after `<capture-id>` in every source filename.
Navigation variants reuse the source name because each variant is collected separately.
With `metadata: true`, AASG also requires a file with the same stem and
`.metadata.json` extension beside the source. Missing media or required metadata fails
the capture. `publish_dir` accepts formatter fields such as `{capture}`, `{locale}`, and
`{theme}`. AASG publishes media as `<capture-id>-<theme>[-<navigation>].<extension>`;
multiple artifacts include `-<artifact-id>` before the theme. Configuration validation
rejects generated publication path collisions.

### `renditions[]`

Each rendition needs `publish_dir` and `pipeline`; optional `extension` overrides the
source file extension. Rendered images support `.png`, `.jpg`, and `.jpeg`; rendered
videos support `.mp4`, `.mov`, `.mkv`, and `.webm`. WebM uses VP9; other video
containers use H.264. The pipeline ID must exist in
`pipelines`. A rendition using `gesture_overlay` requires a video artifact with
`metadata` and `show_taps: false` on its capture.

## `pipelines`

Each named pipeline contains `steps`, plus optional `frame_rate` (default `30`, positive)
and `crf` (default `18`, integer `0`–`51`). A pipeline may contain only one
`gesture_overlay`, and it must be its first step.

| Step `type` | Fields |
| --- | --- |
| `resize` | `width`, `height` (positive); `fit`: `contain` (default), `cover`, or `stretch`. |
| `crop` | Either all of `x`, `y`, `width`, `height`, or `region`; `padding` defaults to `0`. |
| `pad` | Positive `width`, `height`; `color` defaults to `#00000000`. |
| `background` | `color`: one color or a map keyed by theme. |
| `blur` | `sigma`, default `10.0`, positive. |
| `redact` | Non-empty `regions`; `mode`: `blur` (default) or `solid`; `sigma` default `18.0`; `color` default `black`. |
| `device_frame` | `source`, contained relative `frame`; `fit` default `cover`; optional `background`; `crop_to_frame` default `false`. |
| `edge_fade` | Non-empty `edges` from `top`, `right`, `bottom`, `left`; positive `pixels`. |
| `feather` | Positive `pixels`. |
| `trim` | `start_seconds` default `0`; positive `duration_seconds`. |
| `temporal_fade` | `in_seconds` and `out_seconds`, both default `0` and non-negative. |
| `gesture_overlay` | Hex `color` and `halo_color`; `radius_px` default `44`; `trail` default `true`; `timing_offset_ms` from `-10000` to `10000`; `motion`: `standard` (default) or `reduced`. |

## `frame_sources`

| `kind` | Fields |
| --- | --- |
| `device-frames-media` | Optional `index_url`; `allow_unlicensed_downloads`, default `false`. |
| `local` | Required `root` and `license`. |

Remote artwork is never silently refreshed and does not inherit AASG's license. See
[Device frames and licensing](../guides/device-frames/) for the operational contract.
