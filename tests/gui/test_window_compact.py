"""The compact layout for short screens such as the AYN Thor's top screen."""

from pathlib import Path
from typing import Any

import flet as ft
import pytest
from model_helpers import fill, ticking_clock, us_save
from test_widgets import texts, walk
from test_window import FakePage, last_dialog
from test_window_actions import dialog_options, wrapping_rows_with_expanding_children

from dq7tt.apppaths import AppPaths
from dq7tt.savefile import SlotRole
from dq7tt_gui import theme
from dq7tt_gui.device_profile import ANDROID_PROFILE, DESKTOP_PROFILE, Profile
from dq7tt_gui.dialogs import CHOICE_HEIGHT
from dq7tt_gui.layout import Layout
from dq7tt_gui.model import AppModel
from dq7tt_gui.viewmodels import Confirm, PaneSide
from dq7tt_gui.widgets_drag import DragPayload
from dq7tt_gui.widgets_pane import COMPACT_COMPASS, EMPTY_COMPASS
from dq7tt_gui.window import Window
from dq7tt_gui.window_dialogs import DIALOG_CHROME

THOR = (832.52, 468.29)
SMALL = (640.0, 360.0)
DEFAULT = (853.0, 480.0)


def make_compact(
    tmp_path: Path,
    size: tuple[float, float] = THOR,
    profile: Profile = ANDROID_PROFILE,
    opened: bool = True,
) -> tuple[Window, AppModel]:
    model = AppModel(AppPaths.under(tmp_path / "app"), profile, clock=ticking_clock())
    if opened:
        assert model.open_left(us_save(tmp_path)) == []
    page = FakePage(size[0])
    page.height = size[1]
    win = Window(page, model)  # type: ignore[arg-type]
    win.build()
    return win, model


def tagged(root: ft.Control, data: object) -> list[ft.Container]:
    return [c for c in walk(root) if isinstance(c, ft.Container) and c.data == data]


def tapped(root: ft.Control, data: object) -> Any:
    """The tap area tagged `data`, for pressing it."""
    found = [c for c in tagged(root, data) if c.on_click]
    assert found, data
    return found[0]


def press(root: ft.Control, data: object) -> None:
    tapped(root, data).on_click(None)


def bank_some(win: Window, model: AppModel, count: int = 3) -> None:
    for i in range(count):
        model.toggle_row(PaneSide.LEFT, i)
    model.quick_copy()
    win.refresh()


@pytest.mark.parametrize("size", [THOR, SMALL, DEFAULT])
def test_thor_sizes_take_the_compact_layout(tmp_path: Path, size: tuple[float, float]) -> None:
    win, model = make_compact(tmp_path, size)
    bank_some(win, model)
    root = win.build()
    assert win.layout is Layout.COMPACT
    assert not [c for c in walk(root) if isinstance(c, ft.Tabs)]
    # No engraved bands and no logo: the room goes to the lists.
    assert not any(b.visible for b in win._bands)
    assert not [c for c in walk(root) if isinstance(c, ft.Image) and c.src == "compass.svg"]
    lists = [c for c in walk(win._body.content) if isinstance(c, ft.ListView)]
    assert len(lists) == 2  # save and bank side by side
    assert win._top.content.height == theme.STRIP_HEIGHT
    assert win._bottom.content.height == theme.STRIP_HEIGHT


def test_wide_and_tabs_keep_their_bands(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path, (1280.0, 800.0), DESKTOP_PROFILE)
    win.build()
    assert win.layout is Layout.WIDE and all(b.visible for b in win._bands)
    win.apply_size(360.0, 700.0)  # a phone: tabs under the bands
    assert win.layout is Layout.TABS and win.narrow and all(b.visible for b in win._bands)
    win.apply_size(*THOR)
    assert win.layout is Layout.COMPACT and not win.narrow


def test_top_strip_has_log_chips_bank_folder_undo_and_save(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path, DEFAULT)
    top = texts(win._top)
    assert "Log 1" in top
    assert any(t.isdigit() for t in top)  # each log's count
    assert "Quick save" in top and "Undo" in top
    assert "Save into Azahar" in top or "Write changes" in top
    assert "Unsorted" in " ".join(top)


def test_small_width_shortens_the_strip(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path, SMALL)
    top = texts(win._top)
    assert "Quick" in top and "Quick save" not in top
    assert "Undo" not in top  # the arrow alone
    assert tagged(win._top, "undo")


def test_log_chip_picks_the_log(tmp_path: Path) -> None:
    win, model = make_compact(tmp_path)
    press(win._top, SlotRole.LOG_2)
    assert next(c for c in model.left().log_chips if c.active).role is SlotRole.LOG_2
    assert "LOG 2" in texts(win._body)


def test_android_rows_are_48_two_lines_long_press_and_sideways_drag(tmp_path: Path) -> None:
    win, model = make_compact(tmp_path)
    bank_some(win, model)
    shell = win._shells[PaneSide.LEFT]
    assert shell.row_height == theme.ANDROID_ROW_HEIGHT
    body = win._body.content
    (save_list,) = [c for c in walk(body) if isinstance(c, ft.ReorderableListView)]
    assert save_list.show_default_drag_handles  # a long press reorders
    assert not [c for c in walk(body) if isinstance(c, ft.ReorderableDragHandle)]
    drags = [c for c in walk(body) if isinstance(c, ft.Draggable)]
    assert drags and all(d.affinity == ft.Axis.HORIZONTAL for d in drags)
    cells = [c for c in walk(body) if isinstance(c, ft.Container) and c.data == "left:0"]
    cells = [c for c in cells if c.height]
    assert cells and all(c.height == theme.ANDROID_ROW_HEIGHT for c in cells)
    assert any(t.endswith(" clears") or t == "1 clear" for t in texts(body))


def test_desktop_compact_has_48_rows_grips_and_plain_drags(tmp_path: Path) -> None:
    """Two lines need 48 dp on every platform; the PC keeps its grips and plain drag."""
    win, _ = make_compact(tmp_path, SMALL, DESKTOP_PROFILE)
    body = win._body.content
    assert win._shells[PaneSide.LEFT].row_height == theme.COMPACT_ROW_HEIGHT == 48
    cells = [c for c in walk(body) if isinstance(c, ft.Container) and c.data == "left:0"]
    assert [c.height for c in cells if c.height] == [48]
    assert [c for c in walk(body) if isinstance(c, ft.ReorderableDragHandle)]
    drags = [c for c in walk(body) if isinstance(c, ft.Draggable)]
    assert drags and all(d.affinity is None for d in drags)


def test_android_tabs_rows_are_48_without_grips(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path, (360.0, 413.0))
    assert win.layout is Layout.TABS
    body = win._body.content
    assert not [c for c in walk(body) if isinstance(c, ft.ReorderableDragHandle)]
    assert not [c for c in walk(body) if isinstance(c, ft.Draggable)]


def test_key_marks_only_on_android(tmp_path: Path) -> None:
    android, _ = make_compact(tmp_path / "a")
    assert {"L", "R"} <= set(texts(android._body))
    desktop, _ = make_compact(tmp_path / "d", THOR, DESKTOP_PROFILE)
    assert "L" not in texts(desktop._body) and "R" not in texts(desktop._body)


def edge(win: Window, side: PaneSide) -> str:
    inner = win._shells[side].control.content
    return inner.border.top.color  # type: ignore[union-attr]


def test_active_pane_has_the_gold_edge(tmp_path: Path) -> None:
    win, model = make_compact(tmp_path)
    bank_some(win, model)
    assert edge(win, PaneSide.LEFT) == theme.GOLD
    assert edge(win, PaneSide.RIGHT) == theme.WINDOW_EDGE
    win.toggle("right:0")
    assert edge(win, PaneSide.RIGHT) == theme.GOLD
    assert edge(win, PaneSide.LEFT) == theme.WINDOW_EDGE


def test_bottom_strip_acts_on_the_selection(tmp_path: Path) -> None:
    win, model = make_compact(tmp_path)
    win.toggle("left:0")
    win.toggle("left:1")
    bottom = texts(win._bottom)
    assert "2 selected" in bottom
    assert {"Copy to bank", "Move", "Remove", "More"} <= set(bottom)
    press(win._bottom, "copy")
    assert len(model.right().rows) == 2


def test_folder_picker_lists_folders_and_new_folder(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path)
    press(win._top, "picker")
    options = dialog_options(win)
    assert any(o.startswith("Unsorted") for o in options)
    assert "New folder" in options and "Open a second save" in options


def test_more_offers_open_find_and_bank_all(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path)
    press(win._bottom, "more")
    options = dialog_options(win)
    assert {"Open save", "Find saves", "Bank all tablets in this log", "Close this save"} <= set(
        options
    )
    assert last_dialog(win).title.value == "More"  # type: ignore[union-attr]


def test_touch_drop_on_its_own_pane_is_ignored(tmp_path: Path) -> None:
    """A sideways flick that ends on the same pane must not reorder; a long press does."""
    win, model = make_compact(tmp_path)
    calls: list[object] = []
    model.drop = lambda *a: calls.append(a) or []  # type: ignore[method-assign]
    win._drop(DragPayload(PaneSide.LEFT, (0,)), PaneSide.LEFT, 3)
    win._drop(DragPayload(PaneSide.LEFT, (0,)), PaneSide.RIGHT, 0)
    assert calls == [(PaneSide.LEFT, (0,), PaneSide.RIGHT, 0)]


def test_android_keeps_clear_of_the_status_bar(tmp_path: Path) -> None:
    android, _ = make_compact(tmp_path / "a")
    assert [c for c in walk(android.build()) if isinstance(c, ft.SafeArea)]
    desktop, _ = make_compact(tmp_path / "d", THOR, DESKTOP_PROFILE)
    assert not [c for c in walk(desktop.build()) if isinstance(c, ft.SafeArea)]


@pytest.mark.parametrize("size", [THOR, SMALL])
def test_compact_has_no_wrapping_row_with_an_expanding_child(
    tmp_path: Path, size: tuple[float, float]
) -> None:
    win, model = make_compact(tmp_path, size)
    bank_some(win, model)
    win.toggle("left:0")
    assert wrapping_rows_with_expanding_children(win.build()) == []


def test_empty_compact_window_offers_open_and_find(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path, SMALL, opened=False)
    shown = texts(win.build())
    assert "Open save" in shown and "Find saves" in shown
    # The big compass of the wide window would not fit a pane 200 px tall.
    sizes = {c.height for c in walk(win._body) if isinstance(c, ft.Image)}
    assert COMPACT_COMPASS in sizes and EMPTY_COMPASS not in sizes


def test_azahar_save_strip_says_save_into_azahar(tmp_path: Path) -> None:
    from model_helpers import AZAHAR_PATH, US_SET

    win, model = make_compact(tmp_path, opened=False)
    assert model.open_left(fill(tmp_path / AZAHAR_PATH, US_SET)) == []
    win.refresh()
    assert "Save into Azahar" in texts(win._top)


def list_height(dialog: ft.AlertDialog) -> float | None:
    """The height a dialog's list of choices is held to, if it scrolls."""
    body = dialog.content.content  # type: ignore[union-attr]
    return body.height if isinstance(body, ft.Container) else None


@pytest.mark.parametrize("size", [SMALL, THOR])
def test_dialog_lists_fit_a_short_screen(tmp_path: Path, size: tuple[float, float]) -> None:
    win, _ = make_compact(tmp_path, size)
    win.toggle("left:0")  # a selection adds Copy to... to More
    press(win._bottom, "more")
    dialog = last_dialog(win)
    limit = size[1] - DIALOG_CHROME
    height = list_height(dialog)
    if height is None:  # short enough not to scroll
        lines = dialog.content.content.controls  # type: ignore[union-attr]
        assert len(lines) * CHOICE_HEIGHT <= limit
    else:
        assert 2 * CHOICE_HEIGHT <= height <= max(limit, 2 * CHOICE_HEIGHT)


def test_text_dialogs_scroll_rather_than_overflow(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path, SMALL)
    win.show_confirm(Confirm("Sure?", "A question long enough to need room. " * 6, "Yes"))
    assert last_dialog(win).scrollable


BOTTOM_SCREEN = (360.0, 413.0)


def test_short_tabs_use_slim_strips_and_one_slim_pane(tmp_path: Path) -> None:
    """The Thor's bottom screen: tabs, but with the compact strips so the list has room."""
    win, _ = make_compact(tmp_path, BOTTOM_SCREEN)
    root = win.build()
    assert win.layout is Layout.TABS and win.narrow
    assert not any(b.visible for b in win._bands)
    assert win._top.content.height == theme.STRIP_HEIGHT
    assert win._bottom.content.height == theme.STRIP_HEIGHT
    assert not [c for c in walk(root) if isinstance(c, ft.Tabs)]
    lists = [c for c in walk(win._body) if isinstance(c, ft.ListView)]
    assert len(lists) == 1
    top = texts(win._top)
    assert {"Save", "Bank"} <= set(top) and tagged(win._top, "undo") and tagged(win._top, "write")
    assert "LOG 1" in texts(win._body)


def test_short_tabs_switch_to_the_bank(tmp_path: Path) -> None:
    win, model = make_compact(tmp_path, BOTTOM_SCREEN)
    press(win._top, "tab:1")
    assert win.tab_index == 1
    assert "BANK" in texts(win._body) and "LOG 1" not in texts(win._body)
    press(win._top, "tab:0")
    assert "LOG 1" in texts(win._body)


def test_short_tabs_header_picks_the_log(tmp_path: Path) -> None:
    win, model = make_compact(tmp_path, BOTTOM_SCREEN)
    press(win._body, "head")
    assert {"Log 1", "Log 2"} <= {o.split(" (")[0] for o in dialog_options(win)}


def test_short_tabs_bottom_strip_sends_and_more_has_the_rest(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path, BOTTOM_SCREEN)
    win.toggle("left:0")
    assert {"1 selected", "Send...", "More"} <= set(texts(win._bottom))
    press(win._bottom, "more")
    options = set(dialog_options(win))
    assert {"Copy to bank", "Move to...", "Remove", "Open save", "Find saves"} <= options


def test_desktop_rows_go_back_to_40_when_wide(tmp_path: Path) -> None:
    win, _ = make_compact(tmp_path, (1280.0, 800.0), DESKTOP_PROFILE)
    assert win._shells[PaneSide.LEFT].row_height == theme.ROW_HEIGHT
    win.apply_size(*SMALL)
    assert win._shells[PaneSide.LEFT].row_height == theme.COMPACT_ROW_HEIGHT
    win.apply_size(1280.0, 800.0)
    assert win._shells[PaneSide.LEFT].row_height == theme.ROW_HEIGHT


def test_compact_names_and_badges_keep_a_tight_line(tmp_path: Path) -> None:
    """Name (18) + badge (18) + gap fit 48 only with line height 1.0 on both."""
    win, _ = make_compact(tmp_path, SMALL, DESKTOP_PROFILE)
    row = next(
        c for c in walk(win._body.content) if isinstance(c, ft.Container) and c.data == "left:0"
    )
    lines = [t for t in walk(row) if isinstance(t, ft.Text) and t.size in (18, 12)]
    assert len(lines) == 2
    assert all(t.style is not None and t.style.height == 1.0 for t in lines)


def test_wide_compact_wide_keeps_the_list_and_its_scroll(tmp_path: Path) -> None:
    from test_drag import scroll_event

    win, _ = make_compact(tmp_path, (1280.0, 800.0), DESKTOP_PROFILE)
    shell = win._shells[PaneSide.LEFT]
    before = shell.list_control()
    assert before is not None
    before.on_scroll(scroll_event(before, 120.0))
    win.apply_size(*THOR)
    assert win.layout is Layout.COMPACT
    assert shell.list_control() is before and shell.scroll.pixels == 120.0
    win.apply_size(1280.0, 800.0)
    assert win.layout is Layout.WIDE
    assert shell.list_control() is before and shell.scroll.pixels == 120.0


@pytest.mark.parametrize("size", [SMALL, THOR])
def test_both_saves_changed_strip_says_write_both(
    tmp_path: Path, size: tuple[float, float]
) -> None:
    from model_helpers import pal_save

    win, model = make_compact(tmp_path, size, DESKTOP_PROFILE)
    model.open_right(pal_save(tmp_path))
    for side in (PaneSide.LEFT, PaneSide.RIGHT):
        model.toggle_row(side, 0)
        model.remove_selected(confirmed=True)
    win.refresh()
    assert model.toolbar().write_label == "Write changes to both saves"
    top = texts(win._top)
    assert "Write both" in top and "Write changes to both saves" not in top
    assert tapped(win._top, "write")
