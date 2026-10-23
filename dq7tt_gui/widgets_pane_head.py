"""The top of a pane: its tabs, title and buttons, the chips, and the column titles."""

from collections.abc import Callable
from dataclasses import dataclass

import flet as ft

from dq7tt.savefile import SlotRole
from dq7tt_gui import theme
from dq7tt_gui.viewmodels import PUT_INTO_AZAHAR, PaneSide, PaneView, RightMode
from dq7tt_gui.widgets import (
    BAR_BUTTON_HEIGHT,
    BUTTON_RADIUS,
    CLEARS_COLUMN_W,
    GRIP_SLOT,
    KIND_COLUMN_W,
    NAME_START,
    ROW_GAP,
    ROW_INSET,
    ROW_PADDING_R,
    bar_button,
    hover_overlay,
    text,
)
from dq7tt_gui.widgets_chips import CHIP_GAP, LOG_CHIP_MIN_W, folder_chip, log_chip
from dq7tt_gui.widgets_drag import DragPayload
from dq7tt_gui.widgets_frame import pointer, rule

# Pane buttons are touch targets too.
SMALL_BUTTON_HEIGHT = 40
HEADER_SPACING = 10
TITLES_HEIGHT = 30
PANE_LEFT = 22
PANE_RIGHT = 16
TAB_LEFT = 4
TAB_PADDING_H = 10
TAB_POINTER_GAP = 6
HEADER_TOP = 14
TABS_TOP = 10
SECTION_GAP = 12
BANK_ALL_LABEL = "Bank all tablets in this log"
PUT_LABEL = PUT_INTO_AZAHAR  # the desktop wording; panes show their own

# Log chips share their line four to a row when each would still fit "Quick save 6/24",
# two to a row otherwise. Flet's ResponsiveRow picks its layout by the page's width, so
# the page widths where four fit are worked out from the window's layout: the frame's
# margins, the gap between panes, a pane's insets and its window edges.
LOG_CHIP_COUNT = 4
FOUR_CHIPS_W = LOG_CHIP_COUNT * LOG_CHIP_MIN_W + (LOG_CHIP_COUNT - 1) * CHIP_GAP
PANE_EXTRA_W = PANE_LEFT + PANE_RIGHT + 2 * (theme.WINDOW_EDGE_W + theme.WINDOW_RING_W)
FOUR_CHIPS_NARROW = FOUR_CHIPS_W + PANE_EXTRA_W + 2 * theme.FRAME_MARGIN_NARROW
FOUR_CHIPS_WIDE = 2 * (FOUR_CHIPS_W + PANE_EXTRA_W) + 2 * theme.FRAME_MARGIN + theme.PANE_GAP
LOG_CHIP_BREAKPOINTS: dict[str, float] = {
    "pairs": 0,
    "four_tabbed": FOUR_CHIPS_NARROW,
    "pairs_side_by_side": theme.NARROW_WIDTH,
    "four_side_by_side": FOUR_CHIPS_WIDE,
}
GRID_COLUMNS = 12
LOG_CHIP_COLS: dict[str, int] = {
    "pairs": GRID_COLUMNS // 2,
    "four_tabbed": GRID_COLUMNS // LOG_CHIP_COUNT,
    "pairs_side_by_side": GRID_COLUMNS // 2,
    "four_side_by_side": GRID_COLUMNS // LOG_CHIP_COUNT,
}
MODE_LABELS: dict[RightMode, str] = {
    RightMode.BANK: "Bank",
    RightMode.SAVE: "Open a second save",
}


@dataclass
class PaneCallbacks:
    on_pick_log: Callable[[SlotRole], object]
    on_pick_folder: Callable[[str], object]
    on_toggle: Callable[[str], object]
    on_close: Callable[[], object]
    on_mode: Callable[[RightMode], object]
    on_new_folder: Callable[[], object]
    on_reorder: Callable[[int, int], object]
    on_drop: Callable[[DragPayload, int], object]
    on_bank_all: Callable[[], object]
    on_put_into_azahar: Callable[[], object]
    # The compact layout: a tap on the pane's header gives it the focus.
    on_activate: Callable[[], object] | None = None


def pane_button(label: str, on_click: Callable[[], object]) -> ft.Button:
    return bar_button(label, on_click, height=SMALL_BUTTON_HEIGHT, size=theme.BUTTON_TEXT_SIZE)


def tab_button(label: str, active: bool, on_click: Callable[[], object]) -> ft.Button:
    """A tab of a menu window: the pointer marks the one that is showing."""
    caption = text(label, color=theme.TEXT if active else theme.TAB_OFF, size=theme.TAB_SIZE)
    content: ft.Control = caption
    if active:
        content = ft.Row([pointer(), caption], spacing=TAB_POINTER_GAP, tight=True)
    return ft.Button(
        content=content,
        height=BAR_BUTTON_HEIGHT,
        on_click=lambda _e: on_click(),
        style=ft.ButtonStyle(
            bgcolor=theme.CLEAR,
            overlay_color=hover_overlay(),
            shadow_color=theme.CLEAR,
            elevation=0,
            shape=ft.RoundedRectangleBorder(radius=BUTTON_RADIUS),
            padding=ft.Padding.symmetric(horizontal=TAB_PADDING_H),
        ),
    )


def _mode_switch(mode: RightMode, on_mode: Callable[[RightMode], object]) -> list[ft.Control]:
    def tab(target: RightMode) -> ft.Button:
        return tab_button(MODE_LABELS[target], target == mode, lambda: on_mode(target))

    return [tab(RightMode.BANK), tab(RightMode.SAVE)]


def _title(view: PaneView) -> ft.Control:
    """Title and subtitle; they take the room left and shorten with "..." when it runs out."""
    return ft.Column(
        [
            text(view.title, size=theme.TITLE_SIZE),
            text(view.subtitle, color=theme.MUTED, size=theme.SMALL_SIZE),
        ],
        spacing=2,
        tight=True,
        expand=True,
    )


def _line(controls: list[ft.Control]) -> ft.Row:
    return ft.Row(controls, spacing=HEADER_SPACING, vertical_alignment=ft.CrossAxisAlignment.CENTER)


def _inset(content: ft.Control, left: int = PANE_LEFT) -> ft.Container:
    return ft.Container(
        content=content, padding=ft.Padding(left=left, top=0, right=PANE_RIGHT, bottom=0)
    )


def header(view: PaneView, cbs: PaneCallbacks, mode: RightMode, narrow: bool) -> ft.Control:
    """The pane's top lines, so the save's name keeps the full width beside Close.

    The right pane's tabs (Bank, Open a second save) sit on a line of their own above the
    title, with New folder when it shows the bank. The pane's actions go on their own line
    under the title, where they wrap if need be; in the narrow layout they live in the More
    menu instead.
    """
    right = view.side == PaneSide.RIGHT
    bank = right and mode == RightMode.BANK
    lines: list[ft.Control] = []
    if right:
        # The tabs wrap rather than push New folder out of a narrow pane.
        tabs: list[ft.Control] = [
            ft.Container(
                content=ft.Row(
                    _mode_switch(mode, cbs.on_mode),
                    spacing=HEADER_SPACING,
                    run_spacing=0,
                    wrap=True,
                ),
                expand=True,
            )
        ]
        if bank:
            tabs.append(pane_button("New folder", cbs.on_new_folder))
        lines += [
            _inset(_line(tabs), left=TAB_LEFT),
            rule(ft.Margin(left=PANE_LEFT, top=0, right=PANE_RIGHT, bottom=0)),
        ]
    if not bank:
        lines.append(_inset(_line([_title(view), pane_button("Close", cbs.on_close)])))
        actions: list[ft.Control] = []
        if not narrow and view.can_put_into_azahar:
            actions.append(pane_button(view.put_label, cbs.on_put_into_azahar))
        if not narrow and view.can_bank_all:
            actions.append(pane_button(BANK_ALL_LABEL, cbs.on_bank_all))
        if actions:
            lines.append(
                _inset(
                    ft.Row(actions, spacing=HEADER_SPACING, run_spacing=HEADER_SPACING, wrap=True)
                )
            )
    return ft.Container(
        content=ft.Column(lines, spacing=HEADER_SPACING, tight=True),
        padding=ft.Padding(left=0, top=TABS_TOP if right else HEADER_TOP, right=0, bottom=0),
    )


def chips(view: PaneView, cbs: PaneCallbacks) -> ft.Control | None:
    """Log chips, four or two to a line; then folder chips, as many as fit, wrapping."""
    lines: list[ft.Control] = []
    if view.log_chips:
        log_chips = [log_chip(c, cbs.on_pick_log) for c in view.log_chips]
        for chip in log_chips:
            chip.col = LOG_CHIP_COLS
        lines.append(
            ft.ResponsiveRow(
                log_chips,
                columns=GRID_COLUMNS,
                breakpoints=LOG_CHIP_BREAKPOINTS,
                spacing=CHIP_GAP,
                run_spacing=CHIP_GAP,
            )
        )
    if view.folder_chips:
        lines.append(
            ft.Row(
                [folder_chip(c, cbs.on_pick_folder) for c in view.folder_chips],
                spacing=CHIP_GAP,
                run_spacing=CHIP_GAP,
                wrap=True,
            )
        )
    if not lines:
        return None
    return ft.Container(
        content=ft.Column(lines, spacing=CHIP_GAP, tight=True),
        padding=ft.Padding(left=PANE_LEFT, top=SECTION_GAP, right=PANE_RIGHT, bottom=0),
    )


def column_titles(view: PaneView, grip: bool) -> ft.Container:
    """Titles over the columns, inset past the pointer, grip, check box and stone."""

    def title(label: str, width: int, right: bool = False) -> ft.Control:
        align = ft.Alignment.CENTER_RIGHT if right else ft.Alignment.CENTER_LEFT
        return ft.Container(
            content=text(label, color=theme.TITLES, size=theme.DETAIL_SIZE),
            width=width,
            alignment=align,
        )

    return ft.Container(
        content=ft.Row(
            [
                text("Tablet", color=theme.TITLES, size=theme.DETAIL_SIZE),
                text(view.count_text, color=theme.TITLES, size=theme.DETAIL_SIZE, expand=True),
                title("Kind", KIND_COLUMN_W),
                title("Clears", CLEARS_COLUMN_W, right=True),
            ],
            spacing=ROW_GAP,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        height=TITLES_HEIGHT,
        margin=ft.Margin.only(top=SECTION_GAP),
        padding=ft.Padding(
            left=ROW_INSET + (GRIP_SLOT if grip else 0) + NAME_START,
            top=0,
            right=ROW_PADDING_R,
            bottom=0,
        ),
        border=ft.Border(bottom=ft.BorderSide(1, theme.RULE)),
    )
