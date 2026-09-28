from __future__ import annotations

from pathlib import Path


def test_pypi_release_workflow_uses_trusted_publishing() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "publish-pypi.yml").read_text()

    assert "types: [published]" in workflow
    assert "github.event.release.prerelease == false" in workflow
    assert "name: pypi" in workflow
    assert "id-token: write" in workflow
    assert "pypa/gh-action-pypi-publish@release/v1" in workflow
    assert 'test "${GITHUB_REF_NAME}" = "v${version}"' in workflow
