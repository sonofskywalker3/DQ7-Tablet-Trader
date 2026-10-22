"""Window wiring for pane actions, the narrow layout, keys, touch sizes and the folder prompt."""

from pathlib import Path

import flet as ft
import pytest
from model_helpers import AZAHAR_PATH, US_SET, fill
from test_widgets import button_labels, buttons, callbacks, label, pane_view, texts, walk
from test_window import (
    NARROW,
    action,
    key_event,
    last_dialog,
    make,
    page_of,
    remove_first,
    snacks,
)

from dq7tt_gui.model import AppModel
from dq7tt_gui.viewmodels import Confirm, PaneSide, PaneView, RightMode
from dq7tt_gui.widgets_pane import pane
from dq7tt_gui.window import Window

PUT = "Put into Azahar"
BANK_ALL = "Bank all tablets in this log"
TOUCH = 40


def written_azahar(tmp_path: Path, width: float = 1280.0) -> tuple[Window, AppModel]:
    win, model = make(tmp_path, width, opened=False)
    model.open_left(fill(tmp_path / AZAHAR_PATH, US_SET))
    remove_first(model)
    assert isinstance(model.write(PaneSide.LEFT), Confirm)  # "Not now"
    return win, model


def dialog_options(win: Window) -> list[str]:
    return button_labels(last_dialog(win).content)  # type: ignore[arg-type]


def click_option(win: Window, word: str) -> None:
    content = last_dialog(win).content
    button = next(b for b in buttons(content) if label(b) == word)  # type: ignore[arg-type]
    button.on_click(None)  # type: ignore[misc]


def click_button(root: ft.Control, word: str) -> None:
    next(b for b in buttons(root) if label(b) == word).on_click(None)  # type: ignore[misc]


# Put into Azahar and Bank all in the wide layout


def test_wide_pane_header_offers_put_into_azahar_after_not_now(tmp_path: Path) -> None:
    win, _ = written_azahar(tmp_path)
    root = win.build()
    assert PUT in button_labels(root)
    click_button(root, PUT)
    dialog = last_dialog(win)
    assert dialog.title.value == "Put into Azahar?"  # type: ignore[union-attr]
    assert action(dialog, PUT) and action(dialog, "Not now")


def test_wide_pane_header_offers_bank_all(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    root = win.build()
    assert PUT not in button_labels(root)
    count = len(model.left().rows)
    click_button(root, BANK_ALL)
    texts = [b.content.value for b in snacks(page_of(win))]  # type: ignore[union-attr]
    assert texts == [f"Copied {count} tablets to bank folder Unsorted."]
    assert len(model.right().rows) == count


# The narrow layout


def test_narrow_more_menu_offers_bank_all_and_put_into_azahar(tmp_path: Path) -> None:
    win, model = written_azahar(tmp_path, NARROW)
    root = win.build()
    assert BANK_ALL not in button_labels(root) and PUT not in button_labels(root)
    win.more()
    assert {BANK_ALL, PUT} <= set(dialog_options(win))
    click_option(win, BANK_ALL)
    assert len(model.right().rows) == len(model.left().rows)
    win.more()
    click_option(win, PUT)
    assert last_dialog(win).title.value == "Put into Azahar?"  # type: ignore[union-attr]


def test_narrow_rows_are_not_draggable_but_keep_the_grip(tmp_path: Path) -> None:
    wide, _ = make(tmp_path / "wide")
    assert [c for c in walk(wide.build()) if isinstance(c, ft.Draggable)]
    win, model = make(tmp_path / "narrow", NARROW)
    model.toggle_row(PaneSide.LEFT, 0)
    model.quick_copy()
    root = win.build()
    assert not [c for c in walk(root) if isinstance(c, ft.Draggable)]
    assert [c for c in walk(root) if isinstance(c, ft.ReorderableDragHandle)]


def wrapping_rows_with_expanding_children(root: ft.Control) -> list[ft.Control]:
    """Flutter cannot lay out an expanding child in a wrapping row; it draws a grey box.

    That includes an explicit expand=False, which Flet sends on and Flutter acts on.
    """
    return [
        child
        for row in walk(root)
        if isinstance(row, ft.Row) and row.wrap
        for child in row.controls
        if child.expand is not None
    ]


@pytest.mark.parametrize("width", [NARROW, 1280.0])
def test_no_wrapping_row_holds_an_expanding_child(tmp_path: Path, width: float) -> None:
    win, model = make(tmp_path, width)
    model.toggle_row(PaneSide.LEFT, 0)
    model.quick_copy()
    assert wrapping_rows_with_expanding_children(win.build()) == []


def test_narrow_bars_span_the_window_and_keep_write(tmp_path: Path) -> None:
    win, model = make(tmp_path, NARROW)
    model.toggle_row(PaneSide.LEFT, 0)
    root = win.build()
    layout = next(c for c in walk(root) if isinstance(c, ft.Column) and win._top in c.controls)
    assert layout.horizontal_alignment == ft.CrossAxisAlignment.STRETCH
    assert button_labels(root)[-3:] == ["Send 1 to...", "More", "Write changes"]


def test_narrow_second_tab_names_what_it_shows(tmp_path: Path) -> None:
    win, model = make(tmp_path, NARROW)

    def tab_labels() -> list[str]:
        bar = next(c for c in walk(win.build()) if isinstance(c, ft.TabBar))
        return [" ".join(texts(t.label)) for t in bar.tabs]

    assert tab_labels() == ["Save", "Bank"]
    other = fill(tmp_path / "sd/JKSM/User Saves/DRAGON QUEST VII/20261020-101500", US_SET)
    assert model.open_right(other) == []
    assert tab_labels() == ["Save", "JKSM"]
    model.show_bank()
    assert tab_labels() == ["Save", "Bank"]


def test_bank_move_offers_bank_folders_only(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    model.toggle_row(PaneSide.LEFT, 0)
    model.quick_copy()
    model.new_folder("Keep")
    model.pick_folder("")
    win.toggle("right:0")
    assert "Move to..." in button_labels(win.build())
    win.pick_destination(move=True)
    assert dialog_options(win) == ["Bank folder Keep"]


# Keys, toolbar wrapping and touch sizes


def test_ctrl_s_writes_every_save_with_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    win, model = make(tmp_path)
    written: list[PaneSide] = []
    monkeypatch.setattr(model, "dirty_sides", lambda: [PaneSide.LEFT, PaneSide.RIGHT])
    monkeypatch.setattr(model, "write", lambda side: written.append(side) or [])
    win.on_key(key_event("s", ctrl=True))
    assert written == [PaneSide.LEFT, PaneSide.RIGHT]


def test_toolbar_and_action_bar_buttons_wrap_instead_of_clipping(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    model.toggle_row(PaneSide.LEFT, 0)
    root = win.build()
    for word in ("Open save", "Undo", "Remove"):
        rows = [
            c
            for c in walk(root)
            if isinstance(c, ft.Row)
            and any(label(b) == word for b in c.controls if isinstance(b, ft.Button))
        ]
        assert rows and rows[0].wrap, word
    # Write keeps its place at the end of the toolbar, beside the commands that wrap.
    write = next(b for b in buttons(root) if label(b) == "Write changes")
    toolbar = next(
        c
        for c in walk(root)
        if isinstance(c, ft.Row)
        and c.controls
        and getattr(c.controls[-1], "content", None) is write
    )
    assert not toolbar.wrap and toolbar.controls[0].expand


def test_pane_buttons_and_mode_switch_are_touch_sized(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    root = win.build()
    sizes = {label(b): b.height for b in buttons(root)}
    for word in ("Close", "New folder", "Bank", "Open a second save", BANK_ALL):
        assert sizes[word] >= TOUCH, word


# The new folder prompt


def test_refused_folder_name_keeps_the_prompt_open_with_the_reason(tmp_path: Path) -> None:
    win, model = make(tmp_path)
    win.new_folder()
    dialog = last_dialog(win)
    field = next(c for c in walk(dialog.content) if isinstance(c, ft.TextField))  # type: ignore[arg-type]
    field.value = "a/b"
    action(dialog, "Create").on_click(None)  # type: ignore[misc]
    assert last_dialog(win) is dialog
    assert field.value == "a/b"
    assert field.error == "Folder names can't contain / \\ : * ? \" < > |."
    assert not snacks(page_of(win))
    field.value = "Maps"
    action(dialog, "Create").on_click(None)  # type: ignore[misc]
    assert not page_of(win).open_alerts()
    assert any(c.name == "Maps" for c in model.right().folder_chips)


# The pane header


def header_lines(view: PaneView, mode: RightMode = RightMode.SAVE) -> list[ft.Row]:
    """The header's lines, each out of the container that insets it; hairlines left out."""
    window = pane(view, callbacks([]), mode)
    stack = window.content.content  # type: ignore[union-attr]
    column = stack.controls[-1]
    header = column.controls[0]
    lines = header.content.controls
    return [line.content for line in lines if line.content is not None]


def test_title_line_holds_only_the_title_and_close() -> None:
    view = pane_view(PaneSide.RIGHT, can_bank_all=True, can_put_into_azahar=True)
    switch, title, actions = header_lines(view)
    assert button_labels(switch) == ["Bank", "Open a second save"]
    assert texts(title)[0] == "Checkpoint backup" and button_labels(title) == ["Close"]
    assert actions.wrap and button_labels(actions) == [PUT, BANK_ALL]


def test_left_pane_without_actions_has_one_header_line() -> None:
    (title,) = header_lines(pane_view(PaneSide.LEFT))
    assert button_labels(title) == ["Close"]


def test_bank_header_is_the_switch_and_new_folder() -> None:
    (line,) = header_lines(pane_view(PaneSide.RIGHT), RightMode.BANK)
    assert button_labels(line) == ["Bank", "Open a second save", "New folder"]
