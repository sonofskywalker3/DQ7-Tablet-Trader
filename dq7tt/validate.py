"""Checks run before any write: refuse saves that would break in the game."""

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from dq7tt.chunks import check_layout
from dq7tt.constants import (
    CHECKSUM_BYTES,
    RECEIVED_COUNT_OFFSET,
    RECEIVED_END,
    RECEIVED_OFFSET,
    RECEIVED_SLOTS,
    SELFMADE_COUNT_OFFSET,
    SELFMADE_END,
    SELFMADE_OFFSET,
)
from dq7tt.database import TabletDatabase, describe
from dq7tt.errors import CorruptSaveError, TabletTraderError, ValidationError
from dq7tt.savefile import SaveFile, SlotRole
from dq7tt.tablets import TabletKind, TabletRecord


class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class Problem:
    severity: Severity
    code: str
    message: str
    slot: int | None = None

    def __str__(self) -> str:
        return self.message


def _error(code: str, message: str, slot: int | None = None) -> Problem:
    return Problem(Severity.ERROR, code, message, slot)


def _warning(code: str, message: str, slot: int | None = None) -> Problem:
    return Problem(Severity.WARNING, code, message, slot)


def _live(save: SaveFile) -> tuple[TabletRecord, ...] | None:
    """The live records, or None when the list cannot be read."""
    try:
        return save.received.live
    except CorruptSaveError:
        return None


def _layout_problems(edited: SaveFile, original: SaveFile) -> list[Problem]:
    for save in (edited, original):
        try:
            check_layout(save.to_bytes())
        except TabletTraderError as exc:
            return [_error("LAYOUT", f"The file is not a save this tool understands. {exc}")]
    return []


def _outside_problems(edited: SaveFile, original: SaveFile) -> list[Problem]:
    """Flag any difference outside the checksum, the received list and the self-made tablets.

    The self-made region has its own, more specific check.
    """
    a, b = edited.to_bytes(), original.to_bytes()
    skipped = (
        range(CHECKSUM_BYTES),
        range(RECEIVED_OFFSET, RECEIVED_END),
        range(SELFMADE_OFFSET, SELFMADE_END),
        range(RECEIVED_COUNT_OFFSET, RECEIVED_COUNT_OFFSET + 1),
        range(SELFMADE_COUNT_OFFSET, SELFMADE_COUNT_OFFSET + 1),
    )
    if any(
        x != y and not any(i in r for r in skipped)
        for i, (x, y) in enumerate(zip(a, b, strict=True))
    ):
        return [
            _error(
                "OUTSIDE_CHANGED",
                "Something outside the tablet list changed. Nothing was written.",
            )
        ]
    return []


def _received_region(save: SaveFile) -> tuple[bytes, int]:
    data = save.to_bytes()
    return data[RECEIVED_OFFSET:RECEIVED_END], data[RECEIVED_COUNT_OFFSET]


def _selfmade_problems(edited: SaveFile, original: SaveFile) -> list[Problem]:
    a, b = edited.to_bytes(), original.to_bytes()
    if (
        a[SELFMADE_OFFSET:SELFMADE_END] != b[SELFMADE_OFFSET:SELFMADE_END]
        or a[SELFMADE_COUNT_OFFSET] != b[SELFMADE_COUNT_OFFSET]
    ):
        return [
            _error(
                "SELFMADE_CHANGED",
                "Your own tablets were changed. This tool never edits them.",
            )
        ]
    return []


REMOVAL_WARNED_KINDS = frozenset({TabletKind.STORY, TabletKind.RESIDENT})


def _removed_problems(
    original: SaveFile, live: tuple[TabletRecord, ...], db: TabletDatabase
) -> list[Problem]:
    kept = {r.identity for r in live}
    problems: list[Problem] = []
    for rec in _live(original) or ():
        name, kind = describe(rec, db)
        if kind in REMOVAL_WARNED_KINDS and rec.identity not in kept:
            problems.append(
                _warning(
                    "REMOVED_SPECIAL",
                    f"{name} was removed. It came from the story or a Haven resident "
                    "and may be hard to get back.",
                )
            )
    return problems


def _record_problems(
    edited: SaveFile,
    original: SaveFile,
    live: tuple[TabletRecord, ...],
    db: TabletDatabase,
    allowed: frozenset[bytes],
) -> list[Problem]:
    problems: list[Problem] = []
    original_live = _live(original) or ()
    original_by_identity = {r.identity: r for r in original_live}

    for identity, n in Counter(r.identity for r in live).items():
        if n > 1:
            name, _ = describe(
                TabletRecord(next(r.raw for r in live if r.identity == identity)), db
            )
            problems.append(_error("DUPLICATE", f"{name} appears {n} times in the list."))

    for slot, rec in enumerate(live):
        name, kind = describe(rec, db)
        before = original_by_identity.get(rec.identity)
        is_new = before is None
        if not rec.clear_counts_agree and (is_new or before.clear_counts_agree):
            problems.append(
                _error(
                    "CLEAR_MISMATCH",
                    f"{name} has two clear counts that disagree, which the game may reject.",
                    slot,
                )
            )
        if not is_new:
            continue
        info = db.lookup(rec)
        if rec.identity in allowed:
            pass
        elif info is None:
            problems.append(
                _error("UNKNOWN_NEW", f"{name} is not a tablet this tool knows how to add.", slot)
            )
        elif info.record.identity != rec.identity:
            problems.append(
                _error(
                    "UNKNOWN_NEW",
                    f"{name} does not match the copy this tool knows, so it will not be added.",
                    slot,
                )
            )
        elif not info.verified:
            problems.append(
                _error(
                    "UNVERIFIED_NEW",
                    f"{name} has not been tested on a real save yet, so it cannot be added.",
                    slot,
                )
            )
        if kind == TabletKind.STORY:
            problems.append(
                _warning(
                    "STORY_ADDED",
                    f"{name} is a story tablet. The story changes it causes live elsewhere "
                    "in the save and are not copied.",
                    slot,
                )
            )
    return problems


def validate(
    edited: SaveFile,
    original: SaveFile,
    db: TabletDatabase,
    *,
    allowed: frozenset[bytes] = frozenset(),
) -> list[Problem]:
    """Return every problem found; ERRORs mean the edited save must not be written.

    Identities in `allowed` came from a real save's received list and are never UNKNOWN_NEW.
    """
    problems = _layout_problems(edited, original)
    if problems:
        return problems
    if not edited.checksum_ok:
        problems.append(
            _error("CHECKSUM", "The save's checksum is wrong, so the game would reject it.")
        )
    if not original.checksum_ok:
        problems.append(
            _warning(
                "INPUT_CHECKSUM", "The original save had a wrong checksum. The new one is correct."
            )
        )
    problems += _selfmade_problems(edited, original)
    problems += _outside_problems(edited, original)

    live = _live(edited)
    if live is None:
        problems.append(
            _error("COUNT_RANGE", f"The tablet count is outside 0 to {RECEIVED_SLOTS}.")
        )
        return problems
    problems += _record_problems(edited, original, live, db, allowed)
    problems += _removed_problems(original, live, db)

    if edited.role == SlotRole.QUICK_SAVE and _received_region(edited) != _received_region(
        original
    ):
        problems.append(
            _warning(
                "QUICK_SAVE",
                "This is the quick save. The game may discard it, so the change may not last.",
            )
        )
    return problems


def require_valid(
    edited: SaveFile,
    original: SaveFile,
    db: TabletDatabase,
    *,
    allowed: frozenset[bytes] = frozenset(),
) -> None:
    """Raise ValidationError carrying every problem if any of them is an ERROR."""
    problems = validate(edited, original, db, allowed=allowed)
    if any(p.severity == Severity.ERROR for p in problems):
        raise ValidationError(problems)
