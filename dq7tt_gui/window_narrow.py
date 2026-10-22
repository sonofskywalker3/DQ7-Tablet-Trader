"""The narrow layout, below NARROW_WIDTH and meant for touch screens.

Save and Bank tabs, a top bar with Open, Find and Undo, and a bottom bar with Send, More
and Write.
"""

import flet as ft

from dq7tt_gui import theme
from dq7tt_gui.model import AppModel
from dq7tt_gui.viewmodels import PaneSide
from dq7tt_gui.widgets import bar_button, text, write_button
from dq7tt_gui.widgets_frame import menu_window, pointer
from dq7tt_gui.window_open import OpenFlows

TAB_LABELS = ("Save", "Bank")
SECOND_TAB = 1
TAB_POINTER_GAP = 6
BAR_PADDING = 6
BAR_SPACING = 8


def tab_label(name: str, active: bool) -> ft.Control:
    """A narrow-layout tab's name, with the pointer when it is the tab showing."""
    caption = text(name, color=theme.TEXT if active else theme.TAB_OFF, size=theme.TAB_SIZE)
    if not active:
        return caption
    return ft.Row([pointer(), caption], spacing=TAB_POINTER_GAP, tight=True)


class NarrowLayout(OpenFlows):
    """Mixed into `Window`; relies on its model, panes and commands."""

    model: AppModel
    tab_index: int
    _mounted: bool

    def _pane(self, side: PaneSide) -> ft.Control:
        raise NotImplementedError

    def undo(self) -> None:
        raise NotImplementedError

    def write_all(self) -> None:
        raise NotImplementedError

    def _build_tabs(self) -> None:
        """One set of tab controls for the whole session, so the lists keep their scroll."""
        self._tab_view = ft.TabBarView(controls=[], expand=True)
        self._tab_bar = ft.TabBar(
            tabs=[ft.Tab(label=name) for name in TAB_LABELS],
            indicator_color=theme.GOLD,
            divider_color=theme.CLEAR,
            overlay_color=theme.HOVER,
        )
        self._tabs_control = ft.Tabs(
            content=ft.Column(
                [menu_window(self._tab_bar), self._tab_view],
                expand=True,
                spacing=theme.FRAME_GAP_NARROW,
            ),
            length=len(TAB_LABELS),
            selected_index=self.tab_index,
            on_change=self._on_tab,
            expand=True,
        )

    def _tabs(self) -> ft.Control:
        """The Save/Bank tabs; one set of controls lives for the whole session."""
        self._tab_view.controls = [self._pane(PaneSide.LEFT), self._pane(PaneSide.RIGHT)]
        self._label_tabs()
        self._tabs_control.selected_index = self.tab_index
        return self._tabs_control

    def _label_tabs(self) -> None:
        """Name the tabs, the pointer by the one showing; the second names what it shows."""
        names = (TAB_LABELS[0], self.model.right_tab_label())
        for index, (tab, name) in enumerate(zip(self._tab_bar.tabs, names, strict=True)):
            tab.label = tab_label(name, active=index == self.tab_index)

    def _on_tab(self, e: ft.Event[ft.Tabs]) -> None:
        self.tab_index = int(e.control.selected_index)
        self._label_tabs()
        if self._mounted:
            self._tab_bar.update()

    def _narrow_top(self, can_undo: bool) -> ft.Control:
        return menu_window(
            ft.Row(
                [
                    bar_button("Open save", self.open_dialog),
                    bar_button("Find saves", self.find_saves),
                    bar_button("Undo", self.undo, disabled=not can_undo, icon=ft.Icons.UNDO),
                ],
                wrap=True,
                spacing=BAR_SPACING,
                run_spacing=BAR_SPACING,
            ),
            padding=BAR_PADDING,
        )

    def _narrow_bar(self) -> ft.Control:
        """Send and More on the left (wrapping if need be), Write kept on the right.

        The spacer cannot sit inside a wrapping row (Flutter refuses an expanding child in a
        Wrap and draws a grey error box), so the left buttons wrap in their own row.
        """
        bar = self.model.action_bar()
        tb = self.model.toolbar()
        left: list[ft.Control] = []
        if bar.selected_count:
            left.append(bar_button(f"Send {bar.selected_count} to...", self.send_to))
        left.append(bar_button("More", self.more))
        return menu_window(
            ft.Row(
                [
                    ft.Container(
                        content=ft.Row(
                            left, spacing=BAR_SPACING, wrap=True, run_spacing=BAR_SPACING
                        ),
                        expand=True,
                    ),
                    write_button(tb.write_label, self.write_all, tb.can_write),
                ],
                spacing=BAR_SPACING,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=BAR_PADDING,
        )
