"""The handheld's buttons in the main window, and Android's own Back.

B goes back one step: it closes the top dialog, else clears the ticks, else does nothing.
L and R pick the save or the bank (the pane with the gold edge, or the tab), Start saves
as the Save button does, and Y ticks every tablet in the active pane. The D-pad and A are
Flutter's own: they move the focus and press what has it.

Android turns a B press that nobody claims into Back, which would leave the app; Flet
cannot claim a key. So the root view refuses to pop on its own and asks the window: a
Back just after B is that same B and is refused; a real Back leaves at once, or asks
first while something is not written yet.
"""

import logging

import flet as ft

from dq7tt_gui.controller import BackGuard, KeyNames, Pad, pad_action
from dq7tt_gui.layout import Layout
from dq7tt_gui.model import AppModel
from dq7tt_gui.model_text import DISCARD_TITLE
from dq7tt_gui.viewmodels import Confirm, Notice, Outcome, PaneSide
from dq7tt_gui.widgets_pane import PaneShell
from dq7tt_gui.window_dialogs import TAB_SAVE
from dq7tt_gui.window_narrow import SECOND_TAB

log = logging.getLogger(__name__)

LEAVE_TEXT = "You have changes that are not written yet. Leave anyway and lose them?"
LEAVE_OK = "Leave"
TAB_OF: dict[PaneSide, int] = {PaneSide.LEFT: TAB_SAVE, PaneSide.RIGHT: SECOND_TAB}


class ControllerFlows:
    """Mixed into `Window`; relies on its page, model, panes, dialogs and commands."""

    page: ft.Page
    model: AppModel
    layout: Layout
    active_side: PaneSide
    tab_index: int
    touch: bool
    narrow: bool
    slim: bool
    pending_confirm: Confirm | None
    _dialogs: list[ft.AlertDialog]
    _shells: dict[PaneSide, PaneShell]
    _tabs_control: ft.Tabs
    _back_guard: BackGuard
    _key_names: KeyNames
    _leaving: Confirm | None

    def handle(self, outcome: Outcome) -> None:
        raise NotImplementedError

    def refresh(self) -> None:
        raise NotImplementedError

    def show_confirm(self, confirm: Confirm) -> None:
        raise NotImplementedError

    def _waiting(self, confirm: Confirm) -> bool:
        raise NotImplementedError

    def cancel_top(self) -> None:
        raise NotImplementedError

    def show_tab(self, index: int) -> None:
        raise NotImplementedError

    def write_all(self) -> None:
        raise NotImplementedError

    def _label_tabs(self) -> None:
        raise NotImplementedError

    def pad_key(self, key: str) -> bool:
        """Act on a controller button; False when `key` is not one."""
        pad = pad_action(key)
        if pad is None:
            if not self._dialogs:  # never what is typed into a prompt
                self._key_names.note(key)
            return False
        if pad is Pad.BACK:
            self._back_guard.b_pressed()
            self.go_back()
        elif self._dialogs:
            pass  # the other buttons wait until the dialog is answered
        elif pad is Pad.SWITCH_LEFT:
            self.switch_to(PaneSide.LEFT)
        elif pad is Pad.SWITCH_RIGHT:
            self.switch_to(PaneSide.RIGHT)
        elif pad is Pad.SAVE:
            if self.model.write_sides():
                self.write_all()  # the same as the Save button, so it still asks first
        elif pad is Pad.SELECT_ALL:
            self.handle(self.model.select_all(self.active_side))
        return True

    def go_back(self) -> None:
        """Close the top dialog (as its Cancel does), else clear the ticks, else nothing."""
        if self._dialogs:
            self.cancel_top()
            return
        if self.model.action_bar().selected_count:
            self.handle(self.model.clear_selection())

    def switch_to(self, side: PaneSide) -> None:
        """Make `side` the active pane (or show its tab) and put the focus on its first row."""
        if self.layout is Layout.COMPACT:
            self.active_side = side
            self.refresh()
        elif self.narrow and self.slim:
            self.show_tab(TAB_OF[side])
        elif self.narrow:
            self.tab_index = TAB_OF[side]
            self.active_side = side
            self._tabs_control.selected_index = self.tab_index
            self._label_tabs()
            self.refresh()
        else:
            self.active_side = side
        # The first row, or with none the pane's header, so A cannot tick a row in the
        # pane that was active before.
        shell = self._shells[side]
        target = shell.first_row_focus() or shell.head_focus()
        if target is not None:
            self.page.run_task(target.focus)

    def setup_key(self, e: ft.KeyboardEvent) -> None:
        """Keys on Android's setup screens: only B matters, so its Back is refused."""
        if pad_action(e.key) is Pad.BACK:
            self._back_guard.b_pressed()

    # Android's own Back

    def hold_back(self) -> None:
        """Have Android's Back ask the window before it leaves the app (Android only)."""
        if not self.touch or not self.page.views:
            return  # also called for the setup screens, before the window is shown
        view = self.page.views[0]
        view.can_pop = False
        view.on_confirm_pop = self._on_back

    def _on_back(self, _e: object) -> None:
        view = self.page.views[0]
        if self._back_guard.is_echo():
            log.info("Back: kept, it came from B")
            self.page.run_task(view.confirm_pop, False)
            return
        if not self.model.has_unwritten():
            log.info("Back: leaving, nothing unwritten")
            self.page.run_task(view.confirm_pop, True)
            return
        log.info("Back: asking first, changes are not written")

        if self._leaving is not None and self._waiting(self._leaving):
            return  # already asking; the answer goes to this newest Back

        def leave() -> list[Notice]:
            self._leaving = None
            self.page.run_task(view.confirm_pop, True)
            return []

        # Left unanswered, Flet gives up on the Back by itself; Cancel needs nothing more.
        self._leaving = Confirm(DISCARD_TITLE, LEAVE_TEXT, LEAVE_OK, on_ok=leave)
        self.show_confirm(self._leaving)
