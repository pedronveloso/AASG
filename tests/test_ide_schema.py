from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any

from aasg.models import AasgConfig

ROOT = Path(__file__).parents[1]
PLUGIN = ROOT / "android-studio-plugin"


def without_documentation(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: without_documentation(item)
            for key, item in value.items()
            if key not in {"description", "$schema", "$id"}
        }
    if isinstance(value, list):
        return [without_documentation(item) for item in value]
    return value


def test_bundled_schema_preserves_model_contract_and_documents_every_field() -> None:
    schema = json.loads((PLUGIN / "src/main/resources/schemas/aasg.schema.json").read_text())
    assert without_documentation(schema) == without_documentation(
        AasgConfig.model_json_schema(by_alias=True)
    )
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    for model in [schema, *schema["$defs"].values()]:
        for field in model.get("properties", {}).values():
            assert field.get("description"), field


def test_schema_generator_is_deterministic_and_check_does_not_write() -> None:
    namespace = runpy.run_path(str(ROOT / "tools/generate_ide_schema.py"))
    generate = namespace["generate_schema"]
    assert generate() == generate()
    path = PLUGIN / "src/main/resources/schemas/aasg.schema.json"
    before = path.stat().st_mtime_ns
    result = subprocess.run(
        [sys.executable, str(ROOT / "tools/generate_ide_schema.py"), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert path.stat().st_mtime_ns == before
