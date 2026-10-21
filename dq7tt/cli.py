"""Command line tool: list, add, copy and remove tablets, always into a new folder."""

import argparse
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from dq7tt.database import TabletDatabase, describe
from dq7tt.errors import TabletTraderError, UnknownTabletError, UsageError
from dq7tt.folder import SaveFolder, default_output_path, write_edited
from dq7tt.savefile import SaveFile, SlotRole
from dq7tt.tablet_list import ReceivedList
from dq7tt.validate import Severity, require_valid, validate

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
ROLE_LABELS = {
    SlotRole.QUICK_SAVE: "Quick save",
    SlotRole.LOG_1: "Adventure log 1",
    SlotRole.LOG_2: "Adventure log 2",
    SlotRole.LOG_3: "Adventure log 3",
}


def out(text: str = "") -> None:
    sys.stdout.write(text + "\n")


def _label(role: SlotRole) -> str:
    return ROLE_LABELS.get(role, str(role).capitalize())


def _playtime(seconds: int) -> str:
    minutes = seconds // SECONDS_PER_MINUTE
    return f"{minutes // MINUTES_PER_HOUR}:{minutes % MINUTES_PER_HOUR:02d}"


def _get_save(folder: SaveFolder, role: SlotRole) -> SaveFile:
    try:
        return folder.files[role]
    except KeyError:
        raise UsageError(f"{folder.path} has no {_label(role).lower()} save.") from None


def _slot_index(lst: ReceivedList, slot: int, role: SlotRole) -> int:
    """Convert the 1-based position shown by `list` to a 0-based index."""
    if not 1 <= slot <= lst.count:
        raise UsageError(
            f"{_label(role)} has {lst.count} tablets, so position {slot} does not exist."
        )
    return slot - 1


def _check_quick(role: SlotRole, allow: bool) -> None:
    if role == SlotRole.QUICK_SAVE and not allow:
        raise UsageError(
            "The quick save may be discarded by the game. Add --allow-quick-save to edit it anyway."
        )


def _finish(
    folder: SaveFolder,
    role: SlotRole,
    edited: SaveFile,
    out_dir: Path | None,
    db: TabletDatabase,
    protect: Sequence[Path] = (),
) -> None:
    """Validate, write the new folder next to the input (or at `out_dir`), and report it."""
    original = _get_save(folder, role)
    require_valid(edited, original, db)
    for problem in validate(edited, original, db):
        if problem.severity == Severity.WARNING:
            out(f"Warning: {problem.message}")
    target = out_dir if out_dir is not None else default_output_path(folder.path, datetime.now())
    write_edited(folder.path, target, {role: edited}, protect)
    out(f"Wrote {target}")


def cmd_list(args: argparse.Namespace) -> None:
    db = TabletDatabase.load()
    folder = SaveFolder.open(args.path)
    for role, save in folder.files.items():
        lst = save.received
        out(
            f"{_label(role)}: {save.hero_name}, {_playtime(save.playtime_seconds)}, "
            f"{lst.count}/{len(lst.slots)}"
        )
        for i, rec in enumerate(lst.live, start=1):
            name, kind = describe(rec, db)
            out(f"  {i:2d}. {name} [{kind.value}] cleared {rec.clear_count}")


def cmd_add(args: argparse.Namespace) -> None:
    db = TabletDatabase.load()
    role = ROLE_BY_CHOICE[args.log]
    _check_quick(role, args.allow_quick_save)
    info = db.by_name(args.tablet)
    if not info.verified:
        raise UnknownTabletError(
            f"{info.name_en} has not been tested on a real save yet, so it cannot be added."
        )
    folder = SaveFolder.open(args.path)
    save = _get_save(folder, role)
    edited = save.with_received(save.received.insert(info.record, 0))
    _finish(folder, role, edited, args.out, db)


def cmd_copy(args: argparse.Namespace) -> None:
    db = TabletDatabase.load()
    from_role, to_role = ROLE_BY_CHOICE[args.from_log], ROLE_BY_CHOICE[args.to_log]
    _check_quick(to_role, args.allow_quick_save)
    source = SaveFolder.open(args.src_path)
    target = source if args.dst_path.resolve() == args.src_path.resolve() else None
    target = target or SaveFolder.open(args.dst_path)
    from_save = _get_save(source, from_role)
    record = from_save.received.live[_slot_index(from_save.received, args.slot, from_role)]
    if args.reset_clears:
        record = record.with_clear_count(0)
    to_save = _get_save(target, to_role)
    edited = to_save.with_received(to_save.received.insert(record, 0))
    _finish(target, to_role, edited, args.out, db, protect=[source.path])


def cmd_remove(args: argparse.Namespace) -> None:
    db = TabletDatabase.load()
    role = ROLE_BY_CHOICE[args.log]
    _check_quick(role, args.allow_quick_save)
    folder = SaveFolder.open(args.path)
    save = _get_save(folder, role)
    index = _slot_index(save.received, args.slot, role)
    edited = save.with_received(save.received.remove(index))
    _finish(folder, role, edited, args.out, db)


def _add_write_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--out", type=Path, help="new folder to write (default: next to the input)")
    p.add_argument("--allow-quick-save", action="store_true", help="allow editing the quick save")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dq7tt", description="Edit Dragon Quest VII tablets in a copy of your save folder."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="show every log and its tablets")
    p.add_argument("path", type=Path)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("add", help="add a tablet at the top of a log")
    p.add_argument("path", type=Path)
    p.add_argument("--log", choices=LOG_CHOICES, required=True)
    p.add_argument("--tablet", required=True, help="tablet name, for example 'Mount Oddna'")
    _add_write_options(p)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("copy", help="copy one tablet from one log to another")
    p.add_argument("src_path", type=Path)
    p.add_argument("--from-log", choices=LOG_CHOICES, required=True)
    p.add_argument("--slot", type=int, required=True, help="position shown by list, from 1")
    p.add_argument("dst_path", type=Path)
    p.add_argument("--to-log", choices=LOG_CHOICES, required=True)
    p.add_argument("--reset-clears", action="store_true", help="set the clear count to 0")
    _add_write_options(p)
    p.set_defaults(func=cmd_copy)

    p = sub.add_parser("remove", help="remove one tablet from a log")
    p.add_argument("path", type=Path)
    p.add_argument("--log", choices=LOG_CHOICES, required=True)
    p.add_argument("--slot", type=int, required=True, help="position shown by list, from 1")
    _add_write_options(p)
    p.set_defaults(func=cmd_remove)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except TabletTraderError as exc:
        out(f"Refused: {exc}")
        return EXIT_REFUSED
    return EXIT_OK
