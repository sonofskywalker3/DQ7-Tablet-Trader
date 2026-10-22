"""The tablet bank: a personal store of tablets on disk, one small JSON file each."""

import json
import logging
import os
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

import send2trash

from dq7tt.constants import RECEIVED_RECORD_SIZE, SELFMADE_RECORD_SIZE
from dq7tt.database import TabletDatabase, describe
from dq7tt.errors import BankFileError, BankProblem, DuplicateTabletError, SaveIOError
from dq7tt.savefile import SaveFile
from dq7tt.tablets import TabletKind, TabletRecord

log = logging.getLogger(__name__)

BANK_EXTENSION = ".dq7tablet"
BANK_FORMAT = 1
BANK_LAYOUT = "western"
TEMP_SUFFIX = ".tmp"
ROOT_FOLDER = ""
HIDDEN_PREFIX = "."
FALLBACK_STEM = "Tablet"
UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
TRAILING_JUNK = " ."
UNSAFE_REPLACEMENT = "_"
RESERVED_NAMES = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)
RESERVED_PREFIX = "_"
FIRST_SUFFIX = 2
PathList = list[Path]


class BankList(StrEnum):
    RECEIVED = "received"
    SELFMADE = "selfmade"


RECORD_SIZES = {
    BankList.RECEIVED: RECEIVED_RECORD_SIZE,
    BankList.SELFMADE: SELFMADE_RECORD_SIZE,
}

FIELD_ORDER = (
    "format",
    "list",
    "layout",
    "record_hex",
    "name",
    "kind",
    "clear_count",
    "source",
    "region",
    "from_real_save",
)


@dataclass(frozen=True)
class BankTablet:
    path: Path
    list_kind: BankList
    record_raw: bytes
    name: str
    kind: TabletKind
    clear_count: int
    source_note: str
    region: str
    from_real_save: bool

    @property
    def identity(self) -> bytes:
        """The record with clear-count bytes ignored (received records only)."""
        if self.list_kind is BankList.RECEIVED:
            return TabletRecord(self.record_raw).identity
        return self.record_raw


BankTabletList = list[BankTablet]


def safe_file_stem(name: str) -> str:
    """Make a tablet name usable as a Windows file name stem."""
    stem = UNSAFE_CHARS.sub(UNSAFE_REPLACEMENT, name).rstrip(TRAILING_JUNK)
    if not stem:
        return FALLBACK_STEM
    if stem.split(".", 1)[0].rstrip(TRAILING_JUNK).lower() in RESERVED_NAMES:
        stem = RESERVED_PREFIX + stem
    return stem


def _check_folder_name(name: str) -> None:
    problem = None
    reason = BankProblem.EMPTY
    if not name:
        problem = "is empty"
    elif name in (".", "..") or name.startswith(HIDDEN_PREFIX):
        problem, reason = "must not start with a dot", BankProblem.HIDDEN
    elif UNSAFE_CHARS.search(name):
        problem = "contains a character that is not allowed in a folder name"
        reason = BankProblem.BAD_CHARACTERS
    elif name != name.rstrip(TRAILING_JUNK):
        problem, reason = "must not end with a space or dot", BankProblem.TRAILING
    elif name.split(".", 1)[0].lower() in RESERVED_NAMES:
        problem, reason = "is a reserved name", BankProblem.RESERVED
    if problem is not None:
        raise BankFileError(f"folder name {name!r} {problem}", reason)


def _field(data: dict[str, object], key: str, kind: type) -> object:
    value = data.get(key)
    if not isinstance(value, kind) or (kind is int and isinstance(value, bool)):
        raise BankFileError(f"field {key!r} is missing or has the wrong type", BankProblem.DAMAGED)
    return value


def _parse(path: Path, text: str) -> BankTablet:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise BankFileError(f"{path.name} is not valid JSON", BankProblem.DAMAGED) from exc
    if not isinstance(data, dict):
        raise BankFileError(f"{path.name} is not a tablet file", BankProblem.DAMAGED)
    version = data.get("format")
    if not isinstance(version, int) or isinstance(version, bool) or version != BANK_FORMAT:
        raise BankFileError(f"{path.name} has an unknown format version", BankProblem.DAMAGED)
    if data.get("layout") != BANK_LAYOUT:
        raise BankFileError(
            f"{path.name} is not a {BANK_LAYOUT} layout tablet", BankProblem.DAMAGED
        )
    try:
        list_kind = BankList(data.get("list"))
    except ValueError as exc:
        raise BankFileError(f"{path.name} names an unknown list", BankProblem.DAMAGED) from exc
    try:
        hex_text = str(_field(data, "record_hex", str))
        if any(c.isspace() for c in hex_text):
            raise ValueError("whitespace in record_hex")
        raw = bytes.fromhex(hex_text)
    except ValueError as exc:
        raise BankFileError(f"{path.name} has damaged record data", BankProblem.DAMAGED) from exc
    if len(raw) != RECORD_SIZES[list_kind]:
        raise BankFileError(f"{path.name} has a record of the wrong length", BankProblem.DAMAGED)
    try:
        kind = TabletKind(_field(data, "kind", str))
    except ValueError as exc:
        raise BankFileError(f"{path.name} has an unknown tablet kind", BankProblem.DAMAGED) from exc
    if list_kind is BankList.SELFMADE:
        kind = TabletKind.UNKNOWN
    return BankTablet(
        path=path,
        list_kind=list_kind,
        record_raw=raw,
        name=str(_field(data, "name", str)),
        kind=kind,
        clear_count=int(_field(data, "clear_count", int)),  # type: ignore[call-overload]
        source_note=str(_field(data, "source", str)),
        region=str(_field(data, "region", str)),
        from_real_save=bool(_field(data, "from_real_save", bool)),
    )


def _payload(tablet: BankTablet) -> str:
    values = {
        "format": BANK_FORMAT,
        "list": tablet.list_kind.value,
        "layout": BANK_LAYOUT,
        "record_hex": tablet.record_raw.hex(),
        "name": tablet.name,
        "kind": tablet.kind.value,
        "clear_count": tablet.clear_count,
        "source": tablet.source_note,
        "region": tablet.region,
        "from_real_save": tablet.from_real_save,
    }
    return json.dumps({k: values[k] for k in FIELD_ORDER}, indent=2, ensure_ascii=False) + "\n"


class Bank:
    def __init__(self, root: Path) -> None:
        self.root = Path(root).absolute()

    # folders

    def _folder_path(self, folder: str) -> Path:
        if folder == ROOT_FOLDER:
            return self.root
        _check_folder_name(folder)
        return self.root / folder

    def folders(self) -> list[str]:
        try:
            entries = sorted(self.root.iterdir()) if self.root.is_dir() else []
        except OSError as exc:
            raise SaveIOError(f"could not read the bank folder: {exc}") from exc
        names = [p.name for p in entries if p.is_dir() and not p.name.startswith(HIDDEN_PREFIX)]
        if any(p.is_file() and p.suffix == BANK_EXTENSION for p in entries):
            names.insert(0, ROOT_FOLDER)
        return names

    def create_folder(self, name: str) -> None:
        _check_folder_name(name)
        target = self.root / name
        if target.exists():
            raise BankFileError(f"folder {name!r} already exists", BankProblem.EXISTS)
        try:
            target.mkdir(parents=True)
        except OSError as exc:
            raise SaveIOError(f"could not create folder {name!r}: {exc}") from exc

    def rename_folder(self, old: str, new: str) -> None:
        _check_folder_name(old)
        _check_folder_name(new)
        source, target = self.root / old, self.root / new
        if not source.is_dir():
            raise BankFileError(f"folder {old!r} does not exist", BankProblem.MISSING)
        case_only = old != new and old.lower() == new.lower()
        if target.exists() and not case_only:
            raise BankFileError(f"folder {new!r} already exists", BankProblem.EXISTS)
        try:
            source.rename(target)
        except OSError as exc:
            raise SaveIOError(f"could not rename folder {old!r}: {exc}") from exc

    # reading

    def read(self, path: Path) -> BankTablet:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise BankFileError(
                f"could not read {Path(path).name}: {exc}", BankProblem.UNREADABLE
            ) from exc
        return _parse(Path(path), text)

    def list(self, folder: str) -> BankTabletList:
        directory = self._folder_path(folder)
        if not directory.is_dir():
            return []
        try:
            entries = sorted(directory.iterdir())
        except OSError as exc:
            raise SaveIOError(f"could not read folder {folder or 'the bank'}: {exc}") from exc
        tablets: list[BankTablet] = []
        for path in entries:
            if not path.is_file() or path.suffix != BANK_EXTENSION:
                continue
            try:
                tablets.append(self.read(path))
            except BankFileError as exc:
                log.warning("skipping bank file %s: %s", path, exc)
        return sorted(tablets, key=lambda t: (t.name.lower(), t.path.name.lower()))

    # writing

    def _unique_path(self, directory: Path, stem: str) -> Path:
        candidate = directory / f"{stem}{BANK_EXTENSION}"
        number = FIRST_SUFFIX
        while candidate.exists():
            candidate = directory / f"{stem} ({number}){BANK_EXTENSION}"
            number += 1
        return candidate

    def _write_new(self, tablet: BankTablet, directory: Path) -> Path:
        stem = safe_file_stem(tablet.name)
        temp: Path | None = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            fd, temp_name = tempfile.mkstemp(dir=directory, suffix=TEMP_SUFFIX)
            temp = Path(temp_name)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(_payload(tablet))
            return self._publish(temp, directory, stem)
        except OSError as exc:
            raise SaveIOError(f"could not write {stem}{BANK_EXTENSION}: {exc}") from exc
        finally:
            if temp is not None:
                temp.unlink(missing_ok=True)

    def _publish(self, temp: Path, directory: Path, stem: str) -> Path:
        """Give the finished temp file its final name without ever replacing a file."""
        while True:
            target = self._unique_path(directory, stem)
            try:
                os.link(temp, target)
            except FileExistsError:
                continue
            except (OSError, NotImplementedError, AttributeError):
                try:
                    with open(target, "xb") as out:
                        out.write(temp.read_bytes())
                except FileExistsError:
                    continue
            return target

    def _check_not_duplicate(self, folder: str, tablet: BankTablet, source: Path | None) -> None:
        skip = source.resolve() if source is not None else None
        for t in self.list(folder):
            if skip is not None and t.path.resolve() == skip:
                continue
            if t.list_kind is tablet.list_kind and t.identity == tablet.identity:
                raise DuplicateTabletError(
                    f"{tablet.name} is already in {folder or 'the bank'}", tablet.name
                )

    def add(
        self,
        record: TabletRecord,
        folder: str,
        db: TabletDatabase,
        source_note: str,
        region: str,
        from_real_save: bool,
    ) -> Path:
        directory = self._folder_path(folder)
        name, kind = describe(record, db)
        tablet = BankTablet(
            path=directory,
            list_kind=BankList.RECEIVED,
            record_raw=record.raw,
            name=name,
            kind=kind,
            clear_count=record.clear_count,
            source_note=source_note,
            region=region,
            from_real_save=from_real_save,
        )
        self._check_not_duplicate(folder, tablet, None)
        return self._write_new(tablet, directory)

    def import_save(
        self, save: SaveFile, folder: str, db: TabletDatabase, source_note: str, region: str
    ) -> PathList:
        added: list[Path] = []
        for record in save.received.live:
            try:
                added.append(self.add(record, folder, db, source_note, region, True))
            except DuplicateTabletError:
                continue
        return added

    def _check_inside(self, path: Path) -> Path:
        try:
            resolved = Path(path).resolve()
            resolved.relative_to(self.root.resolve())
        except (ValueError, OSError) as exc:
            raise BankFileError(f"{path} is not inside the bank", BankProblem.OUTSIDE) from exc
        return resolved

    def move(self, paths: Sequence[Path], folder: str) -> PathList:
        directory = self._folder_path(folder)
        target_dir = directory.resolve()
        plan: list[tuple[Path, BankTablet]] = []
        for original in paths:
            tablet = self.read(self._check_inside(original))
            plan.append((Path(original), tablet))
        seen: set[tuple[BankList, bytes]] = set()
        for _, tablet in plan:
            if tablet.path.parent == target_dir:
                continue
            key = (tablet.list_kind, tablet.identity)
            if key in seen:
                raise DuplicateTabletError(f"{tablet.name} appears twice in this move", tablet.name)
            seen.add(key)
            self._check_not_duplicate(folder, tablet, tablet.path)
        moved: list[Path] = []
        for original, tablet in plan:
            if tablet.path.parent == target_dir:
                moved.append(original)
                continue
            target = self._unique_path(directory, tablet.path.stem)
            try:
                directory.mkdir(parents=True, exist_ok=True)
                os.rename(tablet.path, target)
            except OSError as exc:
                raise SaveIOError(f"could not move {tablet.path.name}: {exc}") from exc
            moved.append(target)
        return moved

    def delete(self, paths: Sequence[Path]) -> None:
        root = self.root.resolve()
        resolved = [self._check_inside(p) for p in paths]
        for path in resolved:
            if path == root or not path.is_file() or path.suffix != BANK_EXTENSION:
                raise BankFileError(
                    f"{path.name} is not a tablet file in the bank", BankProblem.NOT_TABLET
                )
        for path in resolved:
            try:
                send2trash.send2trash(str(path))
            except OSError as exc:
                raise SaveIOError(f"could not delete {path.name}: {exc}") from exc
