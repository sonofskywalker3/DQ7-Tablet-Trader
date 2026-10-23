"""Dialog-driven parts of the main window: the dialog stack, questions, choosers and notices."""

import logging
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path

import flet as ft

from dq7tt_gui import theme
from dq7tt_gui.dialogs import (
    CHOICE_HEIGHT,
    LIST_MAX_HEIGHT,
    choice_dialog,
    confirm_dialog,
    destination_dialog,
    snack,
    text_prompt,
)
from dq7tt_gui.model import AppModel
from dq7tt_gui.viewmodels import Confirm, Destination, Notice, NoticeKind, Outcome, PaneSide
from dq7tt_gui.widgets_pane import BANK_ALL_LABEL

log = logging.getLogger(__name__)

TAB_SAVE = 0
MORE = "More"
NOTHING_ELSE = "Nothing else to do right now."
COPY_ANY = "Copy to..."
CLOSE_SAVE = "Close this save"
# The bank folder shows in the compact picker, so the quick copy there just says "bank".
BANK_COPY_PREFIX = "Copy to bank folder "
BANK_COPY = "Copy to bank"


def short_copy(label: str) -> str:
    """The quick copy's label, with "bank folder X" cut to "bank"."""
    return BANK_COPY if label.startswith(BANK_COPY_PREFIX) else label


# What a dialog needs around its list: title, actions, Flutter's margin round the dialog
# and the status bar. The list gets the rest of the screen's height, and at least two lines.
DIALOG_CHROME = 230
MIN_LIST_HEIGHT = 2 * CHOICE_HEIGHT


def notices_of(outcome: Outcome) -> list[Notice]:
    return outcome if isinstance(outcome, list) else []


# Given a way to close its own dialog (True only the first time), returns the dialog to show.
type DialogBuilder = Callable[[Callable[[], bool]], ft.AlertDialog]


class DialogFlows:
    """Mixed into `Window`; relies on its page, model, `handle` and `destroy_window`."""

    page: ft.Page
    model: AppModel
    pending_confirm: Confirm | None
    narrow: bool
    tab_index: int
    _queue: list[Confirm]
    _dialogs: list[ft.AlertDialog]
    _cancels: dict[int, Callable[[object], object]]
    _close_question: Confirm | None

    def handle(self, outcome: Outcome) -> None:
        raise NotImplementedError

    def open_dialog(self, side: PaneSide = PaneSide.LEFT) -> None:
        raise NotImplementedError

    def find_saves(self, roots: Sequence[Path] | None = None) -> None:
        raise NotImplementedError

    def destroy_window(self) -> None:
        raise NotImplementedError

    def list_height(self) -> float:
        """How tall a dialog's list of choices may be before it scrolls, on this screen."""
        screen = self.page.height or theme.WINDOW_H
        return max(MIN_LIST_HEIGHT, min(LIST_MAX_HEIGHT, screen - DIALOG_CHROME))

    # The stack of the app's own dialogs

    def _present(self, build: DialogBuilder) -> ft.AlertDialog:
        """Build a dialog that knows how to close itself, and show it."""
        ref: list[ft.AlertDialog] = []
        dialog = build(lambda: self._close_dialog(ref[0]))
        ref.append(dialog)
        self._dialogs.append(dialog)
        # Kept before showing it: the page swaps `on_dismiss` for its own async wrapper,
        # which only acts once Flutter reports the dialog gone.
        if dialog.on_dismiss is not None:
            self._cancels[id(dialog)] = dialog.on_dismiss
        self.page.show_dialog(dialog)
        return dialog

    def cancel_top(self) -> None:
        """Close the top dialog as its Cancel would (the controller's B)."""
        if not self._dialogs:
            return
        cancel = self._cancels.get(id(self._dialogs[-1]))
        if cancel is not None:
            cancel(None)

    def cancel_dialogs(self) -> None:
        """Close every open dialog, top first, as its Cancel would (never its OK); one
        with no Cancel is simply closed."""
        for dialog in reversed(list(self._dialogs)):
            cancel = self._cancels.get(id(dialog))
            if cancel is not None:
                cancel(None)
            self._close_dialog(dialog)
        for dialog in list(self._dialogs):  # any a Cancel opened in turn
            self._close_dialog(dialog)

    def _close_dialog(self, dialog: ft.AlertDialog) -> bool:
        """Close this very dialog (never a snack bar). False if it was already closed."""
        if dialog not in self._dialogs:
            return False
        self._dialogs.remove(dialog)
        self._cancels.pop(id(dialog), None)
        dialog.open = False
        self.page.update()
        return True

    # Choosers

    def send_to(self) -> None:
        self.pick_destination(move=False)

    def more(self) -> None:
        """The tabbed layout's More: what the bottom bar has no room for."""
        side = PaneSide.LEFT if self.tab_index == TAB_SAVE else PaneSide.RIGHT
        self._choose(MORE, self.more_options(side, strip_actions=True), NOTHING_ELSE)

    def more_options(
        self, side: PaneSide, *, strip_actions: bool, slim: bool = False
    ) -> list[tuple[str, Callable[[], object]]]:
        """Every More menu's choices, for the pane `side`, in one order.

        `strip_actions`: the quick copy, Move and Remove, when the bottom strip does not
        show them itself. `slim` (the compact layouts): also Copy to..., and Open, Find and
        Close, which have no other place there; the quick copy says just "bank".
        """
        bar = self.model.action_bar()
        tb = self.model.toolbar()
        options: list[tuple[str, Callable[[], object]]] = []
        if bar.selected_count:
            if strip_actions and bar.quick_copy_label:
                label = short_copy(bar.quick_copy_label) if slim else bar.quick_copy_label
                options.append((label, self.model.quick_copy))
            if slim:
                options.append((COPY_ANY, self.send_to))
            if strip_actions and bar.can_move:
                options.append(("Move to...", partial(self.pick_destination, move=True)))
            if bar.can_reset:
                options.append(("Reset clears", self.model.reset_selected))
            if strip_actions:
                options.append(("Remove", self.model.remove_selected))
        view = self.model.left() if side is PaneSide.LEFT else self.model.right()
        if view.can_bank_all:
            options.append((BANK_ALL_LABEL, partial(self.model.import_all_to_bank, side)))
        if view.can_put_into_azahar:
            options.append((view.put_label, partial(self.model.put_into_azahar, side)))
        if tb.redo_label is not None:
            options.append(("Redo", self.model.redo))
        if slim:
            options += [("Open save", self.open_dialog), ("Find saves", self.find_saves)]
            if self.model.has_save(PaneSide.LEFT):
                options.append((CLOSE_SAVE, self.model.close_left))
        return options

    def _choose(
        self,
        title: str,
        options: Sequence[tuple[str, Callable[[], object]]],
        empty: str,
    ) -> None:
        def build(close: Callable[[], bool]) -> ft.AlertDialog:
            def picked(run: Callable[[], object]) -> Callable[[], None]:
                def act() -> None:
                    if close():
                        result = run()
                        if isinstance(result, list | Confirm):
                            self.handle(result)

                return act

            shown = [(label, picked(run)) for label, run in options]
            return choice_dialog(title, shown, close, empty, max_height=self.list_height())

        self._present(build)

    def pick_destination(self, move: bool) -> None:
        def build(close: Callable[[], bool]) -> ft.AlertDialog:
            def pick(dest: Destination) -> None:
                if close():
                    run = self.model.move_selected if move else self.model.copy_selected
                    self.handle(run(dest))

            title = "Move to..." if move else "Copy to..."
            dests = self.model.destinations(move=move)
            return destination_dialog(dests, pick, close, title, self.list_height())

        self._present(build)

    def new_folder(self) -> None:
        def build(close: Callable[[], bool]) -> ft.AlertDialog:
            def ok(name: str) -> str | None:
                result = self.model.new_folder(name)
                refused = [n.text for n in notices_of(result) if n.kind is NoticeKind.ERROR]
                if refused:
                    return " ".join(refused)
                if close():
                    self.handle(result)
                return None

            return text_prompt(
                "New bank folder", "Folder name", "Create", ok, close, self.page.update
            )

        self._present(build)

    # Notices and questions

    def show_notices(self, notices: Sequence[Notice]) -> None:
        for notice in notices:
            if notice.kind is NoticeKind.ERROR:
                log.info("shown to user: %s", notice.text)
            self.page.show_dialog(snack(notice))

    def show_confirm(self, confirm: Confirm) -> None:
        """Ask now, or after the question already on screen has been answered."""
        if self.pending_confirm is not None:
            self._queue.append(confirm)
            return
        self.pending_confirm = confirm

        def build(close: Callable[[], bool]) -> ft.AlertDialog:
            def accept() -> None:
                if close():
                    self._accept(confirm)

            def decline() -> None:
                if close():
                    self._decline(confirm)

            return confirm_dialog(confirm, accept, decline)

        self._present(build)

    def _waiting(self, confirm: Confirm) -> bool:
        """Whether `confirm` is on screen or waiting its turn."""
        return self.pending_confirm is confirm or any(c is confirm for c in self._queue)

    def _finish(self, confirm: Confirm) -> None:
        self.pending_confirm = None
        if confirm is self._close_question:
            self._close_question = None

    def _accept(self, confirm: Confirm) -> None:
        self._finish(confirm)
        if confirm.on_ok is not None:
            self.handle(confirm.on_ok())
        self._next_confirm()

    def _decline(self, confirm: Confirm) -> None:
        self._finish(confirm)
        self.show_notices(confirm.notices)
        self._next_confirm()

    def _next_confirm(self) -> None:
        while self._queue and self.pending_confirm is None:
            nxt = self._queue.pop(0)
            if nxt is self._close_question and not self.model.has_unwritten():
                self._close_question = None
                self.destroy_window()
                continue
            self.show_confirm(nxt)
