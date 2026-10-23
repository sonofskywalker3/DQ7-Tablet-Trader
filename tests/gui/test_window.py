import asyncio
from collections.abc import Callable
from pathlib import Path

import flet as ft
import pytest
from model_helpers import new_model, us_save
from test_widgets import buttons, label, texts, walk

from dq7tt_gui import theme
from dq7tt_gui.model import AppModel
from dq7tt_gui.viewmodels import Confirm, Notice, NoticeKind, PaneSide
from dq7tt_gui.window import APP_TITLE, EMPTY_TEXT, Window

WIDE = 1280.0
NARROW = 500.0  # below the compact layout's 600
TALL = 700.0


class FakeWindow:
    prevent_close = False
    on_event: Callable[..., object] | None = None

    async def destroy(self) -> None:
        return None


class FakeView:
    """The page's root view: whether Android's Back may leave, and the answers given."""

    def __init__(self) -> None:
        self.can_pop = True
        self.on_confirm_pop: Callable[..., object] | None = None
        self.answers: list[bool] = []

    async def confirm_pop(self, should_pop: bool) -> None:
        self.answers.append(should_pop)


class FakePage:
    """The few page attributes the window touches; records dialogs instead of showing them."""

    def __init__(self, width: float | None = WIDE) -> None:
        self.title = ""
        self.width = width
        self.height: float | None = None
        self.window = FakeWindow()
        self.views = [FakeView()]
        self.platform: ft.PagePlatform | None = None
        self.controls: list[ft.Control] = []
        self.on_keyboard_event: Callable[..., object] | None = None
        self.on_resize: Callable[..., object] | None = None
        self.services: list[object] = []
        self.shown: list[ft.Control] = []
        self.added: list[ft.Control] = []
        self.tasks: list[Callable[..., object]] = []
        self.task_args: list[tuple[object, ...]] = []
        self.updates = 0

    def show_dialog(self, dialog: ft.Control) -> None:
        dialog.open = True  # type: ignore[attr-defined]
        self.shown.append(dialog)

    def pop_dialog(self) -> ft.Control | None:
        """Like Flet: closes the topmost open dialog, whatever kind it is."""
        for dialog in reversed(self.shown):
            if dialog.open:  # type: ignore[attr-defined]
                dialog.open = False  # type: ignore[attr-defined]
                return dialog
        return None

    def open_alerts(self) -> list[ft.AlertDialog]:
        return [d for d in self.shown if isinstance(d, ft.AlertDialog) and d.open]

    def add(self, *controls: ft.Control) -> None:
        self.added.extend(controls)
        self.controls.extend(controls)

    def update(self) -> None:
        self.updates += 1

    def run_task(self, handler: Callable[..., object], *args: object) -> None:
        self.tasks.append(handler)
        self.task_args.append(args)

    def run_tasks(self) -> None:
        """Run every queued background task to the end, in order."""
        while self.tasks:
            handler, args = self.tasks.pop(0), self.task_args.pop(0)
            asyncio.run(handler(*args))  # type: ignore[arg-type]


def make(tmp_path: Path, width: float = WIDE, opened: bool = True) -> tuple[Window, AppModel]:
    model = new_model(tmp_path)
    if opened:
        assert model.open_left(us_save(tmp_path)) == []
    win = Window(FakePage(width), model)  # type: ignore[arg-type]
    win.build()
    return win, model


def page_of(win: Window) -> FakePage:
    return win.page  # type: ignore[return-value]


def key_event(key: str, ctrl: bool = False, shift: bool = False) -> ft.KeyboardEvent:
    return ft.KeyboardEvent(
        name="",
        control=None,
        key=key,
        shift=shift,
        ctrl=ctrl,
        alt=False,
        meta=False,  # type: ignore[arg-type]
    )


def close_event() -> ft.WindowEvent:
    return ft.WindowEvent(name="", control=None, type=ft.WindowEventType.CLOSE)  # type: ignore[arg-type]


def snacks(page: FakePage) -> list[ft.SnackBar]:
    return [d for d in page.shown if isinstance(d, ft.SnackBar)]


def last_dialog(win: Window) -> ft.AlertDialog:
    dialogs = page_of(win).open_alerts()
    assert dialogs
    return dialogs[-1]


def action(dialog: ft.AlertDialog, word: str) -> ft.Button:
    return next(a for a in dialog.actions or [] if isinstance(a, ft.Button) and word in label(a))


def remove_first(model: AppModel) -> str:
    """Remove the first left tablet (accepting any confirm); returns its name."""
    name = model.left().rows[0].name
    assert model.toggle_row(PaneSide.LEFT, 0) == []
    result = model.remove_selected()
    if isinstance(result, Confirm):
        assert result.on_ok is not None
        assert result.on_ok() == []
    else:
        assert result == []
    return name


def test_wide_layout_has_two_panes_and_no_tabs(tmp_path: Path) -> None:
    win, _ = make(tmp_path)
    root = win.build()
    assert not [c for c in walk(root) if isinstance(c, ft.Tabs)]
    shown = texts(root)
    assert "Bank" in shown and "Close" in shown
    assert "Write changes" in shown


def test_narrow_layout_uses_save_and_bank_tabs(tmp_path: Path) -> None:
    win, _ = make(tmp_path, NARROW)
    root = win.build()
    tabs = [c for c in walk(root) if isinstance(c, ft.Tabs)]
    assert len(tabs) == 1 and tabs[0].length == 2
    bar = next(c for c in walk(root) if isinstance(c, ft.TabBar))
    assert [" ".join(texts(t.label)) for t in bar.tabs] == ["Save", "Bank"]
    # The pointer marks the tab that is showing.
    assert isinstance(bar.tabs[0].label, ft.Row)
    assert isinstance(bar.tabs[1].label, ft.Text)
    shown = texts(root)
    assert "More" in shown and "Write changes" in shown


def test_resize_switches_between_layouts(tmp_path: Path) -> None:
    win, _ = make(tmp_path)
    win.on_resize(ft.PageResizeEvent("resize", win.page, NARROW, TALL))  # type: ignore[arg-type]
    assert win.narrow
    assert [c for c in walk(win.build()) if isinstance(c, ft.Tabs)]
    win.apply_width(WIDE)
    assert not win.narrow
    assert not [c for c in walk(win.build()) if isinstance(c, ft.Tabs)]


def test_empty_state_offers_open_and_find(tmp_path: Path) -> None:
    win, _ = make(tmp_path, opened=False)
    root = win.build()
    assert EMPTY_TEXT in texts(root)
    labels = [label(b) for b in buttons(root)]
    assert labels.count("Open save") >= 2 and labels.count("Find saves") >= 2


def test_refresh_shows_the_new_rows(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    name = model.left().rows[0].name
    assert name in texts(win.build())
    remove_first(model)
    win.refresh()
    assert texts(win.build()).count(name) == [r.name for r in model.left().rows].count(name)


def test_selection_shows_in_the_action_bar(tmp_path: Path) -> None:
    win, _ = make(tmp_path)
    win.toggle("left:0")
    assert "1 tablet selected" in texts(win.build())


def test_keyboard_calls_model_undo_and_redo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win, model = make(tmp_path)
    calls: list[str] = []
    monkeypatch.setattr(model, "undo", lambda: calls.append("undo") or [])
    monkeypatch.setattr(model, "redo", lambda: calls.append("redo") or [])
    win.on_key(key_event("z", ctrl=True))
    win.on_key(key_event("Y", ctrl=True))
    win.on_key(key_event("z", ctrl=True, shift=True))
    win.on_key(key_event("z"))
    assert calls == ["undo", "redo", "redo"]


def test_ctrl_z_really_undoes(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    before = [r.name for r in model.left().rows]
    remove_first(model)
    win.on_key(key_event("z", ctrl=True))
    assert [r.name for r in model.left().rows] == before
    win.on_key(key_event("y", ctrl=True))
    assert [r.name for r in model.left().rows] == before[1:]


def test_escape_clears_and_ctrl_a_selects_active_pane(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    win.on_key(key_event("a", ctrl=True))
    assert model.action_bar().selected_count == len(model.left().rows)
    win.on_key(key_event("Escape"))
    assert model.action_bar().selected_count == 0


def test_clicking_a_row_makes_its_pane_active(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    win.toggle("right:0")
    assert win.active_side is PaneSide.RIGHT
    win.toggle("left:1")
    assert win.active_side is PaneSide.LEFT
    assert model.action_bar().selected_count == 1


def test_ctrl_s_writes_the_left_save(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    win, model = make(tmp_path)
    written: list[PaneSide] = []
    monkeypatch.setattr(model, "dirty_sides", lambda: [PaneSide.LEFT])
    monkeypatch.setattr(model, "write", lambda side: written.append(side) or [])
    win.on_key(key_event("s", ctrl=True))
    assert written == [PaneSide.LEFT]


def test_keys_ignored_while_a_dialog_is_open(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    win.show_confirm(Confirm("t", "x", "OK", on_ok=lambda: []))
    win.on_key(key_event("a", ctrl=True))
    assert model.action_bar().selected_count == 0


def test_notices_become_snackbars_with_error_colours(tmp_path: Path) -> None:
    win, _ = make(tmp_path)
    win.show_notices([Notice(NoticeKind.INFO, "fine"), Notice(NoticeKind.ERROR, "bad")])
    bars = snacks(page_of(win))
    assert [b.content.value for b in bars] == ["fine", "bad"]  # type: ignore[union-attr]
    assert bars[1].bgcolor == theme.ERROR_WINDOW
    assert bars[0].bgcolor != theme.ERROR_WINDOW
    assert bars[1].content.color == theme.DANGER_TEXT  # type: ignore[union-attr]


def test_confirm_is_stored_and_ok_runs_on_ok(tmp_path: Path) -> None:
    win, _ = make(tmp_path)
    ran: list[int] = []
    confirm = Confirm("Sure?", "Really?", "Do it", on_ok=lambda: ran.append(1) or [])
    win.handle(confirm)
    assert win.pending_confirm is confirm
    dialog = last_dialog(win)
    assert "Really?" in texts(dialog.content)  # type: ignore[arg-type]
    action(dialog, "Do it").on_click(None)  # type: ignore[misc]
    assert ran == [1]
    assert win.pending_confirm is None
    assert not page_of(win).open_alerts()


def test_confirm_cancel_does_not_run_on_ok(tmp_path: Path) -> None:
    win, _ = make(tmp_path)
    ran: list[int] = []
    win.handle(Confirm("Sure?", "Really?", "Do it", on_ok=lambda: ran.append(1) or []))
    action(last_dialog(win), "Cancel").on_click(None)  # type: ignore[misc]
    assert ran == [] and win.pending_confirm is None


def test_title_gains_star_when_unwritten(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    win.refresh()
    assert page_of(win).title == APP_TITLE
    remove_first(model)
    win.refresh()
    assert page_of(win).title == APP_TITLE + " *"


def test_close_with_unwritten_edits_asks_first(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    remove_first(model)
    win.install()
    assert page_of(win).window.prevent_close is True
    asyncio.run(win.on_window_event(close_event()))
    assert win.pending_confirm is not None
    assert win.pending_confirm.ok_label == "Discard"
    assert page_of(win).tasks == []
    assert win.pending_confirm.on_ok is not None
    win.pending_confirm.on_ok()
    assert len(page_of(win).tasks) == 1


def test_close_without_edits_closes_at_once(tmp_path: Path) -> None:
    win, _ = make(tmp_path, opened=False)
    asyncio.run(win.on_window_event(close_event()))
    assert win.pending_confirm is None
    assert len(page_of(win).tasks) == 1


class FakePicker:
    def __init__(self, path: str | None) -> None:
        self.path = path

    async def get_directory_path(self, **_kw: object) -> str | None:
        return self.path


def test_open_save_uses_folder_picker(tmp_path: Path) -> None:
    win, model = make(tmp_path, opened=False)
    win.picker = FakePicker(str(us_save(tmp_path)))  # type: ignore[assignment]
    asyncio.run(win.pick_and_open())
    assert model.left().rows


def test_open_save_cancelled_changes_nothing(tmp_path: Path) -> None:
    win, model = make(tmp_path, opened=False)
    win.picker = FakePicker(None)  # type: ignore[assignment]
    asyncio.run(win.pick_and_open())
    assert not model.left().rows


def test_find_saves_lists_results_and_opens_choice(tmp_path: Path) -> None:
    win, model = make(tmp_path, opened=False)
    save = us_save(tmp_path)
    win.find_saves([tmp_path / "sd"])
    page_of(win).run_tasks()
    choices = buttons(last_dialog(win).content)  # type: ignore[arg-type]
    assert choices, save
    choices[0].on_click(None)  # type: ignore[misc]
    assert model.left().rows


def test_find_saves_with_none_found_says_so(tmp_path: Path) -> None:
    win, _ = make(tmp_path, opened=False)
    win.find_saves([tmp_path / "nothing"])
    page_of(win).run_tasks()
    assert "No Dragon Quest VII saves" in " ".join(texts(last_dialog(win).content))  # type: ignore[arg-type]


def test_send_to_dialog_lists_destinations(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    win.toggle("left:0")
    win.pick_destination(move=False)
    choices = buttons(last_dialog(win).content)  # type: ignore[arg-type]
    names = [texts(b)[0] for b in choices]
    dests = model.destinations()
    assert names == [d.label.replace("bank folder", "Bank folder", 1) for d in dests]
    assert "Bank folder Unsorted" in names
    # Each log says who plays it, how long and how full, beside its name.
    assert [" ".join(texts(b)[1:]) for b in choices] == [d.detail for d in dests]
    assert any(d.detail for d in dests)
