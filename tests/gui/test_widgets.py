from collections.abc import Callable, Iterator

import flet as ft

from dq7tt.savefile import SlotRole
from dq7tt.tablets import TabletKind
from dq7tt_gui import art, theme, widgets, widgets_bars
from dq7tt_gui.viewmodels import (
    ActionBar,
    FolderChip,
    LogChip,
    PaneSide,
    PaneView,
    RightMode,
    TabletRow,
    ToolbarView,
)
from dq7tt_gui.widgets_drag import DragPayload
from dq7tt_gui.widgets_pane import PaneCallbacks, pane


def walk(control: ft.Control) -> Iterator[ft.Control]:
    yield control
    content = getattr(control, "content", None)
    if isinstance(content, ft.Control):
        yield from walk(content)
    for child in getattr(control, "controls", None) or []:
        yield from walk(child)


def texts(control: ft.Control) -> list[str]:
    return [c.value for c in walk(control) if isinstance(c, ft.Text)]


def buttons(control: ft.Control) -> list[ft.Button]:
    return [c for c in walk(control) if isinstance(c, ft.Button)]


def label(button: ft.Button) -> str:
    return " ".join(texts(button))


def button_labels(control: ft.Control) -> list[str]:
    return [label(b) for b in buttons(control)]


def noop() -> None:
    return None


def row(selected: bool = False, kind: TabletKind = TabletKind.DLC) -> TabletRow:
    return TabletRow(3, "Mount Oddna", kind, 2, selected, "left:3")


def pane_view(side: PaneSide = PaneSide.LEFT, **kw: object) -> PaneView:
    base: dict[str, object] = {
        "side": side,
        "title": "Checkpoint backup",
        "subtitle": "US",
        "empty_text": None,
        "log_chips": (),
        "folder_chips": (),
        "rows": (row(),),
        "count_text": "1 tablet",
    }
    base.update(kw)
    return PaneView(**base)  # type: ignore[arg-type]


def callbacks(log: list[object]) -> PaneCallbacks:
    return PaneCallbacks(
        on_pick_log=lambda r: log.append(("log", r)),
        on_pick_folder=lambda n: log.append(("folder", n)),
        on_toggle=lambda k: log.append(("toggle", k)),
        on_close=lambda: log.append("close"),
        on_mode=lambda m: log.append(("mode", m)),
        on_new_folder=lambda: log.append("new"),
        on_reorder=lambda a, b: log.append(("reorder", a, b)),
        on_drop=lambda p, i: log.append(("drop", p, i)),
        on_bank_all=lambda: log.append("bank all"),
        on_put_into_azahar=lambda: log.append("put"),
    )


def click(control: ft.Control) -> None:
    handler: Callable[..., object] = control.on_click  # type: ignore[attr-defined]
    handler(None)


def images(control: ft.Control) -> list[ft.Image]:
    return [c for c in walk(control) if isinstance(c, ft.Image)]


def row_cells(ctl: ft.Container) -> list[ft.Control]:
    """The parts of a row after the pointer (and grip): check box, stone, name, kind, clears."""
    cells = ctl.content.controls[-1]  # type: ignore[union-attr]
    return list(cells.content.controls)  # type: ignore[union-attr]


def test_kind_badge_writes_the_kind_in_its_colour() -> None:
    badge = widgets.kind_badge(TabletKind.STORY)
    assert badge.bgcolor is None
    assert texts(badge) == ["Story"]
    shown = next(c for c in walk(badge) if isinstance(c, ft.Text))
    assert shown.color == theme.KIND_COLORS[TabletKind.STORY]


def test_row_shows_stone_name_kind_clears_and_toggles() -> None:
    log: list[object] = []
    ctl = widgets.tablet_row(row(), log.append)
    assert texts(ctl) == ["Mount Oddna", "DLC", "2"]
    name = next(c for c in walk(ctl) if isinstance(c, ft.Text) and c.value == "Mount Oddna")
    assert name.overflow == ft.TextOverflow.ELLIPSIS
    assert ctl.bgcolor is None
    stone = [i.src for i in images(ctl) if i.src != art.POINTER]
    assert stone == [art.TABLET_ICONS[TabletKind.DLC]]
    for part in walk(ctl):
        if getattr(part, "on_click", None) is not None:
            click(part)
    assert log == ["left:3", "left:3"]  # the pointer's room and the cells both toggle


def hover(control: ft.Control, inside: bool) -> None:
    handler: Callable[..., object] = control.on_hover  # type: ignore[attr-defined]
    handler(ft.Event(name="hover", control=control, data=inside))  # type: ignore[arg-type]


def test_row_tells_the_pane_when_the_mouse_comes_and_goes() -> None:
    seen: list[tuple[int, bool]] = []
    ctl = widgets.tablet_row(row(), noop, on_hover=lambda i, inside: seen.append((i, inside)))
    hover(ctl, True)
    hover(ctl, False)
    assert seen == [(3, True), (3, False)]
    assert not [i for i in images(ctl) if i.src == art.POINTER]  # the pane draws the pointer


def test_pane_floats_its_pointer_beside_the_row_under_the_mouse(monkeypatch) -> None:
    from dq7tt_gui.widgets_pane import POINTER_TOP, PaneShell

    shell = PaneShell()
    view = pane_view(rows=(row(), TabletRow(4, "Mount Oddna", TabletKind.DLC, 0, False, "left:4")))
    shell.update(view, callbacks([]), RightMode.SAVE)
    monkeypatch.setattr(shell.pointer, "update", noop)
    items = shell.list_control().controls  # type: ignore[union-attr]
    second = items[1].content  # the row inside its keyed holder
    hover(second, True)
    assert shell.pointer.visible and shell.pointer.top == 4 * theme.ROW_HEIGHT + POINTER_TOP
    hover(items[0].content, False)  # leaving another row does not hide it
    assert shell.pointer.visible
    hover(second, False)
    assert not shell.pointer.visible
    assert shell.pointer.ignore_interactions  # it never takes the mouse from the rows


def test_row_name_takes_the_room_so_kind_and_clears_line_up() -> None:
    drag = DragPayload(PaneSide.LEFT, (3,))
    for ctl in (widgets.tablet_row(row(), noop), widgets.tablet_row(row(), noop, drag)):
        cells = row_cells(ctl)
        assert [bool(c.expand) for c in cells] == [False, False, True, False, False]
        assert [c.width for c in cells[3:]] == [widgets.KIND_COLUMN_W, widgets.CLEARS_COLUMN_W]
        assert cells[3].alignment == ft.Alignment.CENTER_LEFT


def test_row_keeps_the_grip_out_of_the_parts_that_tick() -> None:
    grip = ft.Container(width=widgets.GRIP_SLOT)
    ctl = widgets.tablet_row(row(), noop, grip=grip)
    parts = ctl.content.controls  # type: ignore[union-attr]
    assert parts[1] is grip and grip.on_click is None
    assert parts[0].width == widgets.ROW_INSET


def test_selected_row_is_washed_gold_with_a_gold_tick() -> None:
    ctl = widgets.tablet_row(row(selected=True), lambda k: None)
    assert ctl.bgcolor == theme.SELECTED_BG
    box = row_cells(ctl)[0]
    assert box.bgcolor == theme.GOLD
    assert isinstance(box.content, ft.Icon)
    assert row_cells(widgets.tablet_row(row(), noop))[0].content is None


def test_log_chip_marks_active_and_picks() -> None:
    picked: list[SlotRole] = []
    chip = LogChip(SlotRole.LOG_1, "Log 1", "Auster, 135h", True, False, "24/24")
    other = LogChip(SlotRole.LOG_2, "Log 2", "Auster, 135h", False, False, "23/24")
    on = widgets.log_chip(chip, picked.append)
    off = widgets.log_chip(other, picked.append)
    assert on.bgcolor == theme.GOLD_WASH and on.border.top.color == theme.GOLD
    assert off.bgcolor == theme.CHIP and off.border.top.color == theme.CHIP_BORDER
    assert texts(on) == ["Log 1", "24/24", "Auster, 135h"]
    assert on.alignment == ft.Alignment.CENTER_LEFT  # its line sets its width
    click(on)
    assert picked == [SlotRole.LOG_1]


def test_muted_quick_save_chip_is_dim() -> None:
    chip = LogChip(SlotRole.QUICK_SAVE, "Quick save", "", False, True)
    ctl = widgets.log_chip(chip, lambda r: None)
    assert ctl.bgcolor is None
    assert all(c.color == theme.DIM for c in walk(ctl) if isinstance(c, ft.Text))


def test_folder_chip_active_and_count() -> None:
    picked: list[str] = []
    on = widgets.folder_chip(FolderChip("haven", "Haven DLC", 20, True), picked.append)
    off = widgets.folder_chip(FolderChip("story", "Story", 3, False), picked.append)
    assert on.bgcolor == theme.GOLD_WASH
    assert off.bgcolor == theme.CHIP
    assert on.alignment is None  # folder chips are as wide as their names
    assert texts(on) == ["Haven DLC", "20"]
    click(off)
    assert picked == ["story"]


def test_action_bar_hides_remove_when_not_allowed() -> None:
    cbs = widgets_bars.ActionCallbacks(noop, noop, noop, noop, noop)
    full = ActionBar(2, "2 tablets selected", "Copy to Haven DLC", True, True, True)
    assert button_labels(widgets_bars.action_bar(full, cbs)) == [
        "Copy to Haven DLC",
        "Copy to...",
        "Move to...",
        "Reset clears",
        "Remove",
    ]
    part = ActionBar(2, "2 tablets selected", None, False, False, False)
    ctl = widgets_bars.action_bar(part, cbs)
    assert button_labels(ctl) == ["Copy to..."]
    assert "2 tablets selected" in texts(ctl)


def test_action_bar_empty_selection_has_no_buttons() -> None:
    cbs = widgets_bars.ActionCallbacks(noop, noop, noop, noop, noop)
    ctl = widgets_bars.action_bar(ActionBar(0, "", None, False, False, False), cbs)
    assert button_labels(ctl) == []


def test_action_bar_buttons_call_back() -> None:
    log: list[str] = []
    cbs = widgets_bars.ActionCallbacks(
        on_quick_copy=lambda: log.append("quick"),
        on_copy=lambda: log.append("copy"),
        on_move=lambda: log.append("move"),
        on_reset=lambda: log.append("reset"),
        on_remove=lambda: log.append("remove"),
    )
    bar = ActionBar(1, "1 tablet selected", "Copy to X", True, True, True)
    for b in buttons(widgets_bars.action_bar(bar, cbs)):
        click(b)
    assert log == ["quick", "copy", "move", "reset", "remove"]


def test_toolbar_labels_and_disabled_states() -> None:
    cbs = widgets_bars.ToolbarCallbacks(noop, noop, noop, noop, noop)
    view = ToolbarView("Copy 2 tablets to Haven DLC", None, False, "Write changes")
    bs = {label(b): b for b in buttons(widgets_bars.toolbar(view, cbs))}
    assert set(bs) == {
        "Open save",
        "Find saves",
        "Undo: Copy 2 tablets to Haven DLC",
        "Redo",
        "Write changes",
    }
    assert not bs["Undo: Copy 2 tablets to Haven DLC"].disabled
    assert bs["Redo"].disabled
    assert bs["Write changes"].disabled
    on = ToolbarView(None, "Remove 1 tablet", True, "Write changes to both saves")
    bs = {label(b): b for b in buttons(widgets_bars.toolbar(on, cbs))}
    assert bs["Undo"].disabled
    assert not bs["Redo: Remove 1 tablet"].disabled
    assert not bs["Write changes to both saves"].disabled


def test_toolbar_buttons_call_back() -> None:
    log: list[str] = []
    cbs = widgets_bars.ToolbarCallbacks(
        on_open=lambda: log.append("open"),
        on_find=lambda: log.append("find"),
        on_undo=lambda: log.append("undo"),
        on_redo=lambda: log.append("redo"),
        on_write=lambda: log.append("write"),
    )
    for b in buttons(widgets_bars.toolbar(ToolbarView("a", "b", True, "Write changes"), cbs)):
        click(b)
    assert log == ["open", "find", "undo", "redo", "write"]


def test_left_pane_shows_title_chips_rows_and_close() -> None:
    chips = (LogChip(SlotRole.LOG_1, "Log 1", "d", True, False),)
    ctl = pane(pane_view(log_chips=chips), callbacks([]))
    t = texts(ctl)
    assert "Checkpoint backup" in t and "US" in t and "Log 1" in t
    assert "Mount Oddna" in t and "Tablet" in t and "Clears" in t
    assert "Close" in button_labels(ctl)
    assert "Bank" not in t


def test_pane_empty_text_replaces_list() -> None:
    ctl = pane(pane_view(rows=(), empty_text="Open a save to begin"), callbacks([]))
    t = texts(ctl)
    assert "Open a save to begin" in t
    assert "Tablet" not in t


def test_bank_pane_has_mode_switch_new_folder_and_folder_chips() -> None:
    log: list[object] = []
    view = pane_view(PaneSide.RIGHT, folder_chips=(FolderChip("h", "Haven DLC", 20, True),))
    ctl = pane(view, callbacks(log), RightMode.BANK)
    labels = button_labels(ctl)
    assert {"Bank", "Open a second save", "New folder"} <= set(labels)
    assert "Close" not in labels
    for b in buttons(ctl):
        if label(b) in ("Open a second save", "New folder"):
            click(b)
    assert log == [("mode", RightMode.SAVE), "new"]


def test_save_mode_right_pane_has_close_and_no_new_folder() -> None:
    ctl = pane(pane_view(PaneSide.RIGHT), callbacks([]), RightMode.SAVE)
    labels = button_labels(ctl)
    assert "New folder" not in labels and "Close" in labels and "Bank" in labels


def test_pane_row_toggle_reaches_callback() -> None:
    log: list[object] = []
    ctl = pane(pane_view(), callbacks(log))
    target = next(
        c
        for c in walk(ctl)
        if isinstance(c, ft.Container)
        and c.height == theme.ROW_HEIGHT
        and "Mount Oddna" in texts(c)
    )
    click(target)
    assert log == [("toggle", "left:3")]


def test_save_rows_are_reorderable() -> None:
    log: list[object] = []
    view = pane_view(PaneSide.RIGHT, rows=(row(), row()))
    ctl = pane(view, callbacks(log), RightMode.SAVE)
    lv = next(c for c in walk(ctl) if isinstance(c, ft.ReorderableListView))
    event = ft.OnReorderEvent(name="reorder", control=lv, old_index=0, new_index=1)
    lv.on_reorder(event)  # type: ignore[misc]
    assert log == [("reorder", 0, 1)]


def test_disabled_write_button_text_is_muted() -> None:
    cbs = widgets_bars.ToolbarCallbacks(noop, noop, noop, noop, noop)
    ctl = widgets_bars.toolbar(ToolbarView(None, None, False, "Write changes"), cbs)
    write = next(b for b in buttons(ctl) if label(b) == "Write changes")
    assert next(c for c in walk(write) if isinstance(c, ft.Text)).color == theme.DIM


def test_long_undo_label_is_capped_with_tooltip() -> None:
    cbs = widgets_bars.ToolbarCallbacks(noop, noop, noop, noop, noop)
    long = "Copy 12 tablets to Haven DLC and Story"
    ctl = widgets_bars.toolbar(ToolbarView(long, None, False, "Write changes"), cbs)
    undo = next(b for b in buttons(ctl) if label(b).startswith("Undo"))
    shown = next(c for c in walk(undo) if isinstance(c, ft.Text))
    assert shown.width == widgets.HISTORY_LABEL_MAX_W
    assert undo.tooltip == f"Undo: {long}"


def test_folder_chip_is_touch_height_and_handle_has_tooltip() -> None:
    chip = widgets.folder_chip(FolderChip("a", "A", 1, False), lambda n: None)
    assert chip.height >= 40
    view = pane_view(PaneSide.RIGHT)
    ctl = pane(view, callbacks([]), RightMode.SAVE)
    handle = next(c for c in walk(ctl) if isinstance(c, ft.ReorderableDragHandle))
    assert handle.tooltip == "Drag to reorder"


def test_column_titles_are_inset_like_the_rows_below() -> None:
    def titles(mode: RightMode) -> ft.Container:
        ctl = pane(pane_view(PaneSide.RIGHT), callbacks([]), mode)
        hits = [
            c
            for c in walk(ctl)
            if isinstance(c, ft.Container) and {"Tablet", "Kind"} <= set(texts(c))
        ]
        return hits[-1]  # the innermost: the titles bar itself

    save, bank = titles(RightMode.SAVE), titles(RightMode.BANK)
    assert save.padding.right == bank.padding.right == widgets.ROW_PADDING_R
    # Over the name: past the pointer, (the grip,) the check box and the stone.
    assert bank.padding.left == widgets.ROW_INSET + widgets.NAME_START
    assert save.padding.left == bank.padding.left + widgets.GRIP_SLOT


def test_bank_keeps_the_second_saves_log_chips_beside_its_folders() -> None:
    view = pane_view(
        PaneSide.RIGHT,
        log_chips=(LogChip(SlotRole.LOG_1, "Log 1", "Auster, 135h", False, False, "24/24"),),
        folder_chips=(FolderChip("h", "Haven DLC", 20, True),),
    )
    shown = texts(pane(view, callbacks([]), RightMode.BANK))
    assert "Log 1" in shown and "Haven DLC" in shown


def test_pane_tabs_wrap_rather_than_push_new_folder_out() -> None:
    ctl = pane(pane_view(PaneSide.RIGHT), callbacks([]), RightMode.BANK)
    tabs = next(
        c
        for c in walk(ctl)
        if isinstance(c, ft.Row) and "Open a second save" in button_labels(c) and c.wrap
    )
    assert "New folder" not in button_labels(tabs)


# The Windows frame takes a few pixels of the window's width from the page.
WINDOW_FRAME_ALLOWANCE = 16


def test_log_chips_sit_four_to_a_line_when_they_fit_and_two_otherwise() -> None:
    from dq7tt_gui import widgets_pane_head as head

    chips = tuple(LogChip(r, r.name, "", False, False, "24/24") for r in SlotRole)
    ctl = pane(pane_view(log_chips=chips), callbacks([]))
    (line,) = [c for c in walk(ctl) if isinstance(c, ft.ResponsiveRow)]
    assert len(line.controls) == len(chips)
    assert all(c.col == head.LOG_CHIP_COLS for c in line.controls)
    edges = list(line.breakpoints.values())
    assert edges == sorted(edges)
    assert head.FOUR_CHIPS_NARROW < theme.NARROW_WIDTH < head.FOUR_CHIPS_WIDE
    # The default window shows the four logs on one line, as the design does.
    assert head.FOUR_CHIPS_WIDE <= theme.WINDOW_W - WINDOW_FRAME_ALLOWANCE
