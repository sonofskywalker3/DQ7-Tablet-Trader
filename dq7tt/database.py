"""Catalogue of every tablet the tool can name, and which of them can be inserted."""

import json
from dataclasses import dataclass
from importlib import resources

from dq7tt.errors import UnknownTabletError
from dq7tt.tablets import TabletKind, TabletRecord

DATA_PACKAGE = "dq7tt.data"
DATA_FILE = "tablets.json"
STREETPASS_NAME = "StreetPass tablet"


@dataclass(frozen=True)
class TabletInfo:
    name_en: str
    name_jp: str
    kind: TabletKind
    map_id: int
    serial: int
    record: TabletRecord
    verified: bool


class TabletDatabase:
    def __init__(self, tablets: tuple[TabletInfo, ...]) -> None:
        self._tablets = tuple(sorted(tablets, key=lambda t: (t.kind.value, t.name_en)))
        self._by_identity = {t.record.identity: t for t in self._tablets}
        self._by_key = {(t.map_id, t.serial): t for t in self._tablets}
        self._by_name = {t.name_en.lower(): t for t in self._tablets}

    @classmethod
    def load(cls) -> "TabletDatabase":
        text = resources.files(DATA_PACKAGE).joinpath(DATA_FILE).read_text(encoding="utf-8")
        tablets = tuple(
            TabletInfo(
                name_en=e["name_en"],
                name_jp=e["name_jp"],
                kind=TabletKind(e["kind"]),
                map_id=e["map_id"],
                serial=e["serial"],
                record=TabletRecord(bytes.fromhex(e["record_hex"])),
                verified=e["verified"],
            )
            for e in json.loads(text)["tablets"]
        )
        return cls(tablets)

    def lookup(self, record: TabletRecord) -> TabletInfo | None:
        exact = self._by_identity.get(record.identity)
        if exact is not None:
            return exact
        if record.looks_streetpass:
            return None
        return self._by_key.get((record.map_id, record.serial))

    def by_name(self, name_en: str) -> TabletInfo:
        try:
            return self._by_name[name_en.lower()]
        except KeyError:
            raise UnknownTabletError(f"no tablet named {name_en!r}") from None

    def all(self) -> tuple[TabletInfo, ...]:
        return self._tablets

    def insertable(self) -> tuple[TabletInfo, ...]:
        return tuple(t for t in self._tablets if t.verified)


def describe(record: TabletRecord, db: TabletDatabase) -> tuple[str, TabletKind]:
    if record.looks_streetpass:
        return STREETPASS_NAME, TabletKind.STREETPASS
    info = db.lookup(record)
    if info is None:
        return f"Unknown tablet (map {record.map_id:#05x})", TabletKind.UNKNOWN
    return info.name_en, info.kind
