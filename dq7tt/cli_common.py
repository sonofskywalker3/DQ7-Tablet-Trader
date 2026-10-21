"""Shared pieces of the command line: output, log choices, and the session helpers."""

import argparse
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from dq7tt.apppaths import AppPaths
from dq7tt.errors import UsageError, ValidationError
from dq7tt.savefile import SaveFile, SlotRole
from dq7tt.session import Session, Target
from dq7tt.session_ops import role_name
from dq7tt.validate import Problem, Severity

EXIT_OK = 0
EXIT_REFUSED = 2
SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60
QUICK_CHOICE = "quick"
LOG_CHOICES = ("1", "2", "3", QUICK_CHOICE)
ROLE_BY_CHOICE = {
    "1": SlotRole.LOG_1,
    "2": SlotRole.LOG_2,
    "3": SlotRole.LOG_3,
    QUICK_CHOICE: SlotRole.QUICK_SAVE,
}
ARTICLE = "the "


def out(text: str = "") -> None:
    stream = sys.stdout
    encoding = getattr(stream, "encoding", None) or "utf-8"
    safe = (text + "\n").encode(encoding, errors="replace").decode(encoding, errors="replace")
    stream.write(safe)


def label(role: SlotRole) -> str:
    """The role's name as a heading: "the quick save" becomes "Quick save"."""
    name = role_name(role).removeprefix(ARTICLE)
    return name[:1].upper() + name[1:]


def playtime(seconds: int) -> str:
    minutes = seconds // SECONDS_PER_MINUTE
    return f"{minutes // MINUTES_PER_HOUR}:{minutes % MINUTES_PER_HOUR:02d}"


def summary(role: SlotRole, save: SaveFile) -> str:
    lst = save.received
    time = playtime(save.playtime_seconds)
    return f"{label(role)}: {save.hero_name}, {time}, {lst.count}/{len(lst.slots)}"


def app_paths(args: argparse.Namespace) -> AppPaths:
    return AppPaths.under(args.app_dir) if args.app_dir else AppPaths.default()


@contextmanager
def session_scope(args: argparse.Namespace) -> Iterator[tuple[Session, AppPaths]]:
    """A session that always releases what it extracted, however the command ends."""
    paths = app_paths(args)
    session = Session(paths)
    try:
        yield session, paths
    finally:
        for source_id in list(session.sources()):
            session.close(source_id, force=True)


def target_for(session: Session, source_id: int, choice: str) -> Target:
    role = ROLE_BY_CHOICE[choice]
    source = session.sources()[source_id]
    if role not in source.edited:
        raise UsageError(f"{source.source.label} has no {label(role).lower()} save.")
    return Target(source_id, role)


def check_quick(role: SlotRole, allow: bool) -> None:
    if role == SlotRole.QUICK_SAVE and not allow:
        raise UsageError(
            "The quick save may be discarded by the game. Add --allow-quick-save to edit it anyway."
        )


def slot_index(session: Session, target: Target, slot: int) -> int:
    """Convert the 1-based position shown by `list` to a 0-based index."""
    count = len(session.tablets(target))
    if not 1 <= slot <= count:
        raise UsageError(
            f"{label(target.role)} has {count} tablets, so position {slot} does not exist."
        )
    return slot - 1


def finish(session: Session, paths: AppPaths, source_id: int, out_dir: Path | None) -> None:
    """Refuse on errors, print warnings, write the edited copy, and report where it went."""
    dirty = session.dirty_roles(source_id)
    problems = session.problems(source_id)
    shown: list[Problem] = [p for role in dirty for p in problems[role]]
    errors = [p for p in shown if p.severity is Severity.ERROR]
    if errors:
        raise ValidationError(errors)
    for problem in shown:
        if problem.severity is Severity.WARNING:
            out(f"Warning: {problem.message}")
    target = session.write(source_id, out_dir)
    out(f"Wrote {target}")
