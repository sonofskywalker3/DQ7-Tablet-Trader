"""One side of the window: a menu window with its header, chips and the tablet list."""

import flet as ft

from dq7tt_gui import art, theme
from dq7tt_gui.viewmodels import PaneSide, PaneView, RightMode, TabletRow
from dq7tt_gui.widgets import GRIP_SIZE, GRIP_SLOT, POINTER_LEFT, RowHover, tablet_row, text
from dq7tt_gui.widgets_drag import GROUP, DragPayload, ScrollTracker, drop_index, payload_for
from dq7tt_gui.widgets_frame import menu_window, pointer
from dq7tt_gui.widgets_pane_head import (
    BANK_ALL_LABEL,
    PUT_LABEL,
    PaneCallbacks,
    chips,
    column_titles,
    header,
)

__all__ = ["BANK_ALL_LABEL", "GRIP_SIZE", "PUT_LABEL", "PaneCallbacks", "PaneShell", "pane"]

WINDOW_BOTTOM = 8
COMPASS_SIZE = 250
COMPASS_RIGHT = 18
COMPASS_BOTTOM = 14
EMPTY_PADDING = 24
POINTER_TOP = (theme.ROW_HEIGHT - theme.POINTER_H) / 2


def _drag_row(
    row: TabletRow,
    view: PaneView,
    cbs: PaneCallbacks,
    narrow: bool,
    hover: RowHover,
    grip: ft.Control | None = None,
) -> ft.Container:
    """A row whose name drags to the other pane; on a touch screen (narrow) it only scrolls."""
    drag = None if narrow else payload_for(row, view.side, view.rows)
    return tablet_row(row, cbs.on_toggle, drag, grip, hover)


def _grip() -> ft.ReorderableDragHandle:
    return ft.ReorderableDragHandle(
        tooltip="Drag to reorder",
        content=ft.Container(
            content=ft.Icon(ft.Icons.DRAG_INDICATOR, color=theme.GRIP, size=GRIP_SIZE),
            width=GRIP_SLOT,
            height=theme.ROW_HEIGHT,
            alignment=ft.Alignment.CENTER_LEFT,
        ),
    )


def _reorder_items(
    view: PaneView, cbs: PaneCallbacks, narrow: bool, hover: RowHover
) -> list[ft.Control]:
    return [
        ft.Container(key=row.key, content=_drag_row(row, view, cbs, narrow, hover, _grip()))
        for row in view.rows
    ]


def _plain_items(
    view: PaneView, cbs: PaneCallbacks, narrow: bool, hover: RowHover
) -> list[ft.Control]:
    return [_drag_row(r, view, cbs, narrow, hover) for r in view.rows]


def _empty_body(view: PaneView) -> ft.Control:
    return ft.Container(
        content=text(view.empty_text or "", color=theme.MUTED),
        alignment=ft.Alignment.CENTER,
        expand=True,
        padding=ft.Padding.all(EMPTY_PADDING),
    )


def _identity(view: PaneView, mode: RightMode) -> tuple[object, ...]:
    """What a pane is showing; when it changes the list starts again at the top."""
    return (
        view.side,
        mode if view.side == PaneSide.RIGHT else None,
        view.title,
        view.subtitle,
        tuple(c.role for c in view.log_chips if c.active),
        tuple(c.name for c in view.folder_chips if c.active),
        view.empty_text is not None,
    )


class PaneShell:
    """One pane whose controls live across redraws.

    Flet keeps a control's state (the list's scroll position) only while the same Python
    object stays in the tree: a rebuilt single-child field (`Container.content`) is replaced
    and remounted (flet/controls/object_patch.py, `_compare_values`: a non-frozen `src is not
    dst` takes the `_item_replaced` branch). So the outer container, column, drop target and
    list are created once and `update` only changes their lists in place; list items carry
    keys so Flet reconciles them. A new list (and tracker) is made only when the pane shows
    something else, which also puts it back at the top.
    """

    def __init__(self) -> None:
        self.scroll = ScrollTracker()
        # The pointer floats over the list, beside the row the mouse is on. One control for
        # the whole pane: the rows themselves are rebuilt on every redraw and Flet freezes
        # what it reconciles by key, so a pointer inside a row could not be shown or hidden.
        self.pointer = ft.Container(
            content=pointer(), left=POINTER_LEFT, top=0, visible=False, ignore_interactions=True
        )
        self._hovered: int | None = None
        # Left loose: with StackFit.EXPAND Flutter lays the list out against the pane's top.
        self._list_stack = ft.Stack([])
        self._identity: tuple[object, ...] | None = None
        self._bank = False
        self._list: ft.ListView | None = None
        self._view: PaneView | None = None
        self._cbs: PaneCallbacks | None = None
        self._target = ft.DragTarget(
            content=ft.Container(), group=GROUP, on_accept=self._on_accept, expand=True
        )
        self._rows = ft.Column(spacing=0, expand=True)
        self._body = ft.Container(
            content=self._rows, expand=True, padding=ft.Padding(left=0, top=0, right=0, bottom=4)
        )
        self._column = ft.Column(spacing=0, expand=True)
        # The bank's window has a big faint compass in its corner, drawn behind the list.
        self._compass = ft.Container(
            content=ft.Image(src=art.COMPASS_FAINT, width=COMPASS_SIZE, height=COMPASS_SIZE),
            right=COMPASS_RIGHT,
            bottom=COMPASS_BOTTOM,
            visible=False,
        )
        self.control = menu_window(
            ft.Stack([self._compass, self._column], fit=ft.StackFit.EXPAND, expand=True),
            padding=ft.Padding.only(bottom=WINDOW_BOTTOM),
            expand=True,
        )

    def reset(self) -> None:
        """Forget the list: the pane is not showing it (for example an empty state)."""
        self._identity = None
        self._list = None
        self.scroll = ScrollTracker()

    def list_control(self) -> ft.ListView | None:
        return self._list

    def update(
        self, view: PaneView, cbs: PaneCallbacks, mode: RightMode, narrow: bool = False
    ) -> ft.Container:
        """Bring the pane up to date with `view` and return its (persistent) control."""
        self._view, self._cbs = view, cbs
        self._compass.visible = view.side == PaneSide.RIGHT and mode == RightMode.BANK
        parts: list[ft.Control] = [header(view, cbs, mode, narrow)]
        chip_line = chips(view, cbs)
        if chip_line is not None:
            parts.append(chip_line)
        parts.append(self._body)
        self._column.controls = parts
        self._fill_body(view, cbs, mode, narrow)
        return self.control

    def _fill_body(self, view: PaneView, cbs: PaneCallbacks, mode: RightMode, narrow: bool) -> None:
        identity = _identity(view, mode)
        bank = view.side == PaneSide.RIGHT and mode == RightMode.BANK
        if view.empty_text is not None:
            if identity != self._identity:
                self.scroll, self._list = ScrollTracker(), None
                self._target.content = _empty_body(view)
            self._identity = identity
            self._rows.controls = [self._target]
            return
        build = _plain_items if bank else _reorder_items
        items = build(view, cbs, narrow, self._on_row_hover)
        if identity != self._identity or self._list is None:
            self.scroll = ScrollTracker()
            self._list = self._new_list(bank, items)
            self.pointer.visible, self._hovered = False, None
            self._list_stack.controls = [self._list, self.pointer]
            self._target.content = self._list_stack
        else:
            self._list.controls = items
        self._identity = identity
        self._rows.controls = [column_titles(view, grip=not bank), self._target]

    def _new_list(self, bank: bool, items: list[ft.Control]) -> ft.ListView:
        # Flet already subtracts one when a row moves down, so new_index is its final position.
        if bank:
            return ft.ListView(controls=items, on_scroll=self._on_scroll, expand=True, spacing=0)
        return ft.ReorderableListView(
            controls=items,
            show_default_drag_handles=False,
            on_reorder=self._on_reorder,
            on_scroll=self._on_scroll,
            expand=True,
        )

    def _on_scroll(self, e: ft.OnScrollEvent) -> None:
        self.scroll.on_scroll(e)
        if self._hovered is not None:
            self._place_pointer(self._hovered)

    def _on_row_hover(self, index: int, inside: bool) -> None:
        if inside:
            self._hovered = index
            self._place_pointer(index)
        elif index == self._hovered:
            self._hovered = None
            self.pointer.visible = False
            self.pointer.update()

    def _place_pointer(self, index: int) -> None:
        """Put the pointer beside row `index`, wherever the list has scrolled to."""
        self.pointer.top = index * theme.ROW_HEIGHT - self.scroll.pixels + POINTER_TOP
        self.pointer.visible = True
        self.pointer.update()

    def _on_reorder(self, e: ft.OnReorderEvent) -> None:
        if self._cbs is not None:
            self._cbs.on_reorder(e.old_index, e.new_index)

    def _on_accept(self, e: ft.DragTargetEvent) -> None:
        payload = e.src.data
        if isinstance(payload, DragPayload) and self._view is not None and self._cbs is not None:
            gap = drop_index(e.local_position.y, len(self._view.rows), self.scroll.pixels)
            self._cbs.on_drop(payload, gap)


def pane(
    view: PaneView, cbs: PaneCallbacks, mode: RightMode = RightMode.BANK, narrow: bool = False
) -> ft.Container:
    """Draw one pane once. `mode` only matters for the right pane (Bank or a second save)."""
    return PaneShell().update(view, cbs, mode, narrow)
