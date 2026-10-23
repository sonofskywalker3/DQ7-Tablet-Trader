"""The Android first-run screen and how the window takes over from it (no real page)."""

import asyncio
from pathlib import Path

import flet as ft
import flet_permission_handler as fph
import pytest
from test_session import ticking_clock
from test_sources import AZAHAR_PATH, fill
from test_widgets import buttons, texts
from test_window import FakePage

from dq7tt.apppaths import AppPaths, Settings, load_settings, save_settings
from dq7tt_gui import android_setup
from dq7tt_gui import main as gui_main
from dq7tt_gui.android_setup import AndroidSetup, setup_view, window_width
from dq7tt_gui.device_profile import ANDROID_PROFILE
from dq7tt_gui.model import AppModel
from dq7tt_gui.model_setup import NOT_AZAHAR, SetupModel, SetupStep, screen_copy
from dq7tt_gui.viewmodels import PaneSide
from dq7tt_gui.window import Window

US_SET = "us_postgame"
THOR_W, SMALL_W = 832.0, 640.0


class FakeHandler:
    def __init__(self, granted: bool) -> None:
        self.granted = granted
        self.requests = 0

    async def get_status(self, _permission: object) -> fph.PermissionStatus:
        return fph.PermissionStatus.GRANTED if self.granted else fph.PermissionStatus.DENIED

    async def request(self, _permission: object) -> fph.PermissionStatus:
        self.requests += 1
        return await self.get_status(_permission)


class FakePicker:
    def __init__(self, path: str | None) -> None:
        self.path = path

    async def get_directory_path(self, **_kw: object) -> str | None:
        return self.path


def world(tmp_path: Path) -> tuple[AppPaths, Path, Path]:
    paths = AppPaths.for_android(tmp_path / "private", tmp_path / "storage" / "DQ7 Tablet Trader")
    user = tmp_path / "storage" / "Azahar"
    save = fill(user / AZAHAR_PATH.removeprefix("user/"), US_SET)
    return paths, user, save


def start(
    tmp_path: Path, granted: bool, picked: str | None = None, width: float = THOR_W
) -> tuple[AndroidSetup, Window, FakePage, Path, Path]:
    paths, user, save = world(tmp_path)
    page = FakePage(width)
    page.platform = ft.PagePlatform.ANDROID
    model = AppModel(paths, ANDROID_PROFILE, clock=ticking_clock())
    win = Window(page, model)  # type: ignore[arg-type]
    setup = AndroidSetup(page, SetupModel(paths), win.show)  # type: ignore[arg-type]
    setup.handler = FakeHandler(granted)  # type: ignore[assignment]
    setup.picker = FakePicker(picked)  # type: ignore[assignment]
    asyncio.run(setup.start())
    return setup, win, page, user, save


def shown_texts(page: FakePage) -> list[str]:
    return [t for c in page.controls for t in texts(c)]


def resume() -> ft.AppLifecycleStateChangeEvent:
    return ft.AppLifecycleStateChangeEvent(
        name="app_lifecycle_state_change", control=None, state=ft.AppLifecycleState.RESUME
    )  # type: ignore[arg-type]


def test_without_access_the_access_screen_shows(tmp_path: Path) -> None:
    setup, _, page, _, _ = start(tmp_path, granted=False)
    copy = screen_copy(SetupStep.NEED_ACCESS)
    assert shown_texts(page)[:2] == [copy.title, copy.body]
    assert [b for c in page.controls for b in buttons(c)]
    assert page.on_keyboard_event is None


def test_allow_access_asks_android_then_checks_again(tmp_path: Path) -> None:
    setup, _, page, _, _ = start(tmp_path, granted=False)
    setup.handler.granted = True  # type: ignore[attr-defined]
    asyncio.run(setup.ask_access())
    assert setup.handler.requests == 1  # type: ignore[attr-defined]
    assert shown_texts(page)[0] == screen_copy(SetupStep.NEED_FOLDER).title


def test_coming_back_with_access_moves_on_and_revoked_brings_it_back(tmp_path: Path) -> None:
    paths, user, _ = world(tmp_path)
    save_settings(paths, Settings(azahar_dir=user))
    setup, win, page, _, _ = start(tmp_path, granted=False)
    setup.handler.granted = True  # type: ignore[attr-defined]
    asyncio.run(setup.on_lifecycle(resume()))
    assert page.controls == [win.root] and win.model.has_save(PaneSide.LEFT)
    setup.handler.granted = False  # type: ignore[attr-defined]
    asyncio.run(setup.on_lifecycle(resume()))
    assert shown_texts(page)[0] == screen_copy(SetupStep.NEED_ACCESS).title
    setup.handler.granted = True  # type: ignore[attr-defined]
    asyncio.run(setup.on_lifecycle(resume()))
    assert page.controls == [win.root] and page.on_keyboard_event == win.on_key


def test_picking_the_azahar_folder_opens_the_save_with_the_bank(tmp_path: Path) -> None:
    setup, win, page, user, save = start(tmp_path, granted=True)
    assert shown_texts(page)[0] == screen_copy(SetupStep.NEED_FOLDER).title
    setup.picker = FakePicker(str(user))  # type: ignore[assignment]
    asyncio.run(setup.choose_folder())
    assert page.controls == [win.root]
    assert win.model.has_save(PaneSide.LEFT) and win.model.left().rows
    assert win.model.right().title == "Bank"
    assert load_settings(setup.setup._paths).azahar_dir == user


def test_picking_another_folder_says_so_and_asks_again(tmp_path: Path) -> None:
    downloads = tmp_path / "storage" / "Download"
    downloads.mkdir(parents=True)
    setup, _, page, _, _ = start(tmp_path, granted=True, picked=str(downloads))
    asyncio.run(setup.choose_folder())
    shown = shown_texts(page)
    assert shown[0] == screen_copy(SetupStep.NEED_FOLDER).title and NOT_AZAHAR in shown


def test_cancelled_folder_pick_changes_nothing(tmp_path: Path) -> None:
    setup, _, page, _, _ = start(tmp_path, granted=True, picked=None)
    before = shown_texts(page)
    asyncio.run(setup.choose_folder())
    assert shown_texts(page) == before


def test_handler_that_cannot_answer_falls_back_to_reading_storage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setup, _, _, _, _ = start(tmp_path, granted=False)

    async def broken(_permission: object) -> None:
        raise RuntimeError("no answer")

    setup.handler.get_status = broken  # type: ignore[method-assign]
    monkeypatch.setattr(android_setup, "storage_writable", lambda: True)
    assert asyncio.run(setup.has_access())
    monkeypatch.setattr(android_setup, "storage_writable", lambda: False)
    assert not asyncio.run(setup.has_access())


def test_setup_window_fits_the_thor_and_small_screens() -> None:
    assert window_width(THOR_W) == android_setup.WINDOW_MAX_W
    assert window_width(SMALL_W) <= SMALL_W - 2 * android_setup.SIDE_MARGIN
    assert window_width(400) == 400 - 2 * android_setup.SIDE_MARGIN
    assert window_width(None) == android_setup.WINDOW_MAX_W
    view = setup_view(screen_copy(SetupStep.NEED_ACCESS), lambda: None, None, 560)
    gold = buttons(view)
    assert len(gold) == 1 and gold[0].height >= android_setup.TOUCH_HEIGHT


def test_open_save_on_android_goes_straight_to_the_folder_picker(tmp_path: Path) -> None:
    paths, _, save = world(tmp_path)
    page = FakePage(THOR_W)
    win = Window(page, AppModel(paths, ANDROID_PROFILE, clock=ticking_clock()))  # type: ignore[arg-type]
    win.build()
    win.open_dialog()
    assert not page.open_alerts()
    assert page.tasks == [win.pick_and_open]


def test_desktop_never_shows_the_setup_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(gui_main.APP_DIR_ENV, str(tmp_path))
    monkeypatch.delenv(gui_main.SMOKE_ENV, raising=False)
    page = FakePage()
    page.platform = ft.PagePlatform.WINDOWS
    asyncio.run(gui_main.main(page))  # type: ignore[arg-type]
    assert page.services == []
    assert page.added and not any(
        t == screen_copy(SetupStep.NEED_ACCESS).title for c in page.added for t in texts(c)
    )


def test_storage_probe_leaves_nothing_behind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("EXTERNAL_STORAGE", str(tmp_path))
    assert android_setup.storage_writable()
    assert list((tmp_path / "DQ7 Tablet Trader").iterdir()) == []
    monkeypatch.setenv("EXTERNAL_STORAGE", str(tmp_path / "file"))
    (tmp_path / "file").write_text("not a folder", encoding="utf-8")
    assert not android_setup.storage_writable()


def test_setup_screen_passes_keys_to_the_window(tmp_path: Path) -> None:
    paths, _, _ = world(tmp_path)
    page = FakePage(THOR_W)
    page.platform = ft.PagePlatform.ANDROID
    model = AppModel(paths, ANDROID_PROFILE, clock=ticking_clock())
    win = Window(page, model)  # type: ignore[arg-type]
    setup = AndroidSetup(page, SetupModel(paths), win.show, on_key=win.setup_key)  # type: ignore[arg-type]
    setup.handler = FakeHandler(False)  # type: ignore[assignment]
    asyncio.run(setup.start())
    assert page.on_keyboard_event == win.setup_key


def test_setup_screen_coming_back_closes_dialogs_and_keeps_unwritten_edits(
    tmp_path: Path,
) -> None:
    paths, user, _ = world(tmp_path)
    save_settings(paths, Settings(azahar_dir=user))
    setup, win, page, _, _ = start(tmp_path, granted=True)
    setup.on_window_hidden = win.cancel_dialogs
    model = win.model
    count = len(model.left().rows)
    model.toggle_row(PaneSide.LEFT, 0)
    model.remove_selected(confirmed=True)
    assert model.has_unwritten()
    model.toggle_row(PaneSide.LEFT, 0)
    win.handle(model.remove_selected())  # asks first: a dialog is open
    win.right_menu()  # and a second one over it
    assert len(page.open_alerts()) == 2
    setup.handler.granted = False  # type: ignore[attr-defined]
    asyncio.run(setup.on_lifecycle(resume()))
    assert shown_texts(page)[0] == screen_copy(SetupStep.NEED_ACCESS).title
    assert page.open_alerts() == [] and win._dialogs == []
    # Closed as Cancel closes them: the second removal was not made.
    assert len(model.left().rows) == count - 1
    setup.handler.granted = True  # type: ignore[attr-defined]
    asyncio.run(setup.on_lifecycle(resume()))
    assert page.controls == [win.root]
    assert model.has_unwritten() and len(model.left().rows) == count - 1
