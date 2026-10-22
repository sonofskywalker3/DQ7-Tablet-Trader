"""Dialog-driven parts of the main window: the dialog stack, questions, choosers and notices."""

import logging
from collections.abc import Callable, Sequence
from functools import partial

import flet as ft

from dq7tt_gui.dialogs import choice_dialog, confirm_dialog, destination_dialog, snack, text_prompt
from dq7tt_gui.model import AppModel
from dq7tt_gui.viewmodels import Confirm, Destination, Notice, NoticeKind, Outcome, PaneSide
from dq7tt_gui.widgets_pane import BANK_ALL_LABEL, PUT_LABEL

log = logging.getLogger(__name__)

TAB_SAVE = 0


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
    _close_question: Confirm | None

    def handle(self, outcome: Outcome) -> None:
        raise NotImplementedError

    def destroy_window(self) -> None:
        raise NotImplementedError

    # The stack of the app's own dialogs

    def _present(self, build: DialogBuilder) -> ft.AlertDialog:
        """Build a dialog that knows how to close itself, and show it."""
        ref: list[ft.AlertDialog] = []
        dialog = build(lambda: self._close_dialog(ref[0]))
        ref.append(dialog)
        self._dialogs.append(dialog)
        self.page.show_dialog(dialog)
        return dialog

    def _close_dialog(self, dialog: ft.AlertDialog) -> bool:
        """Close this very dialog (never a snack bar). False if it was already closed."""
        if dialog not in self._dialogs:
            return False
        self._dialogs.remove(dialog)
        dialog.open = False
        self.page.update()
        return True

    # Choosers

    def send_to(self) -> None:
        self.pick_destination(move=False)

    def more(self) -> None:
        bar = self.model.action_bar()
        tb = self.model.toolbar()
        options: list[tuple[str, Callable[[], object]]] = []
        if bar.selected_count:
            if bar.quick_copy_label:
                options.append((bar.quick_copy_label, self.model.quick_copy))
            if bar.can_move:
                options.append(("Move to...", lambda: self.pick_destination(move=True)))
            if bar.can_reset:
                options.append(("Reset clears", self.model.reset_selected))
            options.append(("Remove", self.model.remove_selected))
        side = PaneSide.LEFT if self.tab_index == TAB_SAVE else PaneSide.RIGHT
        view = self.model.left() if side is PaneSide.LEFT else self.model.right()
        if view.can_bank_all:
            options.append((BANK_ALL_LABEL, partial(self.model.import_all_to_bank, side)))
        if view.can_put_into_azahar:
            options.append((PUT_LABEL, partial(self.model.put_into_azahar, side)))
        if tb.redo_label is not None:
            options.append(("Redo", self.model.redo))
        self._choose("More", options, "Nothing else to do right now.")

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
            return choice_dialog(title, shown, close, empty)

        self._present(build)

    def pick_destination(self, move: bool) -> None:
        def build(close: Callable[[], bool]) -> ft.AlertDialog:
            def pick(dest: Destination) -> None:
                if close():
                    run = self.model.move_selected if move else self.model.copy_selected
                    self.handle(run(dest))

            title = "Move to..." if move else "Copy to..."
            dests = self.model.destinations(move=move)
            return destination_dialog(dests, pick, close, title)

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
