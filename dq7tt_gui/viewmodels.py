"""What the window shows, as plain frozen values the model builds and the view draws."""

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal

from dq7tt.savefile import SlotRole
from dq7tt.tablets import TabletKind

# The pane action that puts a written Azahar save back in (the desktop wording).
PUT_INTO_AZAHAR = "Put into Azahar"


class NoticeKind(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass(frozen=True)
class Notice:
    kind: NoticeKind
    text: str


class PaneSide(StrEnum):
    LEFT = "left"
    RIGHT = "right"


class RightMode(StrEnum):
    BANK = "bank"
    SAVE = "save"


@dataclass(frozen=True)
class TabletRow:
    index: int
    name: str
    kind: TabletKind
    clears: int
    selected: bool
    key: str


@dataclass(frozen=True)
class LogChip:
    role: SlotRole
    label: str
    detail: str
    active: bool
    muted: bool
    fill: str = ""  # how many tablets the log holds, like "23/24"


@dataclass(frozen=True)
class FolderChip:
    name: str
    label: str
    count: int
    active: bool


@dataclass(frozen=True)
class PaneView:
    side: PaneSide
    title: str
    subtitle: str
    empty_text: str | None
    log_chips: tuple[LogChip, ...]
    folder_chips: tuple[FolderChip, ...]
    rows: tuple[TabletRow, ...]
    count_text: str
    # Pane actions: bank every tablet of the shown log; put a written Azahar save back in.
    can_bank_all: bool = False
    can_put_into_azahar: bool = False
    put_label: str = PUT_INTO_AZAHAR


@dataclass(frozen=True)
class Destination:
    """Somewhere selected tablets can go: an adventure log (`Target`) or a bank folder name."""

    label: str
    kind: Literal["log", "bank"]
    target: object
    # For a log: who plays it, how long and how full ("Auster, 135h, 24/24, full").
    detail: str = field(default="", compare=False)
    full: bool = field(default=False, compare=False)


@dataclass(frozen=True)
class FoundSave:
    """One save the scan found: what to call it, where it is and what it holds."""

    label: str
    path: Path
    logs_text: str


@dataclass(frozen=True)
class ActionBar:
    selected_count: int
    summary: str
    quick_copy_label: str | None
    can_move: bool
    can_reset: bool
    can_remove: bool


@dataclass(frozen=True)
class Confirm:
    """A question the user must accept before anything changes.

    `on_ok` carries out the accepted action (usually the same command with `confirmed=True`)
    and returns its own outcome. `notices` are shown together with the question, for example
    the result of a write that is followed by the offer to put the save into Azahar.
    """

    title: str
    text: str
    ok_label: str
    cancel_label: str = "Cancel"
    notices: tuple[Notice, ...] = ()
    on_ok: Callable[[], "list[Notice] | Confirm"] | None = field(
        default=None, compare=False, repr=False
    )


# What every command returns: notices to show, or a question to ask first.
type Outcome = list[Notice] | Confirm


@dataclass(frozen=True)
class ToolbarView:
    undo_label: str | None
    redo_label: str | None
    can_write: bool
    write_label: str
    # Shorter words for the compact strip, when the full ones would not fit there.
    short_label: str | None = None
