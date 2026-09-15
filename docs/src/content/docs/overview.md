---
title: Overview
description: What AASG is for, and the boundary it keeps with your Android app.
---

AASG is a deterministic Android capture-to-publish orchestrator. It runs app-owned
instrumentation capture tests, collects their AndroidX Test Storage output, and turns
that output into stable screenshots and video renditions.

## Use AASG when

- the Android app already knows how to navigate itself into each capture state;
- you need the same capture across locales, themes, and navigation modes;
- raw captures need repeatable crop, resize, frame, redaction, or video processing;
- generated files need safe, predictable names for a store listing, website, or release.

## Keep these responsibilities in the app

The instrumentation test remains responsible for navigation, fixtures, permissions,
UI synchronization, locale/theme selection, and writing media at the appropriate
moment. AASG intentionally does not introduce another UI automation engine.

## What AASG guarantees

AASG expands configured variants, executes one instrumentation invocation per variant,
copies fresh declared output immediately, validates the result, and atomically replaces
the matching stable rendition only after the complete variant succeeds. It records
versioned manifests and redacted command logs so a published artifact can be traced
back to its configuration and renderer inputs.

Continue with [Quickstart](/getting-started/quickstart/) to make a first configuration.
