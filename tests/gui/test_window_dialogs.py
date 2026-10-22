import asyncio
from pathlib import Path
from types import SimpleNamespace

import flet as ft
import pytest
from model_helpers import pal_save, us_save
from test_widgets import button_labels, buttons, texts, walk
from test_window import (
    FakePage,
    action,
    close_event,
    last_dialog,
    make,
    page_of,
    remove_first,
    snacks,
)

from dq7tt_gui import theme
from dq7tt_gui.dialogs import NO_SAVES_TEXT, SEARCHING_TEXT
from dq7tt_gui.viewmodels import Confirm, Notice, NoticeKind, PaneSide
from dq7tt_gui.window import Window


def ask(name: str, ran: list[str], notices: tuple[Notice, ...] = ()) -> Confirm:
    return Confirm(
        name, f"{name}?", f"Yes {name}", notices=notices, on_ok=lambda: ran.append(name) or []
    )


def open_titles(win: Window) -> list[str]:
    return [str(d.title.value) for d in page_of(win).open_alerts()]  # type: ignore[union-attr]


def cancel(win: Window) -> None:
    action(last_dialog(win), "Cancel").on_click(None)  # type: ignore[misc]


def test_closing_a_dialog_leaves_a_snackbar_open(tmp_path: Path) -> None:
    win, _ = make(tmp_path)
    win.show_confirm(ask("A", []))
    win.show_notices([Notice(NoticeKind.INFO, "later news")])
    cancel(win)
    (bar,) = snacks(page_of(win))
    assert bar.open is True
    assert not page_of(win).open_alerts()


def test_cancel_shows_the_confirm_notices(tmp_path: Path) -> None:
    win, _ = make(tmp_path)
    note = Notice(NoticeKind.INFO, "Wrote the edited save to here.")
    win.show_confirm(ask("Azahar", [], (note,)))
    cancel(win)
    assert [b.content.value for b in snacks(page_of(win))] == [note.text]  # type: ignore[union-attr]


def test_two_confirms_are_shown_one_after_the_other(tmp_path: Path) -> None:
    win, _ = make(tmp_path)
    ran: list[str] = []
    win.handle(ask("First", ran))
    win.handle(ask("Second", ran))
    assert open_titles(win) == ["First"]
    action(last_dialog(win), "Yes First").on_click(None)  # type: ignore[misc]
    assert open_titles(win) == ["Second"]
    action(last_dialog(win), "Yes Second").on_click(None)  # type: ignore[misc]
    assert ran == ["First", "Second"]
    assert win.pending_confirm is None and not page_of(win).open_alerts()


def test_dismissing_a_confirm_acts_like_cancel(tmp_path: Path) -> None:
    win, _ = make(tmp_path)
    ran: list[str] = []
    note = Notice(NoticeKind.INFO, "kept")
    win.show_confirm(ask("A", ran, (note,)))
    win.show_confirm(ask("B", ran))
    dialog = last_dialog(win)
    dialog.on_dismiss(None)  # type: ignore[misc]
    assert ran == [] and open_titles(win) == ["B"]
    assert len(snacks(page_of(win))) == 1
    dialog.on_dismiss(None)  # a late second dismissal changes nothing
    assert open_titles(win) == ["B"] and len(snacks(page_of(win))) == 1


def test_dismissing_a_choice_dialog_frees_the_keyboard(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    win.toggle("left:0")
    win.pick_destination(move=False)
    last_dialog(win).on_dismiss(None)  # type: ignore[misc]
    assert not page_of(win).open_alerts()
    win.on_key(SimpleNamespace(key="Escape", ctrl=False, shift=False))  # type: ignore[arg-type]
    assert model.action_bar().selected_count == 0


def test_close_request_during_another_confirm_waits_its_turn(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    remove_first(model)
    win.show_confirm(ask("Other", []))
    asyncio.run(win.on_window_event(close_event()))
    asyncio.run(win.on_window_event(close_event()))
    assert open_titles(win) == ["Other"]
    cancel(win)
    assert open_titles(win) == ["Discard changes?"]
    asyncio.run(win.on_window_event(close_event()))  # pending now: nothing new is queued
    cancel(win)
    assert not page_of(win).open_alerts() and page_of(win).tasks == []
    asyncio.run(win.on_window_event(close_event()))  # a fresh request asks again
    assert open_titles(win) == ["Discard changes?"]


def test_queued_close_question_just_closes_when_nothing_is_left_to_lose(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    remove_first(model)
    win.show_confirm(ask("Other", []))
    asyncio.run(win.on_window_event(close_event()))
    model.undo()
    cancel(win)
    assert not page_of(win).open_alerts()
    assert len(page_of(win).tasks) == 1


def test_page_width_none_falls_back_to_the_default(tmp_path: Path) -> None:
    win = Window(FakePage(None), make(tmp_path)[1])  # type: ignore[arg-type]
    assert win.narrow is (theme.WINDOW_W < theme.NARROW_WIDTH)
    win.install()
    assert not win.narrow


def test_tab_index_survives_refresh_when_narrow(tmp_path: Path) -> None:
    win, _ = make(tmp_path, 600.0)
    tabs = next(c for c in walk(win.build()) if isinstance(c, ft.Tabs))
    tabs.selected_index = 1
    win._on_tab(SimpleNamespace(control=tabs))  # type: ignore[arg-type]
    win.refresh()
    again = next(c for c in walk(win.build()) if isinstance(c, ft.Tabs))
    assert again.selected_index == 1


def test_find_saves_shows_a_searching_dialog_then_results(tmp_path: Path) -> None:
    win, model = make(tmp_path, opened=False)
    us_save(tmp_path)
    win.find_saves([tmp_path / "sd"])
    assert SEARCHING_TEXT in texts(last_dialog(win).content)  # type: ignore[arg-type]
    assert len(page_of(win).tasks) == 1
    page_of(win).run_tasks()
    assert open_titles(win) == ["Saves on this PC"]
    shown = texts(last_dialog(win).content)  # type: ignore[arg-type]
    assert any("Checkpoint" in t for t in shown) and any("adventure log" in t for t in shown)
    buttons(last_dialog(win).content)[0].on_click(None)  # type: ignore[arg-type, misc]
    assert model.left().rows and not page_of(win).open_alerts()


def test_find_saves_error_becomes_a_notice(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    win, model = make(tmp_path, opened=False)

    def boom(roots: object = None) -> list[object]:
        raise PermissionError("denied")

    monkeypatch.setattr(model, "scan_results", boom)
    win.find_saves()
    page_of(win).run_tasks()
    assert not page_of(win).open_alerts()
    (bar,) = snacks(page_of(win))
    assert bar.bgcolor == theme.ERROR_WINDOW


def test_cancelling_the_search_ignores_late_results(tmp_path: Path) -> None:
    win, _ = make(tmp_path, opened=False)
    us_save(tmp_path)
    win.find_saves([tmp_path / "sd"])
    cancel(win)
    page_of(win).run_tasks()
    assert not page_of(win).open_alerts()


def test_find_saves_with_none_says_so(tmp_path: Path) -> None:
    win, _ = make(tmp_path, opened=False)
    win.find_saves([tmp_path / "nothing"])
    page_of(win).run_tasks()
    assert texts(last_dialog(win).content) == [NO_SAVES_TEXT]  # type: ignore[arg-type]


class FakeFile:
    def __init__(self, path: str) -> None:
        self.path = path


class RecordingPicker:
    def __init__(self, folder: str | None = None, files: list[str] | None = None) -> None:
        self.folder, self.files = folder, files or []
        self.kwargs: dict[str, object] = {}

    async def get_directory_path(self, **_kw: object) -> str | None:
        return self.folder

    async def pick_files(self, **kw: object) -> list[FakeFile]:
        self.kwargs = kw
        return [FakeFile(f) for f in self.files]


def test_open_offers_folder_or_file_or_zip(tmp_path: Path) -> None:
    win, model = make(tmp_path, opened=False)
    picker = RecordingPicker(files=[str(us_save(tmp_path) / "save000.bin")])
    win.picker = picker  # type: ignore[assignment]
    win.open_dialog()
    names = button_labels(last_dialog(win).content)  # type: ignore[arg-type]
    assert names == ["Open folder", "Open file or zip"]
    buttons(last_dialog(win).content)[1].on_click(None)  # type: ignore[arg-type, misc]
    assert not page_of(win).open_alerts()
    page_of(win).run_tasks()
    assert picker.kwargs["allowed_extensions"] == ["bin", "zip"]
    assert picker.kwargs["file_type"] is ft.FilePickerFileType.CUSTOM
    assert model.left().rows


def test_open_file_cancelled_changes_nothing(tmp_path: Path) -> None:
    win, model = make(tmp_path, opened=False)
    win.picker = RecordingPicker()  # type: ignore[assignment]
    asyncio.run(win.pick_file_and_open())
    assert not model.left().rows


def test_open_folder_choice_runs_the_folder_picker(tmp_path: Path) -> None:
    win, model = make(tmp_path, opened=False)
    win.picker = RecordingPicker(folder=str(us_save(tmp_path)))  # type: ignore[assignment]
    win.open_dialog()
    buttons(last_dialog(win).content)[0].on_click(None)  # type: ignore[arg-type, misc]
    page_of(win).run_tasks()
    assert model.left().rows


def test_opening_over_unwritten_edits_asks_then_discards(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    remove_first(model)
    win._open_path(pal_save(tmp_path))
    assert win.pending_confirm is not None and win.pending_confirm.ok_label == "Discard"
    assert model.has_unwritten()
    action(last_dialog(win), "Discard").on_click(None)  # type: ignore[misc]
    assert not model.has_unwritten()


def test_cancel_on_open_leaves_the_model_unchanged(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    remove_first(model)
    before = model.left()
    win._open_path(pal_save(tmp_path))
    cancel(win)
    assert model.left() == before and model.has_unwritten()


def test_new_folder_uses_a_text_prompt(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    win.new_folder()
    dialog = last_dialog(win)
    field = next(c for c in walk(dialog.content) if isinstance(c, ft.TextField))  # type: ignore[arg-type]
    field.value = "Maps"
    action(dialog, "Create").on_click(None)  # type: ignore[misc]
    assert any(c.name == "Maps" for c in model.right().folder_chips)
    assert not page_of(win).open_alerts()


def test_send_to_lists_logs_before_bank_folders(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    model.new_folder("Maps")
    model.toggle_row(PaneSide.LEFT, 0)
    win.pick_destination(move=False)
    dests = model.destinations()
    assert {d.kind for d in dests} == {"log", "bank"}
    names = [texts(b)[0] for b in buttons(last_dialog(win).content)]  # type: ignore[arg-type]
    logs = [d.label for d in dests if d.kind == "log"]
    banks = [d.label.replace("bank folder", "Bank folder", 1) for d in dests if d.kind == "bank"]
    assert names == logs + banks


def test_write_notices_then_the_azahar_question(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win, model = make(tmp_path)
    follow = Confirm("Put into Azahar?", "Close Azahar first.", "Put it in", on_ok=lambda: [])
    results = iter([[Notice(NoticeKind.INFO, "Wrote it.")], follow])
    monkeypatch.setattr(model, "dirty_sides", lambda: [PaneSide.LEFT, PaneSide.RIGHT])
    monkeypatch.setattr(model, "write", lambda side: next(results))
    win.write_all()
    assert [b.content.value for b in snacks(page_of(win))] == ["Wrote it."]  # type: ignore[union-attr]
    assert open_titles(win) == ["Put into Azahar?"]


def test_unexpected_scan_failure_closes_the_dialog_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win, model = make(tmp_path, opened=False)

    def boom(roots: object = None) -> None:
        raise RuntimeError("surprise")

    monkeypatch.setattr(model, "find_saves", boom)
    win.find_saves()
    page_of(win).run_tasks()
    assert not page_of(win).open_alerts()
    (bar,) = snacks(page_of(win))
    assert bar.bgcolor == theme.ERROR_WINDOW
    assert "looking for saves" in bar.content.value  # type: ignore[union-attr]
