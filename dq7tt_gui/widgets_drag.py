"""Dragging tablets between panes: what a drag carries, its feedback, and where it lands."""

import math
from dataclasses import dataclass

import flet as ft

from dq7tt_gui import theme
from dq7tt_gui.viewmodels import PaneSide, TabletRow

GROUP = "tablets"
FEEDBACK_RADIUS = 6
FEEDBACK_PADDING = 10
FEEDBACK_OPACITY = 0.92


@dataclass(frozen=True)
class DragPayload:
    """The tablets a drag carries: which pane they come from and their row positions."""

    side: PaneSide
    indexes: tuple[int, ...]


def payload_for(row: TabletRow, side: PaneSide, rows: tuple[TabletRow, ...]) -> DragPayload:
    """Dragging a selected row drags the whole selection; any other row drags alone."""
    if row.selected:
        return DragPayload(side, tuple(r.index for r in rows if r.selected))
    return DragPayload(side, (row.index,))


def feedback(row: TabletRow, count: int) -> ft.Control:
    label = row.name if count == 1 else f"{count} tablets"
    return ft.Container(
        content=ft.Text(label, color=theme.SELECTED_TEXT, size=14, max_lines=1),
        bgcolor=theme.SELECTED_BG,
        border=ft.Border.all(1, theme.ACCENT),
        border_radius=FEEDBACK_RADIUS,
        padding=ft.Padding.symmetric(horizontal=FEEDBACK_PADDING, vertical=6),
        opacity=FEEDBACK_OPACITY,
    )


def draggable(
    content: ft.Control, row: TabletRow, payload: DragPayload, touch: bool = False
) -> ft.Draggable:
    """Wrap a row's name area so it can be dragged to the other pane.

    On a touch screen the drag only starts on a sideways move (towards the other pane), so
    a swipe up or down still scrolls the list. Flet 1.0.4 has no long-press Draggable; the
    long press is left to the list, where it reorders.
    """
    return ft.Draggable(
        content=content,
        group=GROUP,
        data=payload,
        content_feedback=feedback(row, len(payload.indexes)),
        affinity=ft.Axis.HORIZONTAL if touch else None,
    )


def drop_index(
    y: float, count: int, scroll: float = 0.0, row_height: float = theme.ROW_HEIGHT
) -> int:
    """The gap a drop lands in: before the row under the dragged tablet's centre.

    `y` is the feedback's top-left, relative to the visible list; `scroll` is how far the list
    is scrolled; `row_height` is the list's own (taller on Android). Below the last row it is
    the end of the list.
    """
    row = math.floor((y + scroll + row_height / 2) / row_height)
    return min(max(row, 0), count)


@dataclass
class ScrollTracker:
    """The scroll offset of one pane list, fed by the list's on_scroll."""

    pixels: float = 0.0

    def on_scroll(self, e: ft.OnScrollEvent) -> None:
        self.pixels = e.pixels


def final_position(payload: DragPayload, dest: PaneSide, gap: int) -> int:
    """Where `gap` lands once the dragged row leaves, when it is dropped on its own pane."""
    # Only indexes[0]: the model refuses same-pane reorders of more than one row.
    if payload.side is dest and payload.indexes and payload.indexes[0] < gap:
        return gap - 1
    return gap
