from __future__ import annotations

import json
import os
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "tools/ci_changes.py"
CI = runpy.run_path(str(SCRIPT))
ALL = {"python", "testkit", "plugin", "documentation"}


@pytest.mark.parametrize(
    ("paths", "expected"),
    [
        (["android-studio-plugin/src/main/kotlin/Editor.kt"], {"plugin"}),
        (["android-studio-plugin/schema-descriptions.json"], {"plugin"}),
        (["android-testkit/gradle.properties"], {"testkit"}),
        (["src/aasg/media.py", "tests/test_media.py"], {"python"}),
        (["tools/new_tool.py"], {"python"}),
        (["docs/src/content/docs/overview.md"], {"documentation"}),
        (["src/aasg/models.py"], {"python", "plugin"}),
        (["tools/generate_ide_schema.py"], {"python", "plugin"}),
        (["tests/test_ide_schema.py"], {"python", "plugin"}),
        (["pyproject.toml", "uv.lock"], {"python", "plugin"}),
        ([CI["DOC_EXAMPLE"]], {"python", "documentation"}),
        (["android-testkit/build.gradle.kts", "src/aasg/cli.py"], {"python", "testkit"}),
        (["README.md", "THIRD_PARTY_NOTICES.md"], {"python"}),
        (["LICENSE"], {"python", "plugin"}),
        ([".github/workflows/deploy-docs.yml"], {"documentation"}),
        ([".github/workflows/ci.yml"], ALL),
        ([".github/workflows/android-studio-plugin.yml"], ALL),
        ([".github/actions/detect-changes/action.yml"], ALL),
        (["tools/ci_changes.py", "tests/test_ci_changes.py"], ALL),
        (["unclassified/new-file.txt"], ALL),
        ([".github/workflows/publish-testkit.yml"], ALL),
        (["AGENTS.md", "android-studio-plugin/AGENTS.md", ".opencode/agent/pr-review.md"], set()),
        ([".github/FUNDING.yml", "package-lock.json", ".husky/commit-msg"], set()),
        ([], set()),
    ],
)
def test_component_selection(paths: list[str], expected: set[str]) -> None:
    selected = CI["select_components"](paths)
    assert {name for name, enabled in selected.items() if enabled} == expected


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    # These commits exist only in an isolated temporary fixture repository.
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    for role in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{role}_NAME", "CI fixture")
        monkeypatch.setenv(f"GIT_{role}_EMAIL", "fixture@example.invalid")
    git(tmp_path, "init", "-b", "main")
    (tmp_path / "src/aasg").mkdir(parents=True)
    (tmp_path / "src/aasg/media.py").write_text("original\n")
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "-m", "fixture base")
    base = git(tmp_path, "rev-parse", "HEAD")
    monkeypatch.chdir(tmp_path)
    return tmp_path, base


def commit(repo: Path) -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "fixture change")
    return git(repo, "rev-parse", "HEAD")


def test_fork_pr_uses_merge_base_instead_of_base_branch_changes(
    history: tuple[Path, str],
) -> None:
    repo, _ = history
    git(repo, "checkout", "-b", "fork-pr")
    (repo / "android-studio-plugin").mkdir()
    (repo / "android-studio-plugin/Editor.kt").write_text("plugin\n")
    head = commit(repo)
    git(repo, "checkout", "main")
    (repo / "src/aasg/media.py").write_text("main advanced\n")
    base = commit(repo)
    paths = CI["git_paths"](
        "pull_request",
        {"pull_request": {"base": {"sha": base}, "head": {"sha": head, "repo": {"fork": True}}}},
    )
    assert paths == ["android-studio-plugin/Editor.kt"]


def test_push_includes_all_commits_deletions_and_both_sides_of_renames(
    history: tuple[Path, str],
) -> None:
    repo, base = history
    (repo / "android-studio-plugin").mkdir()
    (repo / "src/aasg/media.py").rename(repo / "android-studio-plugin/renamed.kt")
    commit(repo)
    (repo / "docs").mkdir()
    (repo / "docs/deleted.md").write_text("delete me\n")
    before_deletion = commit(repo)
    (repo / "docs/deleted.md").unlink()
    (repo / "android-testkit").mkdir()
    (repo / "android-testkit/new.kt").write_text("testkit\n")
    head = commit(repo)
    paths = CI["git_paths"]("push", {"before": base, "after": head})
    assert set(paths) == {
        "src/aasg/media.py",
        "android-studio-plugin/renamed.kt",
        "android-testkit/new.kt",
    }
    assert CI["git_paths"]("push", {"before": before_deletion, "after": head}) == [
        "android-testkit/new.kt",
        "docs/deleted.md",
    ]
    assert CI["select_components"](paths) == {
        "python": True,
        "testkit": True,
        "plugin": True,
        "documentation": False,
    }


@pytest.mark.parametrize("base", ["0" * 40, "f" * 40, "--invalid", None])
def test_unavailable_push_history_runs_all_checks(
    history: tuple[Path, str], base: str | None, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, head = history
    event = repo / "event.json"
    event.write_text(json.dumps({"before": base, "after": head}))
    output = repo / "output.txt"
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event))
    monkeypatch.setenv("GITHUB_EVENT_NAME", "push")
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    result = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert set(output.read_text().splitlines()) == {f"{name}=true" for name in ALL}


def test_manual_and_unknown_events_run_all_checks() -> None:
    assert CI["git_paths"]("workflow_dispatch", {}) is None
    assert CI["git_paths"]("unknown", {}) is None
    assert CI["git_paths"]("pull_request", {}) is None


def needs_for_plugin(selected: str, result: str) -> dict[str, Any]:
    return {
        "changes": {"result": "success", "outputs": {"plugin": selected}},
        "plugin": {"result": result},
    }


@pytest.mark.parametrize("result", ["success", "skipped", "failure", "cancelled"])
@pytest.mark.parametrize("selected", ["true", "false"])
def test_result_gate(selected: str, result: str) -> None:
    expected = result == "success" or (selected == "false" and result == "skipped")
    assert CI["results_pass"](needs_for_plugin(selected, result), {"plugin": "plugin"}) == expected


@pytest.mark.parametrize("result", ["skipped", "failure", "cancelled"])
def test_detection_failure_blocks_gate(result: str) -> None:
    needs = needs_for_plugin("false", "skipped")
    needs["changes"]["result"] = result
    assert not CI["results_pass"](needs, {"plugin": "plugin"})


def test_missing_selection_or_job_blocks_gate() -> None:
    assert not CI["results_pass"](needs_for_plugin("", "skipped"), {"plugin": "plugin"})
    assert not CI["results_pass"]({}, {"plugin": "plugin"})
    assert not CI["results_pass"](needs_for_plugin("true", "success"), {"missing": "plugin"})


def test_ci_gate_always_requires_commitlint_and_checks_every_selected_component() -> None:
    jobs = {
        "commitlint": "",
        "validate": "python",
        "testkit": "testkit",
        "documentation": "documentation",
    }
    needs: dict[str, Any] = {
        "changes": {"result": "success", "outputs": dict.fromkeys(ALL, "false")},
        **{job: {"result": "skipped"} for job in jobs},
    }
    assert not CI["results_pass"](needs, jobs)
    needs["commitlint"]["result"] = "success"
    assert CI["results_pass"](needs, jobs)
    needs["changes"]["outputs"]["python"] = "true"
    assert not CI["results_pass"](needs, jobs)
    needs["validate"]["result"] = "success"
    assert CI["results_pass"](needs, jobs)


def test_workflows_preserve_job_conditions_and_always_run_result_gates() -> None:
    import yaml

    ci = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())["jobs"]
    plugin = yaml.safe_load((ROOT / ".github/workflows/android-studio-plugin.yml").read_text())[
        "jobs"
    ]
    for job, component in (
        ("validate", "python"),
        ("testkit", "testkit"),
        ("documentation", "documentation"),
    ):
        assert ci[job]["needs"] == "changes"
        assert ci[job]["if"] == f"needs.changes.outputs.{component} == 'true'"
    assert ci["validate"]["strategy"]["matrix"]["os"] == ["ubuntu-latest", "macos-14"]
    assert "needs" not in ci["commitlint"] and "if" not in ci["commitlint"]
    assert plugin["plugin"]["if"] == "needs.changes.outputs.plugin == 'true'"
    for jobs in (ci, plugin):
        assert jobs["result"]["if"] == "always()"
        assert set(jobs["result"]["needs"]) == set(jobs) - {"result"}
        assert jobs["changes"]["steps"][0]["with"]["fetch-depth"] == 0
