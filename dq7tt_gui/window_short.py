"""Tabs on a short screen, such as the AYN Thor's bottom screen.

One pane at a time, as in the tabbed layout, but with the compact layout's slim strips
and slim panes: the Save and Bank tabs, Undo and Save along the top; the selection's Send
and More along the bottom. A tap on the pane's header picks the log or the bank folder.
"""

from collections.abc import Callable
from functools import partial

import flet as ft

from dq7tt_gui import theme
from dq7tt_gui.viewmodels import PaneSide
from dq7tt_gui.widgets import text
from dq7tt_gui.widgets_frame import pointer
from dq7tt_gui.widgets_pane import PaneShell
from dq7tt_gui.widgets_strip import (
    CHIP,
    CHIP_ON,
    GOLD,
    PLAIN,
    caption,
    group,
    strip,
    strip_button,
)
from dq7tt_gui.window_compact import (
    COUNT_GAP,
    MORE,
    NOTHING_ELSE,
    SELECTED_FORMAT,
    CompactLayout,
)
from dq7tt_gui.window_dialogs import TAB_SAVE

SEND = "Send..."
SAVE_TAB = "Save"
LOGS_MENU = "Adventure logs"


class ShortTabsLayout(CompactLayout):
    """Mixed into `Window`; relies on its model, panes and commands."""

    tab_index: int
    narrow: bool
    _top: ft.Container
    _bottom: ft.Container
    _single: ft.Container
    _shells: dict[PaneSide, PaneShell]

    def refresh(self) -> None:
        raise NotImplementedError

    def _pane(self, side: PaneSide) -> ft.Control:
        raise NotImplementedError

    def _show_layout(self, layout: ft.Control) -> None:
        raise NotImplementedError

    # A tap on a pane's header: the focus (side by side), or its logs or folders (tabs)

    def head_tapped(self, side: PaneSide) -> None:
        if self.narrow:
            self.pane_menu(side)
            return
        if side is self.active_side:
            return  # a redraw would only take the focus off this header (A on it)
        self.active_side = side
        self.refresh()

    def pane_menu(self, side: PaneSide) -> None:
        """The save's logs to choose from, or the bank's folders."""
        if side is PaneSide.RIGHT:
            self.right_menu()
            return
        options: list[tuple[str, Callable[[], object]]] = [
            (f"{c.label} ({c.detail})", partial(self._pick_log, PaneSide.LEFT, c.role))
            for c in self.model.left().log_chips
        ]
        self._choose(LOGS_MENU, options, NOTHING_ELSE)

    # Tabs on a short screen (the Thor's bottom screen): slim strips, one slim pane

    def _fill_short_tabs(self) -> None:
        side = PaneSide.LEFT if self.tab_index == TAB_SAVE else PaneSide.RIGHT
        self.active_side = side
        self._single.content = self._pane(side)
        self._show_layout(self._single)
        self._top.content = self._short_top()
        self._bottom.content = self._short_bottom()

    def show_tab(self, index: int) -> None:
        """Show the save (0) or the bank (1); the pane shown afresh starts at the top."""
        if index == self.tab_index:
            return
        self.tab_index = index
        side = PaneSide.LEFT if index == TAB_SAVE else PaneSide.RIGHT
        self._shells[side].scroll.pixels = 0.0
        self.refresh()

    def _short_top(self) -> ft.Control:
        names = (SAVE_TAB, self.model.right_tab_label())
        tabs: list[ft.Control] = []
        for index, name in enumerate(names):
            look = CHIP_ON if index == self.tab_index else CHIP
            tabs.append(
                strip_button(
                    caption(name, look),
                    partial(self.show_tab, index),
                    look,
                    data=f"tab:{index}",
                    focusable=self.touch,
                )
            )
        return strip(
            ft.Row(
                [
                    group(tabs),
                    group([self._undo_button(False), self._save_button(False)], end=True),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

    def _short_bottom(self) -> ft.Control:
        bar = self.model.action_bar()
        lead: list[ft.Control] = []
        buttons: list[ft.Control] = []
        if bar.selected_count:
            count = SELECTED_FORMAT.format(count=bar.selected_count)
            lead = [pointer(), text(count, size=theme.CLEARS_SIZE)]
            buttons.append(self._bar_button(SEND, self.send_to, GOLD, "send"))
        buttons.append(self._bar_button(MORE, partial(self.compact_more, full=True), PLAIN, "more"))
        return strip(
            ft.Row(
                [
                    ft.Row(lead, spacing=COUNT_GAP, tight=True),
                    group(buttons, end=True),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )
