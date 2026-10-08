"""Select component checks from GitHub event changes using only the standard library."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any

COMPONENTS = ("python", "testkit", "plugin", "documentation")
SHARED = {
    "tools/ci_changes.py",
    "tests/test_ci_changes.py",
    ".github/workflows/ci.yml",
    ".github/workflows/android-studio-plugin.yml",
}
METADATA = {
    "AGENTS.md",
    "CLAUDE.md",
    ".gitignore",
    ".github/FUNDING.yml",
    ".github/dependabot.yml",
    ".github/workflows/opencode-review.yml",
    "package.json",
    "package-lock.json",
    "commitlint.config.mjs",
}
SCHEMA = {
    "src/aasg/models.py",
    "tools/generate_ide_schema.py",
    "tests/test_ide_schema.py",
    "pyproject.toml",
    "uv.lock",
}
DOC_EXAMPLE = "docs/src/content/docs/reference/examples/aasg.yaml"


def select_components(paths: list[str]) -> dict[str, bool]:
    selected = dict.fromkeys(COMPONENTS, False)
    for path in paths:
        if (
            path in METADATA
            or Path(path).name in {"AGENTS.md", "CLAUDE.md"}
            or path.startswith((".opencode/", ".husky/"))
        ):
            continue
        if path in SHARED or path.startswith(".github/actions/detect-changes/"):
            return dict.fromkeys(COMPONENTS, True)
        matched = False
        if path.startswith(("src/", "tests/", "tools/")) or path in {
            "pyproject.toml",
            "uv.lock",
            "README.md",
            "LICENSE",
            "THIRD_PARTY_NOTICES.md",
        }:
            selected["python"] = matched = True
        if path.startswith("android-testkit/"):
            selected["testkit"] = matched = True
        if path.startswith("android-studio-plugin/") or path in SCHEMA or path == "LICENSE":
            selected["plugin"] = matched = True
        if path.startswith("docs/") or path == ".github/workflows/deploy-docs.yml":
            selected["documentation"] = matched = True
        if path == DOC_EXAMPLE:
            selected["python"] = True
        if not matched:
            return dict.fromkeys(COMPONENTS, True)
    return selected


def git_paths(event_name: str, event: dict[str, Any]) -> list[str] | None:
    """Return both sides of renames; None means comparison cannot safely be made."""
    if event_name == "workflow_dispatch":
        return None
    try:
        if event_name == "pull_request":
            base = event["pull_request"]["base"]["sha"]
            head = event["pull_request"]["head"]["sha"]
            separator = "..."
        elif event_name == "push":
            base, head = event["before"], event["after"]
            separator = ".."
        else:
            return None
        # Validate revisions before passing them to Git, including the zero SHA of new refs.
        for revision in (base, head):
            if (
                not isinstance(revision, str)
                or len(revision) != 40
                or any(char not in "0123456789abcdef" for char in revision)
                or revision == "0" * 40
            ):
                return None
        result = subprocess.run(
            ["git", "diff", "--name-only", "--no-renames", "-z", f"{base}{separator}{head}", "--"],
            check=True,
            capture_output=True,
        )
        return [os.fsdecode(path) for path in result.stdout.split(b"\0") if path]
    except (KeyError, TypeError, OSError, subprocess.CalledProcessError):
        return None


def results_pass(needs: dict[str, Any], jobs: dict[str, str]) -> bool:
    """Require detection and all selected jobs to succeed; unrelated jobs may skip."""
    changes = needs.get("changes", {})
    if changes.get("result") != "success":
        return False
    outputs = changes.get("outputs", {})
    for job, component in jobs.items():
        selected = outputs.get(component) if component else "true"
        if selected not in {"true", "false"}:
            return False
        result = needs.get(job, {}).get("result")
        if result != "success" and not (selected == "false" and result == "skipped"):
            return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-results", choices=("ci", "plugin"))
    args = parser.parse_args()
    if args.check_results:
        jobs = (
            {
                "commitlint": "",
                "validate": "python",
                "testkit": "testkit",
                "documentation": "documentation",
            }
            if args.check_results == "ci"
            else {"plugin": "plugin"}
        )
        passed = results_pass(json.loads(os.environ["NEEDS_JSON"]), jobs)
        print(
            "Selected checks passed." if passed else "Change detection or validation did not pass."
        )
        return 0 if passed else 1
    try:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        paths = git_paths(os.environ["GITHUB_EVENT_NAME"], event)
    except (OSError, KeyError, ValueError):
        paths = None
    selected = dict.fromkeys(COMPONENTS, True) if paths is None else select_components(paths)
    if paths is None:
        print("Comparison unavailable or manual run: validating all components.")
    lines = [f"{component}={str(enabled).lower()}" for component, enabled in selected.items()]
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        output.write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
