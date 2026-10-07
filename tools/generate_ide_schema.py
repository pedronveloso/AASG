"""Generate the plugin's bundled schema without changing AASG's public contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aasg.models import CONFIG_SCHEMA_VERSION, AasgConfig

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "android-studio-plugin"
SCHEMA = PLUGIN / "src/main/resources/schemas/aasg.schema.json"
DESCRIPTIONS = PLUGIN / "schema-descriptions.json"


def generate_schema() -> dict[str, Any]:
    schema = AasgConfig.model_json_schema(by_alias=True)
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = f"urn:aasg:configuration:schema:{CONFIG_SCHEMA_VERSION}"
    schema["description"] = (
        "AASG Android capture-to-publish configuration. "
        "Run aasg config validate for full semantic and filesystem validation."
    )
    descriptions = json.loads(DESCRIPTIONS.read_text(encoding="utf-8"))
    for model_name, fields in descriptions.items():
        model = schema if model_name == "AasgConfig" else schema["$defs"][model_name]
        for field, description in fields.items():
            # Fail on stale documentation rather than quietly dropping it.
            model["properties"][field]["description"] = description
    return schema


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if the bundled schema is stale")
    args = parser.parse_args()
    expected = json.dumps(generate_schema(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if args.check:
        if not SCHEMA.exists() or SCHEMA.read_text(encoding="utf-8") != expected:
            print("Bundled IDE schema is stale. Run: uv run python tools/generate_ide_schema.py")
            return 1
        print("Bundled IDE schema matches AASG models and field documentation.")
        return 0
    SCHEMA.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA.write_text(expected, encoding="utf-8")
    print(f"Generated {SCHEMA.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
