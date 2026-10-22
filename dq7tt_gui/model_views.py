"""Pure builders that turn session and bank data into the frozen values the window draws."""

import logging
from collections.abc import Collection, Mapping, Sequence

from dq7tt.bank import ROOT_FOLDER, BankTablet
from dq7tt.constants import RECEIVED_SLOTS
from dq7tt.savefile import SaveFile, SlotRole
from dq7tt.sources import SaveSource, SourceKind
from dq7tt.tablets import TabletKind, TabletRecord
from dq7tt_gui.viewmodels import FolderChip, FoundSave, LogChip, PaneSide, PaneView, TabletRow

SECONDS_PER_HOUR = 3600
SINGLE = 1
ROLE_ORDER = (SlotRole.LOG_1, SlotRole.LOG_2, SlotRole.LOG_3, SlotRole.QUICK_SAVE)
SHORT_LABELS: dict[SlotRole, str] = {
    SlotRole.LOG_1: "Log 1",
    SlotRole.LOG_2: "Log 2",
    SlotRole.LOG_3: "Log 3",
    SlotRole.QUICK_SAVE: "Quick save",
}
LONG_LABELS: dict[SlotRole, str] = {
    SlotRole.LOG_1: "Adventure log 1",
    SlotRole.LOG_2: "Adventure log 2",
    SlotRole.LOG_3: "Adventure log 3",
    SlotRole.QUICK_SAVE: "Quick save (suspended game)",
}
UNSORTED = "Unsorted"
FULL_TEXT = "full"
NOT_WRITTEN = " (changes not written yet)"
NO_SAVE_TITLE = "No save open"
NO_SAVE_TEXT = "Open a save, or use Find saves to look for one."
EMPTY_LOG_TEXT = "This adventure log has no tablets."
EMPTY_FOLDER_TEXT = "This bank folder is empty."
BANK_TITLE = "Bank"
SECOND_SAVE = "Second save"
TAB_LABELS: dict[SourceKind, str] = {
    SourceKind.CHECKPOINT: "Checkpoint",
    SourceKind.JKSM: "JKSM",
    SourceKind.AZAHAR: "Azahar",
}
SaveRows = Sequence[tuple[str, TabletKind, TabletRecord]]


def short_label(role: SlotRole) -> str:
    return SHORT_LABELS.get(role, str(role))


def tab_label(kind: SourceKind) -> str:
    """A tab-sized name for a save: where it came from, else "Second save"."""
    return TAB_LABELS.get(kind, SECOND_SAVE)


def folder_label(name: str) -> str:
    return UNSORTED if name == ROOT_FOLDER else name


def what(names: Sequence[str]) -> str:
    """One tablet's name, or "N tablets"."""
    return names[0] if len(names) == SINGLE else f"{len(names)} tablets"


def tablets_text(count: int) -> str:
    return "1 tablet" if count == SINGLE else f"{count} tablets"


def ordered_roles(roles: Collection[SlotRole]) -> list[SlotRole]:
    """The roles a save offers, logs first and the quick save last."""
    return [role for role in ROLE_ORDER if role in roles]


def default_role(roles: Collection[SlotRole]) -> SlotRole:
    """The log shown first: never the quick save unless it is all there is."""
    return ordered_roles(roles)[0]


def chip_detail(save: SaveFile) -> str:
    """Who is playing the log and for how long, like "Auster, 135h"."""
    hours = save.playtime_seconds // SECONDS_PER_HOUR
    parts = [save.hero_name] if save.hero_name else []
    parts.append(f"{hours}h")
    return ", ".join(parts)


def fill_text(save: SaveFile) -> str:
    """How many tablets the log holds out of how many it can, like "23/24"."""
    return f"{save.received.count}/{RECEIVED_SLOTS}"


def is_full(save: SaveFile) -> bool:
    return save.received.count >= RECEIVED_SLOTS


def destination_detail(save: SaveFile) -> str:
    """A log as a place to send tablets: who, how long, how full, and "full" when it is."""
    parts = [chip_detail(save), fill_text(save)]
    if is_full(save):
        parts.append(FULL_TEXT)
    return ", ".join(parts)


def log_chips(saves: Mapping[SlotRole, SaveFile], active: SlotRole | None) -> tuple[LogChip, ...]:
    return tuple(
        LogChip(
            role=role,
            label=short_label(role),
            detail=chip_detail(saves[role]),
            fill=fill_text(saves[role]),
            active=role is active,
            muted=role is SlotRole.QUICK_SAVE,
        )
        for role in ordered_roles(saves)
    )


def save_rows(side: PaneSide, rows: SaveRows, selected: Collection[int]) -> tuple[TabletRow, ...]:
    return tuple(
        TabletRow(i, name, kind, record.clear_count, i in selected, f"{side}:{i}")
        for i, (name, kind, record) in enumerate(rows)
    )


def bank_rows(
    side: PaneSide, tablets: Sequence[BankTablet], selected: Collection[int]
) -> tuple[TabletRow, ...]:
    return tuple(
        TabletRow(i, t.name, t.kind, t.clear_count, i in selected, f"{side}:{i}")
        for i, t in enumerate(tablets)
    )


def empty_pane(side: PaneSide) -> PaneView:
    return PaneView(side, NO_SAVE_TITLE, "", NO_SAVE_TEXT, (), (), (), "")


def save_pane(
    side: PaneSide,
    label: str,
    saves: Mapping[SlotRole, SaveFile],
    role: SlotRole,
    rows: tuple[TabletRow, ...],
    dirty: bool,
    can_put_into_azahar: bool = False,
) -> PaneView:
    subtitle = LONG_LABELS.get(role, str(role)) + (NOT_WRITTEN if dirty else "")
    return PaneView(
        side=side,
        title=label,
        subtitle=subtitle,
        empty_text=None if rows else EMPTY_LOG_TEXT,
        log_chips=log_chips(saves, role),
        folder_chips=(),
        rows=rows,
        count_text=f"{len(rows)} of {RECEIVED_SLOTS}",
        can_bank_all=bool(rows),
        can_put_into_azahar=can_put_into_azahar,
    )


def folder_chips(counts: Mapping[str, int], active: str) -> tuple[FolderChip, ...]:
    return tuple(
        FolderChip(name, folder_label(name), count, name == active)
        for name, count in counts.items()
    )


def bank_pane(
    side: PaneSide,
    root: str,
    chips: tuple[LogChip, ...],
    folders: tuple[FolderChip, ...],
    rows: tuple[TabletRow, ...],
    problem: str | None = None,
) -> PaneView:
    empty = problem if problem is not None else (None if rows else EMPTY_FOLDER_TEXT)
    return PaneView(
        side=side,
        title=BANK_TITLE,
        subtitle=root,
        empty_text=empty,
        log_chips=chips,
        folder_chips=folders,
        rows=rows,
        count_text=tablets_text(len(rows)),
    )


SAVE_FILE_PATTERN = "save*.bin"
log = logging.getLogger(__name__)


def found_save(source: SaveSource) -> FoundSave:
    """A scan result as the Find saves list shows it."""
    try:
        count = len(list(source.save_dir.glob(SAVE_FILE_PATTERN)))
    except OSError as exc:
        log.warning("could not count the logs in %s: %s", source.save_dir, exc)
        return FoundSave(source.label, source.path, "")
    noun = "adventure log" if count == SINGLE else "adventure logs"
    return FoundSave(source.label, source.path, f"{count} {noun}")
