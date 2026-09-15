---
title: Device frames and licensing
description: Use frame assets with explicit provenance instead of silently bundled artwork.
---

Frame artwork is not bundled with AASG. A `device_frame` pipeline step refers to a
named source and frame ID; AASG records the URL, checksums, and license provenance.

## Remote source

The `device-frames-media` source reads a public index and downloads only the selected
frame, mask, and geometry. Its catalog has no recognized license, so a configuration
must explicitly acknowledge that before a download:

```yaml
frame_sources:
  community:
    kind: device-frames-media
    allow_unlicensed_downloads: true
```

Downloaded artwork does not inherit AASG's Apache-2.0 license. You are responsible for
deciding whether a particular use is permitted.

## Local source

Use a project-local frame pack when you can provide the license yourself:

```yaml
frame_sources:
  product-frames:
    kind: local
    root: frames
    license: "CC-BY-4.0"
```

The pack's `template.json` describes `frame`, `mask`, `screen`, and `frameSize`, plus
SHA-256 checksums for both artwork files. AASG verifies the checksums, image size, and
screen crop bounds before use.

## Manage cache deliberately

Indexes are not silently refreshed. Inspect, fetch, or refresh a remote catalog
explicitly:

```shell
aasg frames list community
aasg frames fetch community android-phone/pixel-8/hazel
aasg frames refresh community
```
