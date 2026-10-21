"""Exceptions raised by the tablet trader."""

from collections.abc import Sequence


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
    """The tablet is already present."""


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
