"""The handheld's controller: B, L, R, Start and Y, focus and Android's Back."""

import logging
from pathlib import Path

import flet as ft
import pytest
from test_model_android import edited_azahar, tree
from test_widgets import walk
from test_window import key_event, page_of
from test_window_compact import BOTTOM_SCREEN, bank_some, make_compact

from dq7tt.savefile import SlotRole
from dq7tt_gui import theme
from dq7tt_gui.controller import BackGuard, Pad, pad_action
from dq7tt_gui.device_profile import DESKTOP_PROFILE
from dq7tt_gui.viewmodels import Confirm, PaneSide
from dq7tt_gui.window import Window

B, L1, R1 = "Game Button B", "Game Button Left 1", "Game Button Right 1"
START, Y = "Game Button Start", "Game Button Y"


@pytest.mark.parametrize(
    ("key", "pad"),
    [
        (B, Pad.BACK),
        (L1, Pad.SWITCH_LEFT),
        (R1, Pad.SWITCH_RIGHT),
        (START, Pad.SAVE),
        (Y, Pad.SELECT_ALL),
        ("game button b", Pad.BACK),
        ("GAME BUTTON START", Pad.SAVE),
        ("Arrow Down", None),
        ("Game Button A", None),
        ("", None),
    ],
)
def test_pad_action_table(key: str, pad: Pad | None) -> None:
    assert pad_action(key) is pad


def press_key(win: Window, key: str) -> None:
    win.on_key(key_event(key))


def open_alerts(win: Window) -> list[ft.AlertDialog]:
    return page_of(win).open_alerts()


def flet_wraps_dismiss(dialog: ft.AlertDialog) -> None:
    """What a real page's `show_dialog` does: it puts its own async wrapper in place of the
    dialog's `on_dismiss`, which only acts once Flutter reports the dismissal."""

    async def wrapper(*_args: object) -> None:
        raise AssertionError("only Flutter calls this")

    dialog.on_dismiss = wrapper


def test_back_closes_dialog_then_clears_selection(tmp_path: Path) -> None:
    win, model = make_compact(tmp_path)
    win.toggle("left:0")
    win.compact_more()
    assert len(open_alerts(win)) == 1
    flet_wraps_dismiss(win._dialogs[-1])
    press_key(win, B)
    assert open_alerts(win) == [] and not win._dialogs
    assert model.action_bar().selected_count == 1  # the dialog went first
    press_key(win, B)
    assert model.action_bar().selected_count == 0
    press_key(win, B)  # nothing left to go back from: nothing happens, the app stays
    assert model.action_bar().selected_count == 0 and page_of(win).tasks == []


def test_back_declines_a_question(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path)
    accepted: list[bool] = []
    win.show_confirm(Confirm("t", "x", "OK", on_ok=lambda: accepted.append(True) or []))
    flet_wraps_dismiss(win._dialogs[-1])
    press_key(win, B)
    assert open_alerts(win) == [] and win.pending_confirm is None and accepted == []


def test_r_and_l_move_the_active_pane_and_focus_its_first_row(tmp_path: Path) -> None:
    win, model = make_compact(tmp_path)
    bank_some(win, model)
    page = page_of(win)
    press_key(win, R1)
    assert win.active_side is PaneSide.RIGHT
    first = win._shells[PaneSide.RIGHT].first_row_focus()
    assert first is not None and page.tasks[-1] == first.focus
    press_key(win, L1)
    assert win.active_side is PaneSide.LEFT
    first = win._shells[PaneSide.LEFT].first_row_focus()
    assert first is not None and page.tasks[-1] == first.focus


def test_r_and_l_switch_the_short_tabs(tmp_path: Path) -> None:
    win, model = make_compact(tmp_path, BOTTOM_SCREEN)
    press_key(win, R1)
    assert win.tab_index == 1 and win.active_side is PaneSide.RIGHT
    press_key(win, L1)
    assert win.tab_index == 0 and win.active_side is PaneSide.LEFT


def test_r_switches_the_tall_tabs(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path, (360.0, 800.0))
    assert win.narrow and not win.slim
    press_key(win, R1)
    assert win.tab_index == 1 and win._tabs_control.selected_index == 1


def test_start_saves_like_the_save_button_and_asks_first(tmp_path: Path) -> None:
    win, model = make_compact(tmp_path)
    press_key(win, START)  # nothing to save yet
    assert open_alerts(win) == []
    azahar = edited_azahar(tmp_path, model)
    before = tree(azahar)
    win.refresh()
    press_key(win, START)
    assert len(open_alerts(win)) == 1 and win.pending_confirm is not None
    assert tree(azahar) == before  # nothing written before the yes


def test_y_ticks_every_tablet_in_the_active_pane(tmp_path: Path) -> None:
    win, model = make_compact(tmp_path)
    press_key(win, Y)
    assert model.action_bar().selected_count == len(model.left().rows)


def test_pad_keys_wait_while_a_dialog_is_open(tmp_path: Path) -> None:
    win, model = make_compact(tmp_path)
    win.compact_more()
    press_key(win, Y)
    press_key(win, R1)
    assert model.action_bar().selected_count == 0 and win.active_side is PaneSide.LEFT


# Android's own Back


def android_back(win: Window) -> list[bool]:
    """Send Android's Back to the root view; what the window answered (True leaves)."""
    view = page_of(win).views[0]
    win.install()
    assert view.can_pop is False and view.on_confirm_pop is not None
    view.on_confirm_pop(None)
    page_of(win).run_tasks()
    return view.answers


def test_back_leaves_when_nothing_is_unwritten(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path)
    assert android_back(win) == [True]


def test_back_with_unwritten_changes_asks_first(tmp_path: Path) -> None:
    win, model = make_compact(tmp_path)
    model.toggle_row(PaneSide.LEFT, 0)
    model.remove_selected()
    assert android_back(win) == []  # waiting for the answer
    assert win.pending_confirm is not None
    win._accept(win.pending_confirm)
    page_of(win).run_tasks()
    assert page_of(win).views[0].answers == [True]


def test_back_that_follows_b_is_refused(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path)
    press_key(win, B)
    assert android_back(win) == [False]


def test_back_guard_only_takes_the_back_right_after_b() -> None:
    now = [0.0]
    guard = BackGuard(lambda: now[0])
    assert not guard.is_echo()
    guard.b_pressed()
    now[0] = 0.5
    assert guard.is_echo() and not guard.is_echo()  # once only
    guard.b_pressed()
    now[0] = 10.0
    assert not guard.is_echo()


def test_desktop_does_not_hold_back(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path, profile=DESKTOP_PROFILE)
    win.install()
    assert page_of(win).views[0].on_confirm_pop is None


# Focus: every row, chip and strip button can take it


def focusables(root: ft.Control) -> list[ft.CupertinoButton]:
    return [c for c in walk(root) if isinstance(c, ft.CupertinoButton)]


def test_android_rows_and_strip_buttons_are_focusable(tmp_path: Path) -> None:
    win, model = make_compact(tmp_path)
    bank_some(win, model)
    win.toggle("left:0")
    rows = focusables(win._body)
    assert len(rows) >= len(model.left().rows) + len(model.right().rows)
    top = focusables(win._top)
    assert len(top) >= len(model.left().log_chips) + 3  # chips, picker, Undo, Save
    assert focusables(win._bottom)


def test_focused_strip_button_shows_a_gold_ring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Drawn by the app, not by Flutter: Flutter shows its own focus ring only when the
    keys come from a hardware keyboard, which an injected or virtual key is not."""
    win, _ = make_compact(tmp_path)
    button = next(b for b in focusables(win._top) if b.data == "picker")
    visual = button.content
    assert isinstance(visual, ft.Container)
    monkeypatch.setattr(visual, "update", lambda: None)
    button.on_focus(None)
    ring = visual.foreground_decoration
    assert ring is not None and ring.border.top.color == theme.GOLD  # type: ignore[union-attr]
    button.on_blur(None)
    assert visual.foreground_decoration is None


def test_gold_edged_buttons_get_a_light_ring(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A gold ring would not show on the active log chip, Copy to bank or Save."""
    win, _ = make_compact(tmp_path)
    win.toggle("left:0")
    for root, data in ((win._top, SlotRole.LOG_1), (win._bottom, "copy")):
        button = next(b for b in focusables(root) if b.data == data)
        visual = button.content
        monkeypatch.setattr(visual, "update", lambda: None)
        button.on_focus(None)
        assert visual.foreground_decoration.border.top.color == theme.TEXT  # type: ignore[union-attr]


def test_focused_row_shows_the_pointer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    win, _ = make_compact(tmp_path)
    shell = win._shells[PaneSide.LEFT]
    rows = focusables(win._body)
    third = next(b for b in rows if b.data == "left:2")
    monkeypatch.setattr(shell.pointer, "update", lambda: None)
    third.on_focus(None)
    middle = (shell.row_height - theme.POINTER_H) / 2
    assert shell.pointer.visible and shell.pointer.top == 2 * shell.row_height + middle
    third.on_blur(None)
    assert not shell.pointer.visible


def test_a_on_a_focused_row_ticks_it(tmp_path: Path) -> None:
    win, model = make_compact(tmp_path)
    row = next(b for b in focusables(win._body) if b.data == "left:1")
    row.on_click(None)
    assert model.action_bar().selected_count == 1


def test_first_save_row_takes_the_focus_at_start(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path)
    autofocused = [b for b in focusables(win._body) if b.autofocus]
    assert [b.data for b in autofocused] == ["left:0"]


def test_desktop_keeps_its_mouse_rows(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path, profile=DESKTOP_PROFILE)
    assert focusables(win._body) == [] and focusables(win._top) == []


def test_android_bank_rows_keep_their_focus_across_redraws(tmp_path: Path) -> None:
    """Bank rows carry keys on Android, so a tick redraws the focused row in place rather
    than replacing it (Flutter would send the focus back to the save)."""
    win, model = make_compact(tmp_path)
    bank_some(win, model)
    bank = win._shells[PaneSide.RIGHT].list_control()
    assert bank is not None and [c.key for c in bank.controls][:2] == ["right:0", "right:1"]


# Fix round 1


def test_unmapped_labels_are_logged_once_and_mapped_ones_never(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    win, _ = make_compact(tmp_path)
    with caplog.at_level(logging.DEBUG, logger="dq7tt_gui.controller"):
        press_key(win, "Game Button Mode")
        press_key(win, "Game Button Mode")
        press_key(win, Y)
        press_key(win, B)
        win.compact_more()
        press_key(win, "Q")  # typed while a dialog (a prompt, say) is open
    messages = [r.getMessage() for r in caplog.records]
    assert len([m for m in messages if "Game Button Mode" in m]) == 1
    assert not [m for m in messages if "Game Button Y" in m or "Game Button B" in m]
    assert not [m for m in messages if "'Q'" in m]
    assert all(r.levelno == logging.DEBUG for r in caplog.records)


def test_switch_to_an_empty_pane_focuses_its_header(tmp_path: Path) -> None:
    """An empty bank has no first row: the focus goes to its header, so A cannot tick a
    row in the pane that is no longer active."""
    win, model = make_compact(tmp_path)
    assert model.right().rows == ()
    press_key(win, R1)
    head = win._shells[PaneSide.RIGHT].head_focus()
    assert head is not None and head.data == "head"
    assert page_of(win).tasks[-1] == head.focus


def test_b_on_the_setup_screens_does_not_leave(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path, opened=False)
    page = page_of(win)
    win.hold_back()
    view = page.views[0]
    assert view.can_pop is False and view.on_confirm_pop is not None
    win.setup_key(key_event(B))
    view.on_confirm_pop(None)
    page.run_tasks()
    assert view.answers == [False]
    view.on_confirm_pop(None)  # a real Back still leaves
    page.run_tasks()
    assert view.answers == [False, True]


def test_row_focus_leaves_long_press_to_the_list(tmp_path: Path) -> None:
    """The focus control is a sliver at the row's left edge; the rest of the lead is a
    plain tap area, so a long press there still starts a reorder."""
    from dq7tt_gui.widgets import ROW_INSET
    from dq7tt_gui.widgets_focus import LEAD_FOCUS_W

    win, _ = make_compact(tmp_path)
    leads = [
        c
        for c in walk(win._body)
        if isinstance(c, ft.Container)
        and isinstance(c.content, ft.CupertinoButton)
        and c.width == ROW_INSET
    ]
    assert leads and all(c.on_click is not None for c in leads)
    assert all(c.content.width == LEAD_FOCUS_W < ROW_INSET for c in leads)


def test_header_ring_is_drawn_inside_its_focus_control(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redrawing the header itself would rebuild the control that just took the focus."""
    win, _ = make_compact(tmp_path)
    head = win._shells[PaneSide.RIGHT].head_focus()
    assert head is not None
    inside = head.content
    assert isinstance(inside, ft.Container)
    monkeypatch.setattr(inside, "update", lambda: None)
    head.on_focus(None)
    assert inside.foreground_decoration is not None


def test_a_on_the_active_panes_header_changes_nothing(tmp_path: Path) -> None:
    """Redrawing would rebuild the header that has the focus and Flutter would hand the
    focus back to a row of the other pane."""
    win, _ = make_compact(tmp_path)
    win._mounted = True  # so a redraw shows as a page update
    press_key(win, R1)
    updates = page_of(win).updates
    win.head_tapped(PaneSide.RIGHT)
    assert page_of(win).updates == updates and win.active_side is PaneSide.RIGHT


def test_header_ring_sits_clear_of_the_header_words(tmp_path: Path) -> None:
    """The ring is drawn inside the box; the words keep a margin wider than the ring, and
    the header's words stay where they were without the focus control."""
    from dq7tt_gui.widgets_compact import HEAD_PAD_LEFT, HEAD_PAD_RIGHT
    from dq7tt_gui.widgets_focus import FOCUS_RING_W

    win, _ = make_compact(tmp_path)
    head = win._shells[PaneSide.RIGHT].head_focus()
    assert head is not None
    inside = head.content
    outer = next(c for c in walk(win._body) if isinstance(c, ft.Container) and c.content is head)
    assert inside.padding.left > FOCUS_RING_W and inside.padding.right > FOCUS_RING_W
    assert outer.padding.left + inside.padding.left == HEAD_PAD_LEFT
    assert outer.padding.right + inside.padding.right == HEAD_PAD_RIGHT
