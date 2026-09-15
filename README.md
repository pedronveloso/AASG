# AASG

AASG is a deterministic, code-first Android capture-to-publish tool. It runs capture
journeys that already live in Android instrumentation tests, collects AndroidX Test
Storage output, and turns it into repeatable screenshots, cut-outs, and framed video.

AASG deliberately does not replace Compose testing, UI Automator, Gradle, ADB, or
FFmpeg. The app owns navigation and state; AASG owns the capture matrix, collection,
metadata, rendering recipes, and stable output.

## Documentation

The full guide covers first capture, the Android test contract, rendering, device-frame
licensing, the complete `aasg.yaml` schema, semantic metadata, and every CLI command:

- [AASG documentation](https://pedronveloso.github.io/AASG/)
- [Agent-readable Markdown index](https://pedronveloso.github.io/AASG/llms.txt)

The site is initially served from GitHub Pages. It will move to
`https://aasg.pedronveloso.com/` once the custom-domain DNS record is configured.

## Requirements

- Python 3.12 or newer
- An Android project using AGP 8+ and AndroidX Test Storage
- ADB from Android SDK Platform Tools
- A project Gradle wrapper
- FFmpeg and FFprobe

## Install and run

```shell
uv tool install android-automated-screengrabs
aasg init
aasg config validate
aasg doctor
aasg capture
```

For source development, run `uv sync` and then `uv run aasg --help`.

## Development

```shell
uv run ruff format --check .
uv run ruff check .
uv run mypy
uv run pytest
uv build
npm ci
npm run commitlint -- --from HEAD~1 --to HEAD
```

Build the documentation with `npm ci --prefix docs` and `npm run build --prefix docs`.

## License

AASG source code and documentation are licensed under the Apache License 2.0.
Third-party device-frame media retains its own license and provenance. See
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
