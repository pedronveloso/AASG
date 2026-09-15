---
title: aasg.yaml schema
description: Complete reference for the strict, versioned AASG configuration schema.
---

`aasg.yaml` is strict and versioned. Unknown fields, unsafe paths, unsupported schema
versions, missing references, and incompatible pipeline combinations fail before a test
starts. All project-relative paths are resolved from this file.

## Canonical example

The [full canonical configuration](https://github.com/pedronveloso/AASG/blob/main/docs/src/content/docs/reference/examples/aasg.yaml)
is validated in AASG's Python test suite. It includes an image capture, a video capture,
direct instrumentation, frame sources, and rendering pipelines.

```yaml
schema: 5
project:
  artifact_root: artifacts
android:
  test_task: ":app:connectedDebugAndroidTest"
variants:
  locales: {en: English}
  themes: {light: Light}
captures: {}
```

## Top-level fields

| Field | Required | Description |
| --- | --- | --- |
| `schema` | Yes | Must be `5`. Change only when migrating an AASG schema release. |
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
| `artifact_root` | `artifacts` | Root for all `publish` paths. |
| `run_log_root` | `artifacts/aasg/runs` | Root for manifests and redacted logs. |
| `default_timeout_seconds` | `90` | Positive integer. |

Every artifact and rendition `publish` path must remain inside `artifact_root`.

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
| `test` | Yes | Instrumentation test class or selector. |
| `arguments` | No | `{}`; string-to-string test arguments. |
| `timeout_seconds` | No | Falls back to `project.default_timeout_seconds`; positive when set. |
| `locales` | No | Selected locale IDs; each must exist in `variants.locales`. |
| `themes` | No | Selected theme IDs; each must exist in `variants.themes`. |
| `navigation` | No | `ignore`; one of `gestural`, `three-button`, `all`, `ignore`. |
| `show_taps` | No | `true`; controls Android's Show taps setting for video captures. |
| `artifacts` | Yes | Declared files produced by this test. |

When `navigation: all`, every artifact and rendition `publish` path must contain a real
`{navigation}` formatter field. This prevents capture modes overwriting one another.
A capture containing a video artifact may contain JSON artifacts, but may not mix video
and image artifacts.

### `captures.<id>.artifacts[]`

| Field | Required | Default / rules |
| --- | --- | --- |
| `id` | Yes | Path-safe artifact ID. |
| `type` | Yes | `image`, `video`, or `json`. |
| `source` | Yes | Exact suffix inside `android.additional_output_dir`. |
| `publish` | Yes | Stable path below `project.artifact_root`. |
| `metadata` | No | Semantic metadata sidecar path. |
| `renditions` | No | `[]`; rendered publications. |

`source`, `publish`, and rendition `publish` accept formatter fields such as
`{capture}`, `{locale}`, `{theme}`, and `{navigation}` when that selection is present.

### `renditions[]`

Each rendition needs `publish` and `pipeline`. The pipeline ID must exist in
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
[Device frames and licensing](/guides/device-frames/) for the operational contract.
