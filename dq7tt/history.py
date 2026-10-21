"""A small undo and redo stack over immutable states."""

from collections.abc import Callable

from dq7tt.errors import SessionError

DEFAULT_HISTORY_LIMIT = 200
MIN_HISTORY_LIMIT = 1


class History[T]:
    """Undo and redo over states that are never mutated in place.

    `limit` is the number of undoable steps kept, not counting the current state.
    """

    def __init__(self, initial: T, limit: int = DEFAULT_HISTORY_LIMIT) -> None:
        if limit < MIN_HISTORY_LIMIT:
            raise SessionError(f"History limit must be at least {MIN_HISTORY_LIMIT}.")
        self._limit = limit
        self._states: list[T] = [initial]
        # _labels[i] names the step that produced _states[i]; the first has none.
        self._labels: list[str | None] = [None]
        self._index = 0

    @property
    def current(self) -> T:
        return self._states[self._index]

    @property
    def can_undo(self) -> bool:
        return self._index > 0

    @property
    def can_redo(self) -> bool:
        return self._index < len(self._states) - 1

    @property
    def undo_label(self) -> str | None:
        return self._labels[self._index] if self.can_undo else None

    @property
    def redo_label(self) -> str | None:
        return self._labels[self._index + 1] if self.can_redo else None

    def push(self, state: T, label: str) -> None:
        del self._states[self._index + 1 :]
        del self._labels[self._index + 1 :]
        self._states.append(state)
        self._labels.append(label)
        self._index += 1
        excess = self._index - self._limit
        if excess > 0:
            del self._states[:excess]
            del self._labels[:excess]
            self._labels[0] = None
            self._index -= excess

    def undo(self) -> T:
        if not self.can_undo:
            raise SessionError("Nothing to undo.")
        self._index -= 1
        return self.current

    def redo(self) -> T:
        if not self.can_redo:
            raise SessionError("Nothing to redo.")
        self._index += 1
        return self.current

    def rewrite(self, change: Callable[[T], T]) -> None:
        """Apply `change` to every kept state, then drop steps that no longer change anything.

        Used when something outside the history (a closed or reloaded save) must vanish from
        every state, so undo never walks through steps that would now do nothing.
        """
        states = [change(s) for s in self._states]
        kept_states = [states[0]]
        kept_labels = [self._labels[0]]
        index = 0
        for i in range(1, len(states)):
            if states[i] == kept_states[-1]:
                continue
            kept_states.append(states[i])
            kept_labels.append(self._labels[i])
            if i <= self._index:
                index = len(kept_states) - 1
        self._states = kept_states
        self._labels = kept_labels
        self._index = index
