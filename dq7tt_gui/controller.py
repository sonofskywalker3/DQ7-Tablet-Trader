"""The handheld's controller: which buttons do what. No Flet in here.

On Android the AYN Thor's built-in controller arrives as key events. The D-pad and A are
left to Flutter (they move the focus and press the focused control); the other buttons
come to the window as Flutter key labels and are looked up here.
"""

import logging
import time
from collections.abc import Callable
from enum import StrEnum

log = logging.getLogger(__name__)


class Pad(StrEnum):
    BACK = "back"
    SWITCH_LEFT = "switch_left"
    SWITCH_RIGHT = "switch_right"
    SAVE = "save"
    SELECT_ALL = "select_all"


# Flutter's names for the controller's buttons (`LogicalKeyboardKey.keyLabel`). Seen in the
# emulator; still to be checked on the Thor itself, which is why every other key's label
# is logged once at debug level (see `KeyNames`).
PAD_KEYS: tuple[tuple[str, Pad], ...] = (
    ("Game Button B", Pad.BACK),
    ("Game Button Left 1", Pad.SWITCH_LEFT),
    ("Game Button Right 1", Pad.SWITCH_RIGHT),
    ("Game Button Start", Pad.SAVE),
    ("Game Button Y", Pad.SELECT_ALL),
)
_BY_LABEL: dict[str, Pad] = {label.casefold(): pad for label, pad in PAD_KEYS}


def pad_action(key: str) -> Pad | None:
    """What a controller button does, from its key label (any case); None for other keys."""
    return _BY_LABEL.get(key.casefold())


class KeyNames:
    """Logs each key label that is not a controller button, once, at debug level.

    That is how a new handheld's button names are found (the app writes these lines only
    on Android). The window never passes keys typed into a dialog.
    """

    def __init__(self) -> None:
        self._seen: set[str] = set()

    def note(self, key: str) -> None:
        if key not in self._seen:
            self._seen.add(key)
            log.debug("key not mapped: %r", key)


# How soon after B a "go back" from Android counts as that same B press, not a real Back.
B_ECHO_S = 1.5


class BackGuard:
    """Tells Android's Back that comes from B (which the app has already handled) apart
    from a real Back gesture or button.

    Android turns a B press nobody claims into Back. Flet cannot claim it, so the window
    notes each B and refuses the Back that follows it.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._b_at: float | None = None

    def b_pressed(self) -> None:
        self._b_at = self._clock()

    def is_echo(self) -> bool:
        """True (once) when a Back comes just after B."""
        if self._b_at is None:
            return False
        echo = self._clock() - self._b_at <= B_ECHO_S
        self._b_at = None
        return echo
