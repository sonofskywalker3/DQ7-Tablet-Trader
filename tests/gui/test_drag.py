from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import flet as ft
import pytest
from test_widgets import callbacks, pane_view, row, walk
from test_window import make

from dq7tt.savefile import SlotRole
from dq7tt_gui import theme
from dq7tt_gui.viewmodels import LogChip, Outcome, PaneSide, PaneView, RightMode
from dq7tt_gui.widgets_drag import GROUP, DragPayload, drop_index
from dq7tt_gui.widgets_pane import PaneShell, pane


def three_rows(side: PaneSide, selected: tuple[int, ...] = ()) -> PaneView:
    rows = tuple(
        replace(row(selected=i in selected), index=i, name=f"Tablet {i}", key=f"{side.value}:{i}")
        for i in range(3)
    )
    return pane_view(side, rows=rows)


def accept(payload: object, y: float) -> SimpleNamespace:
    return SimpleNamespace(
        src=SimpleNamespace(data=payload), local_position=SimpleNamespace(x=0.0, y=y)
    )


def find(control: Any, kind: type) -> list[Any]:
    return [c for c in walk(control) if isinstance(c, kind)]


def shown(control: Any) -> list[str]:
    return [t.value for t in find(control, ft.Text)]


def test_row_names_are_draggable_in_the_tablets_group() -> None:
    ctl = pane(three_rows(PaneSide.LEFT), callbacks([]))
    drags = find(ctl, ft.Draggable)
    assert len(drags) == 3
    assert {d.group for d in drags} == {GROUP}
    assert drags[1].data == DragPayload(PaneSide.LEFT, (1,))


def test_dragging_a_selected_row_carries_the_whole_selection() -> None:
    ctl = pane(three_rows(PaneSide.LEFT, selected=(0, 2)), callbacks([]))
    drags = find(ctl, ft.Draggable)
    assert drags[0].data == DragPayload(PaneSide.LEFT, (0, 2))
    assert drags[2].data == DragPayload(PaneSide.LEFT, (0, 2))
    assert drags[1].data == DragPayload(PaneSide.LEFT, (1,))


def test_feedback_names_the_tablet_or_counts_the_selection() -> None:
    ctl = pane(three_rows(PaneSide.LEFT, selected=(0, 2)), callbacks([]))
    drags = find(ctl, ft.Draggable)
    assert shown(drags[1].content_feedback) == ["Tablet 1"]
    assert shown(drags[0].content_feedback) == ["2 tablets"]


def test_grip_stays_outside_the_draggable_name_area() -> None:
    ctl = pane(three_rows(PaneSide.LEFT), callbacks([]))
    for d in find(ctl, ft.Draggable):
        assert not find(d, ft.ReorderableDragHandle)
    assert len(find(ctl, ft.ReorderableDragHandle)) == 3


def test_pane_list_is_a_drop_target_in_the_same_group() -> None:
    ctl = pane(three_rows(PaneSide.RIGHT), callbacks([]), RightMode.SAVE)
    (target,) = find(ctl, ft.DragTarget)
    assert target.group == GROUP


def test_drop_reports_payload_and_index_where_dropped() -> None:
    log: list[object] = []
    cbs = callbacks(log)
    cbs.on_drop = lambda p, i: log.append(("drop", p, i))
    ctl = pane(three_rows(PaneSide.RIGHT), cbs, RightMode.SAVE)
    (target,) = find(ctl, ft.DragTarget)
    payload = DragPayload(PaneSide.LEFT, (0, 2))
    target.on_accept(accept(payload, theme.ROW_HEIGHT * 1.0))
    target.on_accept(accept(payload, 5000.0))
    assert log == [("drop", payload, 1), ("drop", payload, 3)]


def test_drop_ignores_foreign_data() -> None:
    log: list[object] = []
    cbs = callbacks(log)
    cbs.on_drop = lambda p, i: log.append("drop")
    ctl = pane(three_rows(PaneSide.RIGHT), cbs, RightMode.SAVE)
    (target,) = find(ctl, ft.DragTarget)
    target.on_accept(accept("left:1", 10.0))
    assert log == []


def test_empty_bank_pane_still_accepts_drops_at_the_start() -> None:
    log: list[object] = []
    cbs = callbacks(log)
    cbs.on_drop = lambda p, i: log.append(i)
    view = pane_view(PaneSide.RIGHT, rows=(), empty_text="Nothing here")
    ctl = pane(view, cbs, RightMode.BANK)
    (target,) = find(ctl, ft.DragTarget)
    target.on_accept(accept(DragPayload(PaneSide.LEFT, (0,)), 90.0))
    assert log == [0]


def test_drop_index_rounds_to_nearest_gap_and_clamps() -> None:
    h = theme.ROW_HEIGHT
    assert drop_index(-30.0, 5) == 0
    assert drop_index(h * 0.4, 5) == 0
    assert drop_index(h * 0.6, 5) == 1
    assert drop_index(h * 99, 5) == 5
    assert drop_index(10.0, 0) == 0


def test_save_rows_are_reorderable_but_bank_rows_are_not() -> None:
    save = pane(three_rows(PaneSide.LEFT), callbacks([]))
    assert find(save, ft.ReorderableListView)
    bank = pane(three_rows(PaneSide.RIGHT), callbacks([]), RightMode.BANK)
    assert not find(bank, ft.ReorderableListView)
    assert not find(bank, ft.ReorderableDragHandle)


def test_flet_reorder_event_new_index_is_final_position(tmp_path: Any) -> None:
    """Flet 1.0.4 already subtracts one when moving down (reorderable_list_view.dart,
    onReorder: `if (oldIndex < newIndex) newIndex -= 1`), so the event's new_index is the
    final position and goes to the model unchanged."""
    win, model = make(tmp_path)
    before = [r.name for r in model.left().rows]
    (lv,) = find(win._body.content, ft.ReorderableListView)[:1]
    # Dragging row 0 below row 1: Flutter says (0, 2); Flet reports (0, 1).
    lv.on_reorder(ft.OnReorderEvent(name="reorder", control=lv, old_index=0, new_index=1))
    after = [r.name for r in model.left().rows]
    assert after[:2] == [before[1], before[0]]
    assert after[2:] == before[2:]


def spy_drop(model: Any, monkeypatch: pytest.MonkeyPatch) -> list[tuple[object, ...]]:
    calls: list[tuple[object, ...]] = []

    def spy(*args: object) -> Outcome:
        calls.append(args)
        return []

    monkeypatch.setattr(model, "drop", spy)
    return calls


def test_drop_on_right_pane_calls_model_drop(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    win, model = make(tmp_path)
    calls = spy_drop(model, monkeypatch)
    right = find(win._body.content, ft.DragTarget)[1]
    payload = DragPayload(PaneSide.LEFT, (0, 2))
    right.on_accept(accept(payload, theme.ROW_HEIGHT * 2.0))
    # The bank is empty here, so any spot is the end of the list.
    assert calls == [(PaneSide.LEFT, (0, 2), PaneSide.RIGHT, 0)]


def test_drop_within_the_same_pane_lands_at_the_final_position(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    win, model = make(tmp_path)
    calls = spy_drop(model, monkeypatch)
    left = find(win._body.content, ft.DragTarget)[0]
    left.on_accept(accept(DragPayload(PaneSide.LEFT, (0,)), theme.ROW_HEIGHT * 3.0))
    left.on_accept(accept(DragPayload(PaneSide.LEFT, (5,)), theme.ROW_HEIGHT * 2.0))
    # Gap 3 with row 0 removed first is position 2; a row from below the gap is unaffected.
    assert calls == [
        (PaneSide.LEFT, (0,), PaneSide.LEFT, 2),
        (PaneSide.LEFT, (5,), PaneSide.LEFT, 2),
    ]


def test_drop_gap_uses_the_row_under_the_dragged_tablet_centre() -> None:
    h = theme.ROW_HEIGHT
    assert drop_index(h * 1.0 - 1, 5) == 1  # centre is in row 1, so insert before it
    assert drop_index(h * 0.4, 5) == 0
    assert drop_index(h * 0.6, 5) == 1


def test_scrolled_list_adds_its_offset_to_the_drop() -> None:
    log: list[object] = []
    cbs = callbacks(log)
    cbs.on_drop = lambda p, i: log.append(i)
    view = pane_view(
        PaneSide.RIGHT,
        rows=tuple(replace(row(), index=i, key=f"right:{i}") for i in range(20)),
    )
    ctl = pane(view, cbs, RightMode.SAVE)
    (target,) = find(ctl, ft.DragTarget)
    (lv,) = find(ctl, ft.ReorderableListView)
    scroll = ft.OnScrollEvent(
        name="scroll",
        control=lv,
        event_type=ft.ScrollType.UPDATE,
        pixels=theme.ROW_HEIGHT * 10,
        min_scroll_extent=0.0,
        max_scroll_extent=1000.0,
        viewport_dimension=300.0,
    )
    lv.on_scroll(scroll)
    target.on_accept(accept(DragPayload(PaneSide.LEFT, (0,)), theme.ROW_HEIGHT * 2.0))
    assert log == [12]


def scroll_event(lv: ft.Control, pixels: float) -> ft.OnScrollEvent:
    return ft.OnScrollEvent(
        name="scroll",
        control=lv,  # type: ignore[arg-type]
        event_type=ft.ScrollType.UPDATE,
        pixels=pixels,
        min_scroll_extent=0.0,
        max_scroll_extent=1000.0,
        viewport_dimension=300.0,
    )


def test_both_list_kinds_track_the_scroll_offset() -> None:
    for mode in (RightMode.SAVE, RightMode.BANK):
        shell = PaneShell()
        shell.update(three_rows(PaneSide.RIGHT), callbacks([]), mode)
        lv = shell.list_control()
        assert lv is not None
        lv.on_scroll(scroll_event(lv, 123.0))
        assert shell.scroll.pixels == 123.0


def test_redraw_of_the_same_log_keeps_the_list_and_its_offset() -> None:
    shell = PaneShell()
    shell.update(three_rows(PaneSide.LEFT), callbacks([]), RightMode.SAVE)
    lv = shell.list_control()
    tracker = shell.scroll
    lv.on_scroll(scroll_event(lv, 200.0))  # type: ignore[union-attr]
    shell.update(three_rows(PaneSide.LEFT, selected=(1,)), callbacks([]), RightMode.SAVE)
    assert shell.list_control() is lv
    assert shell.scroll is tracker and shell.scroll.pixels == 200.0
    assert len(lv.controls) == 3  # type: ignore[union-attr]


def test_switching_logs_starts_a_fresh_list_at_the_top() -> None:
    def chips(active: SlotRole) -> tuple[LogChip, ...]:
        return tuple(
            LogChip(r, r.name, "", r is active, False) for r in (SlotRole.LOG_1, SlotRole.LOG_2)
        )

    shell = PaneShell()
    view = three_rows(PaneSide.LEFT)
    shell.update(replace(view, log_chips=chips(SlotRole.LOG_1)), callbacks([]), RightMode.SAVE)
    lv = shell.list_control()
    lv.on_scroll(scroll_event(lv, 200.0))  # type: ignore[union-attr]
    shell.update(replace(view, log_chips=chips(SlotRole.LOG_2)), callbacks([]), RightMode.SAVE)
    assert shell.list_control() is not lv
    assert shell.scroll.pixels == 0.0


def test_window_redraw_after_a_tick_keeps_the_same_list(tmp_path: Any) -> None:
    win, _ = make(tmp_path)
    body = win._body.content
    lv = find(body, ft.ReorderableListView)[0]
    lv.on_scroll(scroll_event(lv, 80.0))
    win.toggle("left:0")
    assert win._body.content is body
    assert find(win._body.content, ft.ReorderableListView)[0] is lv
    assert win._shells[PaneSide.LEFT].scroll.pixels == 80.0


def test_narrow_tick_keeps_list_offset_and_selected_tab(tmp_path: Any) -> None:
    win, _ = make(tmp_path, width=600.0)
    tabs = win._body.content
    lv = find(tabs, ft.ReorderableListView)[0]
    lv.on_scroll(scroll_event(lv, 80.0))
    win.tab_index = 1
    win.toggle("left:0")
    assert win._body.content is tabs
    assert find(win._body.content, ft.ReorderableListView)[0] is lv
    assert win._shells[PaneSide.LEFT].scroll.pixels == 80.0
    assert tabs.selected_index == 1


def test_wide_narrow_wide_keeps_each_panes_list(tmp_path: Any) -> None:
    win, _ = make(tmp_path)
    before = win._shells[PaneSide.LEFT].list_control()
    win.apply_width(600.0)
    assert win._shells[PaneSide.LEFT].list_control() is before
    assert find(win._body.content, ft.ReorderableListView)[0] is before
    win.apply_width(1280.0)
    assert win._shells[PaneSide.LEFT].list_control() is before
    assert find(win._body.content, ft.ReorderableListView)[0] is before
    assert win._shells[PaneSide.LEFT].scroll.pixels == 0.0


def test_close_and_reopen_drops_by_unscrolled_position(tmp_path: Any) -> None:
    from model_helpers import us_save

    win, model = make(tmp_path)
    lv = find(win._body.content, ft.ReorderableListView)[0]
    lv.on_scroll(scroll_event(lv, 400.0))
    assert model.close_left() == []
    win.refresh()
    assert model.open_left(us_save(tmp_path)) == []
    win.refresh()
    left = find(win._body.content, ft.DragTarget)[0]
    log: list[tuple[object, ...]] = []
    win.model.drop = lambda *a: log.append(a) or []  # type: ignore[method-assign]
    left.on_accept(accept(DragPayload(PaneSide.RIGHT, (0,)), theme.ROW_HEIGHT * 2.0))
    assert log == [(PaneSide.RIGHT, (0,), PaneSide.LEFT, 2)]
