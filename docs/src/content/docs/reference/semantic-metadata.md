---
title: Semantic metadata
description: Versioned sidecar data for named regions and video gesture timelines.
---

Artifacts can name a JSON `metadata` sidecar. AASG validates it before using a semantic region for crop/redaction or a gesture timeline for a video overlay.

## Schema 1: image regions

```json
{
  "schema": 1,
  "media": "home-light.png",
  "regions": {
    "setup-tips": {"x": 42, "y": 560, "width": 996, "height": 480}
  }
}
```

`regions` is required. Coordinates are non-negative integer pixels with a top-left origin; `width` and `height` must be positive. Schema 1 does not support gestures.

## Schema 2: video gestures

```json
{
  "schema": 2,
  "media": "onboarding-light.mp4",
  "coordinate_space": {"width": 1080, "height": 2400, "origin": "top-left"},
  "gestures": [
    {"type": "tap", "at_ms": 700, "cue_lead_ms": 120, "x": 540, "y": 1800},
    {
      "type": "swipe",
      "at_ms": 2420,
      "cue_lead_ms": 120,
      "duration_ms": 450,
      "from": {"x": 900, "y": 1200},
      "to": {"x": 180, "y": 1200}
    }
  ]
}
```

Schema 2 requires `coordinate_space`; its width and height are positive and its origin is `top-left`. Gesture events must be sorted by `at_ms`, and every coordinate must fit inside that space.

| Gesture | Required fields |
| --- | --- |
| `tap` | `at_ms`, `x`, `y`; optional non-negative `cue_lead_ms` (default `0`). |
| `swipe` | `at_ms`, positive `duration_ms`, `from`, `to`; optional `cue_lead_ms`. |
| `drag` | `at_ms`, at least two `points`; optional `cue_lead_ms`. Each point has `offset_ms`, `x`, `y`; first offset is `0` and later offsets strictly increase. |

`at_ms` starts the visual cue. The wrapped test action begins `cue_lead_ms` later. Rendering rejects unsorted events, out-of-bounds coordinates, media-dimension mismatch, and gestures extending beyond the decoded video.
