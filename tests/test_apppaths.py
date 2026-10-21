import logging
from pathlib import Path

import platformdirs
import pytest

from dq7tt import apppaths
from dq7tt.apppaths import (
    APP_NAME,
    AppPaths,
    Settings,
    effective_bank_dir,
    load_settings,
    save_settings,
)
from dq7tt.errors import SaveIOError

REAL_DEFAULT = AppPaths.__dict__["default"]


def test_under_layout(tmp_path: Path) -> None:
    p = AppPaths.under(tmp_path)
    assert p.data_dir == tmp_path / "data"
    assert p.bank_dir == p.data_dir / "bank"
    assert p.backups_dir == p.data_dir / "backups"
    assert p.work_dir == p.data_dir / "work"
    assert p.edited_dir == tmp_path / "edited"
    assert not p.data_dir.exists()


def test_settings_round_trip(tmp_path: Path) -> None:
    p = AppPaths.under(tmp_path)
    s = Settings(bank_dir=tmp_path / "mybank", last_sources=[tmp_path / "a", tmp_path / "b"])
    save_settings(p, s)
    assert load_settings(p) == s
    assert [f.name for f in p.data_dir.iterdir()] == ["settings.json"]


def test_missing_settings_returns_defaults(tmp_path: Path) -> None:
    s = load_settings(AppPaths.under(tmp_path))
    assert s == Settings()
    assert s.last_sources == []


def test_corrupt_settings_returns_defaults(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    p = AppPaths.under(tmp_path)
    p.data_dir.mkdir(parents=True)
    (p.data_dir / "settings.json").write_text("{not json", encoding="utf-8")
    with caplog.at_level(logging.WARNING):
        assert load_settings(p) == Settings()
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_wrong_shape_settings_returns_defaults(tmp_path: Path) -> None:
    p = AppPaths.under(tmp_path)
    p.data_dir.mkdir(parents=True)
    (p.data_dir / "settings.json").write_text('{"last_sources": 5}', encoding="utf-8")
    assert load_settings(p) == Settings()


def test_bank_dir_override(tmp_path: Path) -> None:
    p = AppPaths.under(tmp_path)
    assert effective_bank_dir(p, Settings()) == p.bank_dir
    custom = tmp_path / "custom"
    assert effective_bank_dir(p, Settings(bank_dir=custom)) == custom


def test_save_failure_is_wrapped(tmp_path: Path) -> None:
    blocker = tmp_path / "data"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(SaveIOError):
        save_settings(AppPaths.under(tmp_path), Settings())


def test_default_uses_platformdirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[str, bool]] = []

    def fake_data(appname: str, appauthor: bool = True) -> Path:
        calls.append((appname, appauthor))
        return tmp_path / "appdata"

    monkeypatch.setattr(platformdirs, "user_data_path", fake_data)
    monkeypatch.setattr(platformdirs, "user_documents_path", lambda: tmp_path / "docs")
    monkeypatch.setattr(AppPaths, "default", REAL_DEFAULT)
    p = AppPaths.default()
    assert calls == [(APP_NAME, False)]
    assert p.data_dir == tmp_path / "appdata"
    assert p.bank_dir == tmp_path / "appdata" / "bank"
    assert p.edited_dir == tmp_path / "docs" / APP_NAME / "edited"
    assert apppaths.APP_NAME == "DQ7 Tablet Trader"


def test_binary_settings_returns_defaults(tmp_path: Path) -> None:
    p = AppPaths.under(tmp_path)
    p.data_dir.mkdir(parents=True)
    (p.data_dir / "settings.json").write_bytes(b"\xff\xfe\x00")
    assert load_settings(p) == Settings()
