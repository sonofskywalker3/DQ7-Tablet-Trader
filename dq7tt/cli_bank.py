"""Command line: scan for saves, the tablet bank, and putting a save into Azahar."""

import argparse
import logging
from datetime import datetime
from pathlib import Path

from dq7tt import output
from dq7tt.apppaths import load_settings
from dq7tt.bank import ROOT_FOLDER, Bank, BankTablet
from dq7tt.cli_common import (
    LOG_CHOICES,
    ROLE_BY_CHOICE,
    app_paths,
    check_quick,
    finish,
    out,
    session_scope,
    slot_index,
    summary,
    target_for,
)
from dq7tt.errors import TabletTraderError
from dq7tt.scan import default_roots, scan
from dq7tt.session_ops import load_saves

log = logging.getLogger(__name__)

BANK_HEADING = "Bank"
LOG_SEPARATOR = "; "


def _bank(args: argparse.Namespace) -> Bank:
    paths = app_paths(args)
    settings = load_settings(paths)
    return Bank(settings.bank_dir if settings.bank_dir else paths.bank_dir)


def _bank_line(tablet: BankTablet) -> str:
    return (
        f"  {tablet.name} [{tablet.kind.value}] cleared {tablet.clear_count}  ({tablet.path.name})"
    )


def cmd_scan(args: argparse.Namespace) -> None:
    paths = app_paths(args)
    roots = args.roots or default_roots()
    found = scan(roots, paths.work_dir)
    if not found:
        out("No Dragon Quest VII saves found.")
        return
    for source in found:
        try:
            files = load_saves(source)
        except TabletTraderError as exc:
            log.warning("could not read %s: %s", source.save_dir, exc)
            continue
        logs = LOG_SEPARATOR.join(summary(role, save) for role, save in files.items())
        out(f"{source.label} | {source.path} | {logs}")


def cmd_bank_list(args: argparse.Namespace) -> None:
    bank = _bank(args)
    folders = [args.folder] if args.folder is not None else bank.folders()
    for folder in folders:
        out(folder or BANK_HEADING)
        for tablet in bank.list(folder):
            out(_bank_line(tablet))


def cmd_bank_import(args: argparse.Namespace) -> None:
    bank = _bank(args)
    with session_scope(args) as (session, _):
        source_id = session.open(args.path)
        added = session.bank_all(target_for(session, source_id, args.log), bank, args.folder)
        out(f"Added {len(added)} tablets to {args.folder or 'the bank'}.")


def _bank_file(bank: Bank, name: Path) -> BankTablet:
    """A bank file given as a path, or as a name relative to the bank folder."""
    if not name.is_absolute() and not name.exists():
        return bank.read(bank.root / name)
    return bank.read(name)


def cmd_bank_add(args: argparse.Namespace) -> None:
    check_quick(ROLE_BY_CHOICE[args.log], args.allow_quick_save)
    bank = _bank(args)
    tablet = _bank_file(bank, args.file)
    with session_scope(args) as (session, paths):
        source_id = session.open(args.path)
        session.add_from_bank(target_for(session, source_id, args.log), tablet)
        finish(session, paths, source_id, args.out)


def cmd_bank_export(args: argparse.Namespace) -> None:
    bank = _bank(args)
    with session_scope(args) as (session, _):
        source_id = session.open(args.path)
        target = target_for(session, source_id, args.log)
        written = session.bank_from(
            target, slot_index(session, target, args.slot), bank, args.folder
        )
        out(f"Banked {written}")


def cmd_azahar_put(args: argparse.Namespace) -> None:
    backup = output.put_into_azahar(
        args.edited_dir, args.azahar_dir, app_paths(args), datetime.now()
    )
    out(str(backup))


def add_parsers(sub: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    p = sub.add_parser("scan", help="find Dragon Quest VII saves on this computer")
    p.add_argument("roots", nargs="*", type=Path, help="folders to search (default: known places)")
    p.set_defaults(func=cmd_scan)

    bank = sub.add_parser("bank", help="work with the tablet bank")
    bank_sub = bank.add_subparsers(dest="bank_command", required=True)

    p = bank_sub.add_parser("list", help="show banked tablets")
    p.add_argument("folder", nargs="?", default=None, help="bank folder (default: all)")
    p.set_defaults(func=cmd_bank_list)

    p = bank_sub.add_parser("import", help="bank every tablet of a log")
    p.add_argument("path", type=Path)
    p.add_argument("--log", choices=LOG_CHOICES, required=True)
    p.add_argument("--folder", default=ROOT_FOLDER, help="bank folder (default: bank root)")
    p.set_defaults(func=cmd_bank_import)

    p = bank_sub.add_parser("add", help="add a banked tablet to a log")
    p.add_argument("path", type=Path)
    p.add_argument("--log", choices=LOG_CHOICES, required=True)
    p.add_argument("--file", type=Path, required=True, help="bank file, or its name in the bank")
    p.add_argument("--out", type=Path, help="new folder to write (default: next to the input)")
    p.add_argument("--allow-quick-save", action="store_true", help="allow editing the quick save")
    p.set_defaults(func=cmd_bank_add)

    p = bank_sub.add_parser("export", help="bank one tablet of a log")
    p.add_argument("path", type=Path)
    p.add_argument("--log", choices=LOG_CHOICES, required=True)
    p.add_argument("--slot", type=int, required=True, help="position shown by list, from 1")
    p.add_argument("--folder", default=ROOT_FOLDER, help="bank folder (default: bank root)")
    p.set_defaults(func=cmd_bank_export)

    azahar = sub.add_parser("azahar", help="Azahar emulator saves")
    azahar_sub = azahar.add_subparsers(dest="azahar_command", required=True)
    p = azahar_sub.add_parser("put", help="copy edited saves into an Azahar save folder")
    p.add_argument("edited_dir", type=Path)
    p.add_argument("azahar_dir", type=Path)
    p.set_defaults(func=cmd_azahar_put)
