from __future__ import annotations

from pathlib import Path

from aasg.config import load_config


def test_canonical_documentation_config_is_valid_schema_seven() -> None:
    root = Path(__file__).parents[1]
    example = root / "docs" / "src" / "content" / "docs" / "reference" / "examples" / "aasg.yaml"

    config = load_config(example)

    assert config.schema_version == 7
    assert set(config.captures) == {"home", "walkthrough"}
    assert set(config.pipelines) == {"pixel-8", "promo-video"}
