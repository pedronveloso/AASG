---
title: Rendering pipelines
description: Apply typed, validated image and video operations to captured media.
---

A named pipeline is an ordered list of typed operations. Artifacts reference a pipeline
through a rendition. AASG validates its shape before executing FFmpeg or image work.

```yaml
pipelines:
  social-video:
    frame_rate: 30
    crf: 18
    steps:
      - type: gesture_overlay
        color: "#FFFFFF"
        halo_color: "#000000A0"
        radius_px: 44
        trail: true
        motion: standard
```

## Available operations

| Operation | Purpose |
| --- | --- |
| `resize` | Resize with `contain`, `cover`, or `stretch` fit. |
| `crop` | Crop literal coordinates or a named semantic region. |
| `pad` | Place media on a colored canvas. |
| `background` | Apply one color or a theme-keyed color map. |
| `blur` | Blur a frame or image by sigma. |
| `redact` | Blur or cover named semantic regions. |
| `device_frame` | Place media into a verified frame asset. |
| `edge_fade` / `feather` | Fade selected edges or soften the alpha boundary. |
| `trim` / `temporal_fade` | Trim and fade video over time. |
| `gesture_overlay` | Render recorded taps, swipes, and drags over video. |

`gesture_overlay` may appear only once and must be the first step because its
coordinates refer to the untouched source video. It requires a video artifact with
metadata and `show_taps: false` on the capture.

## Process media outside a capture

Run a pipeline against an existing file with the same validation rules:

```shell
aasg process setup-card raw.png --metadata raw.metadata.json \
  --theme light --output card.png
```

Pass `--theme` only when the selected pipeline has a theme-keyed background color.
Detailed field definitions are in the [schema reference](/reference/configuration/#pipelines).
