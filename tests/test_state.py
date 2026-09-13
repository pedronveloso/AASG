from __future__ import annotations

from pathlib import Path

from aasg.state import load_selection, save_selection, state_path


def test_selection_state_is_keyed_by_canonical_config(tmp_path: Path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    data_root = tmp_path / "user-data"
    monkeypatch.setattr("aasg.state.user_data_path", lambda _name: data_root)
    project = tmp_path / "project"
    project.mkdir()
    config = project / "aasg.yaml"
    config.touch()
    selection = {"device": "emulator-5554", "captures": ["home"]}

    save_selection(config, selection)

    assert load_selection(project / "." / "aasg.yaml") == selection
    assert state_path(config).parent == data_root / "selections"
