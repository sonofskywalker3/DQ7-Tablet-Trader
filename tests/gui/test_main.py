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


def test_android_paths_keep_settings_private_and_the_bank_visible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(gui_main.APP_DIR_ENV, raising=False)
    monkeypatch.setenv("FLET_APP_STORAGE_DATA", str(tmp_path / "private"))
    monkeypatch.setenv("EXTERNAL_STORAGE", str(tmp_path / "storage"))
    paths = gui_main.app_paths(android=True)
    assert paths == AppPaths.for_android(
        tmp_path / "private", tmp_path / "storage" / "DQ7 Tablet Trader"
    )


def test_profile_follows_the_page_platform() -> None:
    from dq7tt_gui.device_profile import ANDROID_PROFILE, DESKTOP_PROFILE

    assert gui_main.on_android(ft.PagePlatform.ANDROID)
    assert not gui_main.on_android(ft.PagePlatform.WINDOWS)
    assert not gui_main.on_android(None)
    assert gui_main.profile_for(True) is ANDROID_PROFILE
    assert gui_main.profile_for(False) is DESKTOP_PROFILE


@pytest.mark.parametrize(("android", "level"), [(False, logging.NOTSET), (True, logging.DEBUG)])
def test_key_names_are_written_only_on_android(tmp_path: Path, android: bool, level: int) -> None:
    keys = logging.getLogger("dq7tt_gui.controller")
    root = logging.getLogger()
    handlers, before = list(root.handlers), keys.level
    keys.setLevel(logging.NOTSET)
    try:
        gui_main.setup_logging(AppPaths.under(tmp_path), android=android)
        assert keys.level == level
    finally:
        for handler in root.handlers[len(handlers) :]:
            handler.close()
        root.handlers = handlers
        keys.setLevel(before)
