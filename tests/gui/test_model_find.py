from pathlib import Path

import pytest
from model_helpers import new_model, us_save

from dq7tt_gui.viewmodels import NoticeKind


def test_find_saves_describes_each_source(tmp_path: Path) -> None:
    us_save(tmp_path)
    found, notices = new_model(tmp_path).find_saves([tmp_path / "sd"])
    assert notices == []
    assert len(found) == 1
    assert "Checkpoint" in found[0].label
    assert found[0].path.is_dir()
    assert found[0].logs_text.endswith("adventure logs")


def test_find_saves_with_nothing_is_empty(tmp_path: Path) -> None:
    assert new_model(tmp_path).find_saves([tmp_path / "none"]) == ([], [])


def test_find_saves_turns_io_errors_into_a_notice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model = new_model(tmp_path)

    def boom(roots: object = None) -> list[object]:
        raise PermissionError("denied")

    monkeypatch.setattr(model, "scan_results", boom)
    found, notices = model.find_saves()
    assert found == []
    assert [n.kind for n in notices] == [NoticeKind.ERROR]
    assert "denied" not in notices[0].text
