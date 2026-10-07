---
title: Android Studio plugin
description: Edit AASG configuration with completion, validation and Android source navigation.
---

The **AASG** Android Studio plugin adds YAML configuration assistance and navigation
to the instrumentation tests that own your captures. Version 0.1.0 targets Android
Studio Quail 4 2026.1.4 Patch 1, with compatibility restricted to platform branch
261 starting at build 261.26222.65.

## Install the plugin

Download the installable ZIP artifact from the repository's **Android Studio
plugin** workflow, or build it following the
[plugin README](https://github.com/pedronveloso/AASG/blob/main/android-studio-plugin/README.md).
In Studio, open **Settings → Plugins → gear menu → Install Plugin from Disk**,
choose the ZIP, and restart if requested.

Keep Studio's bundled Java, Kotlin, YAML and JSON support enabled. Open and sync
your Android project, then open `aasg.yaml` or `aasg.yml` anywhere within it.
The editor assistance works without Python or AASG installed.

## Navigate to capture code

```yaml
captures:
  home:
    label: Home
    test: 'com.example.CaptureTest#captureHome, com.example.OtherTest'
```

Cmd-click on macOS, or Ctrl-click on Windows/Linux, on a class or method name to
open its declaration. **Go to Declaration** (Cmd-B / Ctrl-B with default keymaps)
also works. Kotlin classes open their Kotlin sources. If several declarations or
method overloads match, Studio offers its normal target chooser.

Navigation and completion are available in `captures.<id>.test` and in the class
name at `android.direct_instrumentation.runner`. Test selectors support classes,
`Class#method`, comma-separated selectors and nested classes using JVM `$` notation.
Use plain, single-quoted or double-quoted single-line values; block scalars and
YAML aliases are not interpreted as Android references.

Project source declarations are preferred, including imported instrumentation-test
roots across modules. Dependency classes can also resolve, including test runners.
Index-dependent assistance pauses during indexing; unresolved recognized classes
and methods produce warnings afterwards. Sync the project if test sources are missing.

## Configuration assistance

The bundled schema provides normal YAML highlighting, AASG key and enum completion,
field documentation, and structural diagnostics. It checks required and unknown
fields, types, numeric constraints and schema versions. Configuration schema 9 is
supported; older versions receive diagnostics while class navigation still works.

Use `aasg config validate` for full semantic and filesystem validation, including
cross-references, publication templates and pipeline compatibility. The plugin
does not run capture commands. Its schema is bundled, so assistance does not
depend on remote schema downloads.
