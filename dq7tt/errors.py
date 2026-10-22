"""Exceptions raised by the tablet trader."""

from collections.abc import Sequence
from enum import StrEnum


class TabletTraderError(Exception):
    """Base class for every error this package raises."""


class UnsupportedLayoutError(TabletTraderError):
    """The file is not a save layout this tool understands."""


class JapaneseSaveError(UnsupportedLayoutError):
    """The file is a Japanese save, whose layout differs and is not supported."""


class CorruptSaveError(TabletTraderError):
    """The file looks like a save but its contents are damaged."""


class TabletCapError(TabletTraderError):
    """A tablet list is full."""


class DuplicateTabletError(TabletTraderError):
    """The tablet is already present; `name` names it when the raiser knows it."""

    def __init__(self, message: str, name: str | None = None) -> None:
        super().__init__(message)
        self.name = name


class UnknownTabletError(TabletTraderError):
    """The tablet is not in the catalogue."""


class ValidationError(TabletTraderError):
    """A save failed validation; `problems` lists what was wrong."""

    def __init__(self, problems: Sequence[object]) -> None:
        self.problems = list(problems)
        super().__init__("; ".join(str(p) for p in self.problems) or "validation failed")


class OutputExistsError(TabletTraderError):
    """The output location already exists."""


class UsageError(TabletTraderError):
    """The request cannot be carried out as given (missing log, bad position, missing flag)."""


class InvalidSlotError(TabletTraderError, IndexError):
    """A tablet position is outside the list."""


class InvalidClearCountError(TabletTraderError, ValueError):
    """A clear count is outside the range a record can hold."""


class UnsupportedSourceError(TabletTraderError):
    """The path is not a Dragon Quest VII save this tool can read."""


class SaveIOError(TabletTraderError):
    """A file or folder could not be read or written."""


class BankProblem(StrEnum):
    """Why a bank file or folder was refused, for callers that word it themselves."""

    EXISTS = "exists"
    MISSING = "missing"
    EMPTY = "empty"
    HIDDEN = "hidden"
    BAD_CHARACTERS = "bad characters"
    TRAILING = "trailing"
    RESERVED = "reserved"
    DAMAGED = "damaged"
    UNREADABLE = "unreadable"
    OUTSIDE = "outside"
    NOT_TABLET = "not a tablet"


class BankFileError(TabletTraderError):
    """A bank file is damaged, hand-edited or from an unknown version, or a folder name is bad.

    `reason` says which, when the raiser knows it.
    """

    def __init__(self, message: str, reason: BankProblem | None = None) -> None:
        super().__init__(message)
        self.reason = reason


class SessionError(TabletTraderError):
    """The request cannot be carried out in the current session."""
