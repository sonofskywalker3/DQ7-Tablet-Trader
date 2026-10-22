"""Starting the window: the app folder override, and failures at start-up that must show."""

import asyncio
import logging
from pathlib import Path

import flet as ft
import pytest
from test_widgets import texts
from test_window import FakePage

from dq7tt.apppaths import AppPaths
from dq7tt.database import TabletDatabase
from dq7tt_gui import art
from dq7tt_gui import main as gui_main


def test_app_dir_override_moves_every_app_folder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(gui_main.APP_DIR_ENV, str(tmp_path))
    assert gui_main.app_paths() == AppPaths.under(tmp_path)
    monkeypatch.delenv(gui_main.APP_DIR_ENV)
    assert gui_main.app_paths() == AppPaths.default()


def test_run_without_a_writable_log_folder_still_opens(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a folder", encoding="utf-8")
    monkeypatch.setenv(gui_main.APP_DIR_ENV, str(blocker))
    started: list[tuple[object, dict[str, object]]] = []
    monkeypatch.setattr(ft, "run", lambda target, **kw: started.append((target, kw)))
    root = logging.getLogger()
    handlers = list(root.handlers)
    try:
        with caplog.at_level(logging.WARNING):
            gui_main.run()
    finally:
        root.handlers = handlers
    assert started == [(gui_main.main, {"assets_dir": str(art.ASSETS_DIR)})]
    assert "no log file" in caplog.text


def test_a_tablet_list_that_will_not_load_is_shown_in_the_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(gui_main.APP_DIR_ENV, str(tmp_path))
    monkeypatch.delenv(gui_main.SMOKE_ENV, raising=False)

    def broken(cls: type) -> TabletDatabase:
        raise OSError("missing data file")

    monkeypatch.setattr(TabletDatabase, "load", classmethod(broken))
    page = FakePage()
    asyncio.run(gui_main.main(page))  # type: ignore[arg-type]
    shown = [t for c in page.added for t in texts(c)]
    log_file = gui_main.log_file(AppPaths.under(tmp_path))
    assert shown == [gui_main.start_failed_text(AppPaths.under(tmp_path))]
    assert shown[0].startswith(gui_main.START_FAILED) and str(log_file) in shown[0]


def test_start_failure_text_blames_nothing_in_particular() -> None:
    message = gui_main.start_failed_text(None)
    assert "tablets" not in message
    assert "download" in message.lower()
    assert "\N{EM DASH}" not in message
