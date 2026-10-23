"""One side of the window: a menu window with its header, chips and the tablet list."""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

import flet as ft

from dq7tt_gui import art, theme
from dq7tt_gui.viewmodels import PaneSide, PaneView, RightMode, TabletRow
from dq7tt_gui.widgets import (
    GRIP_SIZE,
    GRIP_SLOT,
    POINTER_LEFT,
    RowHover,
    bar_button,
    tablet_row,
    text,
)
from dq7tt_gui.widgets_compact import compact_row, pane_head
from dq7tt_gui.widgets_drag import GROUP, DragPayload, ScrollTracker, drop_index, payload_for
from dq7tt_gui.widgets_focus import first_focus
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
EMPTY_COMPASS = 160
EMPTY_SPACING = 16
COMPACT_COMPASS = 64
COMPACT_EMPTY_SPACING = 8
EMPTY_BUTTON_GAP = 8


@dataclass(frozen=True)
class RowStyle:
    """How a pane draws its rows.

    `narrow`: one pane at a time, so nothing to drag to. `compact`: two-line rows under a
    slim header. `touch`: a finger, not a mouse (Android): no grips, a long press reorders
    and a drag to the other pane starts with a sideways move.
    """

    height: float = theme.ROW_HEIGHT
    narrow: bool = False
    compact: bool = False
    touch: bool = False


def _grip(height: float) -> ft.ReorderableDragHandle:
    return ft.ReorderableDragHandle(
        tooltip="Drag to reorder",
        content=ft.Container(
            content=ft.Icon(ft.Icons.DRAG_INDICATOR, color=theme.GRIP, size=GRIP_SIZE),
            width=GRIP_SLOT,
            height=height,
            alignment=ft.Alignment.CENTER_LEFT,
        ),
    )


def _row(
    row: TabletRow,
    view: PaneView,
    cbs: PaneCallbacks,
    style: RowStyle,
    hover: RowHover,
    reorder: bool,
) -> ft.Container:
    """A row whose name drags to the other pane; in the narrow layout it only scrolls.

    With a mouse a grip reorders the save's rows; on a touch screen a long press does.
    On Android the D-pad's focus moves the pointer just as the mouse does; the save's
    first row takes the focus when the list appears.
    """
    drag = None if style.narrow else payload_for(row, view.side, view.rows)
    grip = _grip(style.height) if reorder and not style.touch else None
    focus = partial(hover, row.index) if style.touch else None
    first = style.touch and row.index == 0 and view.side is PaneSide.LEFT
    if style.compact:
        return compact_row(
            row,
            cbs.on_toggle,
            height=style.height,
            drag=drag,
            grip=grip,
            on_hover=hover,
            touch=style.touch,
            on_focus=focus,
            autofocus=first,
        )
    return tablet_row(
        row, cbs.on_toggle, drag, grip, hover, style.height, style.touch, focus, first
    )


def _items(
    view: PaneView, cbs: PaneCallbacks, style: RowStyle, hover: RowHover, reorder: bool
) -> list[ft.Control]:
    rows: list[ft.Control] = [_row(r, view, cbs, style, hover, reorder) for r in view.rows]
    # Keys let Flet redraw a row in place. The save's reorderable list needs them; on
    # Android the bank's rows get them too, or a tick would replace the focused row and
    # Flutter would hand the focus back to the save.
    if not reorder and not style.touch:
        return rows
    return [ft.Container(key=r.key, content=c) for r, c in zip(view.rows, rows, strict=True)]


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

    def __init__(self, row_height: float = theme.ROW_HEIGHT, touch: bool = False) -> None:
        # The shell's own row height (40 on a PC, 48 on Android); `row_height` is the one
        # the rows have now, which is 48 in the compact layouts everywhere.
        self._own_height = row_height
        self.row_height = row_height
        self.touch = touch
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
        self._target = ft.DragTarget(content=ft.Container(), group=GROUP, on_accept=self._on_accept)
        # Flet 1.0.4 ignores `expand` on a DragTarget (its Dart side has no layout wrapper),
        # which left the list under it unbounded: laid out full length, clipped, never
        # scrolling. This container is what takes the pane's remaining height.
        self._target_box = ft.Container(content=self._target, expand=True)
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

    def first_row_focus(self) -> ft.CupertinoButton | None:
        """What takes the focus on the first row (Android), if the list has a row."""
        if self._list is None or not self._list.controls:
            return None
        return first_focus(self._list.controls[0])

    def head_focus(self) -> ft.CupertinoButton | None:
        """What takes the focus on the pane's header (Android, compact layouts)."""
        if not self._column.controls:
            return None
        return first_focus(self._column.controls[0])

    def update(
        self,
        view: PaneView,
        cbs: PaneCallbacks,
        mode: RightMode,
        narrow: bool = False,
        *,
        compact: bool = False,
        active: bool = False,
        key: str | None = None,
    ) -> ft.Container:
        """Bring the pane up to date with `view` and return its (persistent) control.

        `compact` draws the slim header and two-line rows; there the pane with the focus
        (`active`) gets a gold edge, and `key` names the controller key that picks it.
        """
        self._view, self._cbs = view, cbs
        bank = view.side == PaneSide.RIGHT and mode == RightMode.BANK
        self._compass.visible = bank and not compact
        inner = self.control.content
        if isinstance(inner, ft.Container):
            edge = theme.GOLD if compact and active else theme.WINDOW_EDGE
            inner.border = ft.Border.all(theme.WINDOW_EDGE_W, edge)
        self.control.padding = ft.Padding.only(bottom=0 if compact else WINDOW_BOTTOM)
        if compact:
            parts: list[ft.Control] = [
                pane_head(
                    view,
                    mode,
                    active=active,
                    key=key,
                    on_click=cbs.on_activate,
                    focusable=self.touch,
                )
            ]
        else:
            parts = [header(view, cbs, mode, narrow)]
            chip_line = chips(view, cbs)
            if chip_line is not None:
                parts.append(chip_line)
        parts.append(self._body)
        self._column.controls = parts
        self.row_height = theme.COMPACT_ROW_HEIGHT if compact else self._own_height
        style = RowStyle(self.row_height, narrow, compact, self.touch)
        self._fill_body(view, cbs, mode, style)
        return self.control

    def _fill_body(
        self, view: PaneView, cbs: PaneCallbacks, mode: RightMode, style: RowStyle
    ) -> None:
        identity = _identity(view, mode)
        bank = view.side == PaneSide.RIGHT and mode == RightMode.BANK
        if view.empty_text is not None:
            if identity != self._identity:
                self.scroll, self._list = ScrollTracker(), None
                self._target.content = _empty_body(view)
            self._identity = identity
            self._rows.controls = [self._target_box]
            return
        items = _items(view, cbs, style, self._on_row_hover, reorder=not bank)
        if identity != self._identity or self._list is None:
            self.scroll = ScrollTracker()
            self._list = self._new_list(bank, items)
            self.pointer.visible, self._hovered = False, None
            self._list_stack.controls = [self._list, self.pointer]
            self._target.content = self._list_stack
        else:
            self._list.controls = items
        self._identity = identity
        grip = not bank and not style.touch
        titles = [] if style.compact else [column_titles(view, grip=grip)]
        self._rows.controls = [*titles, self._target_box]

    def _new_list(self, bank: bool, items: list[ft.Control]) -> ft.ListView:
        # Flet already subtracts one when a row moves down, so new_index is its final position.
        if bank:
            return ft.ListView(controls=items, on_scroll=self._on_scroll, expand=True, spacing=0)
        return ft.ReorderableListView(
            controls=items,
            # On a touch screen Flutter's own handles: a long press anywhere on a row.
            show_default_drag_handles=self.touch,
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
        middle = (self.row_height - theme.POINTER_H) / 2
        self.pointer.top = index * self.row_height - self.scroll.pixels + middle
        self.pointer.visible = True
        self.pointer.update()

    def _on_reorder(self, e: ft.OnReorderEvent) -> None:
        if self._cbs is not None:
            self._cbs.on_reorder(e.old_index, e.new_index)

    def _on_accept(self, e: ft.DragTargetEvent) -> None:
        payload = e.src.data
        if isinstance(payload, DragPayload) and self._view is not None and self._cbs is not None:
            rows = len(self._view.rows)
            gap = drop_index(e.local_position.y, rows, self.scroll.pixels, self.row_height)
            self._cbs.on_drop(payload, gap)


def pane(
    view: PaneView, cbs: PaneCallbacks, mode: RightMode = RightMode.BANK, narrow: bool = False
) -> ft.Container:
    """Draw one pane once. `mode` only matters for the right pane (Bank or a second save)."""
    return PaneShell().update(view, cbs, mode, narrow)


def empty_window(
    message: str,
    on_open: Callable[[], object],
    on_find: Callable[[], object],
    compact: bool = False,
) -> ft.Container:
    """The save's place before one is open: a faint compass, a word, Open and Find.

    The compact layout draws the compass small, to fit a pane two hundred pixels high.
    """
    compass = COMPACT_COMPASS if compact else EMPTY_COMPASS
    buttons = ft.Row(
        [bar_button("Open save", on_open), bar_button("Find saves", on_find)],
        alignment=ft.MainAxisAlignment.CENTER,
        wrap=True,
        spacing=EMPTY_BUTTON_GAP,
        run_spacing=EMPTY_BUTTON_GAP,
    )
    return menu_window(
        ft.Column(
            [
                ft.Image(src=art.COMPASS_FAINT, width=compass, height=compass),
                text(message, color=theme.MUTED, size=theme.TITLE_SIZE),
                buttons,
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=COMPACT_EMPTY_SPACING if compact else EMPTY_SPACING,
        ),
        expand=True,
    )
