from __future__ import annotations

from pathlib import Path

import yaml

from aasg.models import AasgConfig


def test_canonical_documentation_config_is_valid_schema_five() -> None:
    root = Path(__file__).parents[1]
    example = root / "docs" / "src" / "content" / "docs" / "reference" / "examples" / "aasg.yaml"

    config = AasgConfig.model_validate(yaml.safe_load(example.read_text(encoding="utf-8")))

    assert config.schema_version == 5
    assert set(config.captures) == {"home", "walkthrough"}
    assert set(config.pipelines) == {"pixel-8", "promo-video"}
