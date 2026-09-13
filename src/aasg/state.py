"""Per-user selection state."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from platformdirs import user_data_path


def state_path(config_path: Path) -> Path:
    key = hashlib.sha256(str(config_path.resolve()).encode()).hexdigest()[:16]
    return user_data_path("aasg") / "selections" / f"{key}.json"


def load_selection(config_path: Path) -> dict[str, Any] | None:
    path = state_path(config_path)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None
    return value if isinstance(value, dict) else None


def save_selection(config_path: Path, selection: dict[str, Any]) -> None:
    path = state_path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(selection, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
