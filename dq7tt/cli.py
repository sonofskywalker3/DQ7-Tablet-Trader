"""Command line tool: list, add, copy and remove tablets, always into a new folder."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from dq7tt import cli_bank
from dq7tt.cli_common import (
    EXIT_OK,
    EXIT_REFUSED,
    LOG_CHOICES,
    ROLE_BY_CHOICE,
    check_quick,
    finish,
    out,
    session_scope,
    slot_index,
    summary,
    target_for,
)
from dq7tt.errors import TabletTraderError, UnknownTabletError
from dq7tt.session import Target

__all__ = ["EXIT_OK", "EXIT_REFUSED", "build_parser", "main", "out"]


def cmd_list(args: argparse.Namespace) -> None:
    with session_scope(args) as (session, _):
        source_id = session.open(args.path)
        for role, save in session.sources()[source_id].edited.items():
            out(summary(role, save))
            for i, (name, kind, record) in enumerate(
                session.tablets(Target(source_id, role)), start=1
            ):
                out(f"  {i:2d}. {name} [{kind.value}] cleared {record.clear_count}")


def cmd_add(args: argparse.Namespace) -> None:
    role = ROLE_BY_CHOICE[args.log]
    check_quick(role, args.allow_quick_save)
    with session_scope(args) as (session, paths):
        info = session.db.by_name(args.tablet)
        if not info.verified:
            raise UnknownTabletError(
                f"{info.name_en} has not been tested on a real save yet, so it cannot be added."
            )
        source_id = session.open(args.path)
        session.add_from_database(target_for(session, source_id, args.log), info.name_en)
        finish(session, paths, source_id, args.out)


def cmd_copy(args: argparse.Namespace) -> None:
    to_role = ROLE_BY_CHOICE[args.to_log]
    check_quick(to_role, args.allow_quick_save)
    with session_scope(args) as (session, paths):
        src_id = session.open(args.src_path)
        same = args.dst_path.resolve() == args.src_path.resolve()
        dst_id = src_id if same else session.open(args.dst_path)
        src = target_for(session, src_id, args.from_log)
        dst = target_for(session, dst_id, args.to_log)
        index = slot_index(session, src, args.slot)
        session.copy(src, index, dst, reset_clears=args.reset_clears)
        finish(session, paths, dst_id, args.out)


def cmd_remove(args: argparse.Namespace) -> None:
    check_quick(ROLE_BY_CHOICE[args.log], args.allow_quick_save)
    with session_scope(args) as (session, paths):
        source_id = session.open(args.path)
        target = target_for(session, source_id, args.log)
        session.remove(target, slot_index(session, target, args.slot))
        finish(session, paths, source_id, args.out)


def _add_write_options(p: argparse.ArgumentParser) -> None:
    p.add_argument("--out", type=Path, help="new folder to write (default: next to the input)")
    p.add_argument("--allow-quick-save", action="store_true", help="allow editing the quick save")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dq7tt", description="Edit Dragon Quest VII tablets in a copy of your save folder."
    )
    parser.add_argument(
        "--app-dir", type=Path, help="keep bank, backups and edited saves here (default: standard)"
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

    cli_bank.add_parsers(sub)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        args.func(args)
    except TabletTraderError as exc:
        out(f"Refused: {exc}")
        return EXIT_REFUSED
    return EXIT_OK
