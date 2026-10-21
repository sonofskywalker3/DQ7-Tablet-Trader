import importlib.util
import json
import shutil
from pathlib import Path

import pytest
from conftest import ALL_SAVES, FIXTURES

from dq7tt.constants import RECEIVED_OFFSET
from dq7tt.database import TabletDatabase, describe
from dq7tt.errors import UnknownTabletError
from dq7tt.savefile import SaveFile
from dq7tt.tablets import TabletKind, TabletRecord

ROOT = Path(__file__).parent.parent
EXPECTED_VERIFIED = 62
MAP_MAGIC = 0x126
MAP_MENAGERIE = 0x127
UNKNOWN_MAP = 0x0FFF
STORY_SERIALS = (0x46, 0x47, 0x48)
STREETPASS_BYTE = 1


@pytest.fixture(scope="module")
def db() -> TabletDatabase:
    return TabletDatabase.load()


def _blank(map_id: int, serial: int, first: int = 0) -> TabletRecord:
    raw = bytearray(0x54)
    raw[0x00] = first
    raw[0x0C:0x0E] = map_id.to_bytes(2, "little")
    raw[0x50] = serial
    return TabletRecord(bytes(raw))


def test_every_fixture_record_is_known(db: TabletDatabase) -> None:
    seen = 0
    for path in ALL_SAVES:
        for rec in SaveFile.load(path).received.live:
            info = db.lookup(rec)
            assert info is not None, (path, rec.map_id, rec.serial)
            assert info.verified
            assert info.record.identity == rec.identity
            seen += 1
    assert seen > 0


def test_counts(db: TabletDatabase) -> None:
    verified = [t for t in db.all() if t.verified]
    assert len(verified) == EXPECTED_VERIFIED
    assert len(db.all()) >= EXPECTED_VERIFIED
    names = [t.name_en.lower() for t in db.all()]
    assert len(names) == len(set(names))


def test_shared_map_ids_have_distinct_names(db: TabletDatabase) -> None:
    magic = {t.name_en for t in db.all() if t.map_id == MAP_MAGIC}
    menagerie = {t.name_en for t in db.all() if t.map_id == MAP_MENAGERIE}
    assert magic == {"Magic Moments", "A Kind of Magic"}
    assert menagerie == {"Monstrous Menagerie", "A Beastly Treat"}


def test_story_kind(db: TabletDatabase) -> None:
    for serial in STORY_SERIALS:
        matches = [t for t in db.all() if t.serial == serial]
        assert len(matches) == 1
        assert matches[0].kind == TabletKind.STORY


def test_upstream_entries_not_insertable(db: TabletDatabase) -> None:
    insertable = db.insertable()
    assert all(t.verified for t in insertable)
    assert not any(not t.verified for t in insertable)
    assert len(insertable) == EXPECTED_VERIFIED


def test_describe_unknown(db: TabletDatabase) -> None:
    name, kind = describe(_blank(UNKNOWN_MAP, 0), db)
    assert name.startswith("Unknown tablet")
    assert kind == TabletKind.UNKNOWN
    name, kind = describe(_blank(UNKNOWN_MAP, 0, first=STREETPASS_BYTE), db)
    assert name == "StreetPass tablet"
    assert kind == TabletKind.STREETPASS


def test_describe_known(db: TabletDatabase) -> None:
    info = db.by_name("magic moments")
    assert describe(info.record, db) == ("Magic Moments", TabletKind.DLC)


def test_by_name_unknown_raises(db: TabletDatabase) -> None:
    with pytest.raises(UnknownTabletError):
        db.by_name("No Such Tablet")


def test_lookup_by_map_and_serial(db: TabletDatabase) -> None:
    info = db.by_name("Slimetree Forest")
    variant = bytearray(info.record.raw)
    variant[0x16] ^= 0xFF
    found = db.lookup(TabletRecord(bytes(variant)))
    assert found is not None
    assert found.name_en == "Slimetree Forest"
    assert found.record.identity != TabletRecord(bytes(variant)).identity


def test_all_sorted_by_kind_then_name(db: TabletDatabase) -> None:
    keys = [(t.kind.value, t.name_en) for t in db.all()]
    assert keys == sorted(keys)


def test_db_build_is_reproducible() -> None:
    spec = importlib.util.spec_from_file_location(
        "build_tablet_db", ROOT / "tools" / "build_tablet_db.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    built = module.build(
        FIXTURES,
        ROOT / "dq7tt" / "data" / "upstream_records.json",
        ROOT / "tools" / "tablet_names.csv",
    )
    committed = json.loads((ROOT / "dq7tt" / "data" / "tablets.json").read_text(encoding="utf-8"))
    assert built == committed


def _load_build_module():
    spec = importlib.util.spec_from_file_location(
        "build_tablet_db", ROOT / "tools" / "build_tablet_db.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_db_build_rejects_conflicting_records(tmp_path: Path) -> None:
    module = _load_build_module()
    source = FIXTURES / "us_postgame" / "save000.bin"
    for name in ("a", "b"):
        (tmp_path / name).mkdir()
        shutil.copy(source, tmp_path / name / "save000.bin")
    data = bytearray(source.read_bytes())
    data[RECEIVED_OFFSET + 0x20] ^= 0x01  # same map and serial as slot 0, different bytes
    (tmp_path / "b" / "save000.bin").write_bytes(bytes(data))
    with pytest.raises(module.BuildError):
        module.build(
            tmp_path,
            ROOT / "dq7tt" / "data" / "upstream_records.json",
            ROOT / "tools" / "tablet_names.csv",
        )
