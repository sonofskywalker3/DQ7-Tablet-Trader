"""Build dq7tt/data/tablets.json from preserved saves, upstream records and the name table."""

import csv
import json
import logging
import sys
from pathlib import Path

from dq7tt.constants import STORY_SERIALS
from dq7tt.errors import TabletTraderError
from dq7tt.savefile import SaveFile
from dq7tt.tablets import TabletKind, TabletRecord

LOG = logging.getLogger("build_tablet_db")
EXPECTED_ARGS = 5
UPSTREAM_EMPTY_NAME = "Empty"
SAVE_GLOB = "*/save*.bin"
SOURCE_SAVE = "save"
SOURCE_UPSTREAM = "upstream"
HEX_BASE = 16
SOURCE_NOTE = (
    "Tablet records from preserved DQ7 saves (DaniPhoFani, Gronya); "
    "Haven-resident records from {upstream}"
)


class BuildError(TabletTraderError):
    """The tablet database cannot be built from the given inputs."""


def _read_names(names: Path) -> dict[tuple[int, int], dict[str, str]]:
    rows: dict[tuple[int, int], dict[str, str]] = {}
    with names.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            key = (int(row["map_id"], HEX_BASE), int(row["serial"]))
            if key in rows:
                raise BuildError(f"two name rows share map {key[0]:#x} serial {key[1]}")
            rows[key] = row
    return rows


def _check_kind(row: dict[str, str], serial: int) -> TabletKind:
    kind = TabletKind(row["kind"])
    if (serial in STORY_SERIALS) != (kind == TabletKind.STORY):
        raise BuildError(f"{row['name_en']!r}: kind {kind} does not fit serial {serial}")
    return kind


def _entry(row: dict[str, str], key: tuple[int, int], record: TabletRecord, source: str) -> dict:
    return {
        "name_en": row["name_en"],
        "name_jp": row["name_jp"],
        "kind": _check_kind(row, key[1]).value,
        "map_id": key[0],
        "serial": key[1],
        "record_hex": record.identity.hex(),
        "verified": source == SOURCE_SAVE,
        "source": source,
    }


def build(fixtures: Path, upstream: Path, names: Path) -> dict:
    rows = _read_names(names)
    real: dict[tuple[int, int], TabletRecord] = {}
    for path in sorted(fixtures.glob(SAVE_GLOB)):
        for rec in SaveFile.load(path).received.live:
            key = (rec.map_id, rec.serial)
            if key not in rows:
                raise BuildError(f"{path}: record map {key[0]:#x} serial {key[1]} has no name row")
            seen = real.setdefault(key, TabletRecord(rec.identity))
            if seen.identity != rec.identity:
                raise BuildError(
                    f"{path}: map {key[0]:#x} serial {key[1]} differs from another save's record"
                )
    entries = [_entry(rows[key], key, rec, SOURCE_SAVE) for key, rec in real.items()]
    upstream_data = json.loads(upstream.read_text(encoding="utf-8"))
    for item in upstream_data["records"]:
        if item["name"] == UPSTREAM_EMPTY_NAME:
            continue
        rec = TabletRecord(bytes.fromhex(item["record_hex"]))
        key = (rec.map_id, rec.serial)
        if key in real:
            continue
        if key not in rows:
            LOG.warning("upstream %r (map %#x serial %d) has no name row", item["name"], *key)
            continue
        entries.append(_entry(rows[key], key, TabletRecord(rec.identity), SOURCE_UPSTREAM))
    covered = {(e["map_id"], e["serial"]) for e in entries}
    for key, row in rows.items():
        if key not in covered:
            LOG.warning("%r (map %#x serial %d) has no record", row["name_en"], *key)
    entries.sort(key=lambda e: (e["kind"], e["name_en"]))
    return {"source": SOURCE_NOTE.format(upstream=upstream_data["source"]), "tablets": entries}


def main(argv: list[str]) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(argv) != EXPECTED_ARGS:
        LOG.error("usage: build_tablet_db.py FIXTURES UPSTREAM.json NAMES.csv OUT.json")
        return 2
    try:
        data = build(Path(argv[1]), Path(argv[2]), Path(argv[3]))
    except (BuildError, OSError, KeyError, ValueError) as exc:
        LOG.error("build failed: %s", exc)
        return 1
    Path(argv[4]).write_text(
        json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    verified = sum(1 for e in data["tablets"] if e["verified"])
    LOG.info("%d entries, %d verified", len(data["tablets"]), verified)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
