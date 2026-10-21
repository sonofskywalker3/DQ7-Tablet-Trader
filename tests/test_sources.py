import os
import stat
import struct
import zipfile
from pathlib import Path

import pytest
from conftest import load_fixture

from dq7tt.constants import SAVE_FILENAMES, SAVE_SIZE, SURE_OFFSET
from dq7tt.errors import JapaneseSaveError, UnsupportedSourceError
from dq7tt.sources import Region, SourceKind, open_source

SIZE_FIELD = 8
JP_SURE_SIZE = 0xD58
FIXTURE_SET = "us_postgame"
ZEROS = "0" * 32
AZAHAR_PATH = f"user/sdmc/Nintendo 3DS/{ZEROS}/{ZEROS}/title/00040000/0018ef00/data/00000001"


def fill(folder: Path, set_name: str = FIXTURE_SET) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for slot, name in enumerate(SAVE_FILENAMES):
        (folder / name).write_bytes(load_fixture(set_name, slot))
    return folder


def japanese_bytes() -> bytes:
    data = bytearray(load_fixture(FIXTURE_SET, 0))
    struct.pack_into("<I", data, SURE_OFFSET + SIZE_FIELD, JP_SURE_SIZE)
    return bytes(data)


def make_zip(path: Path, entries: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return path


def snapshot(root: Path) -> set[Path]:
    """Every path under root."""
    return set(root.rglob("*"))


def test_checkpoint(tmp_path: Path) -> None:
    folder = fill(tmp_path / "sd/3ds/Checkpoint/saves/0x18EF0 DRAGON QUEST VII/20261020-101500")
    src = open_source(folder, tmp_path / "work")
    assert src.kind is SourceKind.CHECKPOINT
    assert src.region is Region.US
    assert src.save_dir == folder
    assert src.label == "Checkpoint backup 20261020-101500 (US)"


def test_checkpoint_other_regions_and_unknown(tmp_path: Path) -> None:
    eu = fill(tmp_path / "a/3ds/Checkpoint/saves/0x18F00 DQ7/x")
    assert open_source(eu, tmp_path / "w").region is Region.EU
    jp = fill(tmp_path / "b/3ds/Checkpoint/saves/0x065E0 DQ7/x")
    assert open_source(jp, tmp_path / "w").region is Region.JP
    unk = fill(tmp_path / "c/3ds/Checkpoint/saves/Some Game/x")
    src = open_source(unk, tmp_path / "w")
    assert src.kind is SourceKind.CHECKPOINT
    assert src.region is Region.UNKNOWN


def test_jksm(tmp_path: Path) -> None:
    folder = fill(tmp_path / "sd/JKSM/User Saves/DRAGON QUEST VII/backup1")
    src = open_source(folder, tmp_path / "work")
    assert src.kind is SourceKind.JKSM
    assert src.region is Region.UNKNOWN
    assert src.label == "JKSM backup backup1"


def test_azahar(tmp_path: Path) -> None:
    folder = fill(tmp_path / AZAHAR_PATH)
    src = open_source(folder, tmp_path / "work")
    assert src.kind is SourceKind.AZAHAR
    assert src.region is Region.US
    assert src.label == "Azahar save (US)"


def test_plain_folder(tmp_path: Path) -> None:
    folder = fill(tmp_path / "My saves")
    src = open_source(folder, tmp_path / "work")
    assert (src.kind, src.region, src.label) == (
        SourceKind.FOLDER,
        Region.UNKNOWN,
        "Folder: My saves",
    )


def test_single_file(tmp_path: Path) -> None:
    folder = tmp_path / "loose"
    folder.mkdir()
    (folder / "save002.bin").write_bytes(load_fixture(FIXTURE_SET, 2))
    src = open_source(folder / "save002.bin", tmp_path / "work")
    assert src.kind is SourceKind.FILE
    assert src.save_dir == folder
    assert src.label == "File: save002.bin"


def test_zip_extracts_into_work_dir(tmp_path: Path) -> None:
    entries = {f"inner/{n}": load_fixture(FIXTURE_SET, i) for i, n in enumerate(SAVE_FILENAMES)}
    archive = make_zip(tmp_path / "DRAGON QUEST 7 PRESERVED.zip", entries)
    work = tmp_path / "work"
    src = open_source(archive, work)
    assert src.kind is SourceKind.ZIP
    assert src.label == "Zip: DRAGON QUEST 7 PRESERVED"
    assert work in src.save_dir.parents
    assert (src.save_dir / "save000.bin").read_bytes() == load_fixture(FIXTURE_SET, 0)
    again = open_source(archive, work)
    assert again.save_dir != src.save_dir


def test_empty_folder(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    with pytest.raises(UnsupportedSourceError, match="saves were found in empty"):
        open_source(tmp_path / "empty", tmp_path / "work")


def test_random_files_named_like_saves(tmp_path: Path) -> None:
    folder = tmp_path / "junk"
    folder.mkdir()
    (folder / "save001.bin").write_bytes(os.urandom(SAVE_SIZE))
    with pytest.raises(UnsupportedSourceError):
        open_source(folder, tmp_path / "work")


def test_zip_of_text_file(tmp_path: Path) -> None:
    archive = make_zip(tmp_path / "t.zip", {"readme.txt": b"hello"})
    with pytest.raises(UnsupportedSourceError):
        open_source(archive, tmp_path / "work")


def test_not_a_zip(tmp_path: Path) -> None:
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    with pytest.raises(UnsupportedSourceError):
        open_source(bad, tmp_path / "work")


@pytest.mark.parametrize("name", ["notes.txt", "save001.bin"])
def test_non_save_single_file(tmp_path: Path, name: str) -> None:
    target = tmp_path / name
    target.write_bytes(b"hello")
    with pytest.raises(UnsupportedSourceError):
        open_source(target, tmp_path / "work")


def test_missing_path(tmp_path: Path) -> None:
    with pytest.raises(UnsupportedSourceError):
        open_source(tmp_path / "nope", tmp_path / "work")


UNSAFE_NAMES = [
    "../evil",
    "/abs/evil",
    "C:/evil",
    "a/../../evil",
    "..\\evil",
    "a/C:evil",
    "a/C:/evil",
    "a/b:ads",
    "a/NUL.txt",
    "a/com1",
    "a/x.",
]


@pytest.mark.parametrize("name", UNSAFE_NAMES)
def test_zip_path_traversal_refused(tmp_path: Path, name: str) -> None:
    entries = {"save000.bin": load_fixture(FIXTURE_SET, 0), name: b"x"}
    archive = make_zip(tmp_path / "evil.zip", entries)
    work = tmp_path / "work"
    before = snapshot(tmp_path)
    with pytest.raises(UnsupportedSourceError):
        open_source(archive, work)
    assert snapshot(tmp_path) - {work} == before
    assert not work.exists() or not any(work.iterdir())


def test_zip_too_many_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dq7tt.sources.MAX_ZIP_ENTRIES", 2)
    archive = make_zip(tmp_path / "many.zip", {"a": b"1", "b": b"2", "c": b"3"})
    with pytest.raises(UnsupportedSourceError):
        open_source(archive, tmp_path / "work")


def test_zip_too_large(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("dq7tt.sources.MAX_ZIP_BYTES", 10)
    archive = make_zip(tmp_path / "big.zip", {"a": b"x" * 100})
    with pytest.raises(UnsupportedSourceError):
        open_source(archive, tmp_path / "work")


def test_japanese_folder_reraises(tmp_path: Path) -> None:
    folder = tmp_path / "jp"
    folder.mkdir()
    for name in SAVE_FILENAMES:
        (folder / name).write_bytes(japanese_bytes())
    with pytest.raises(JapaneseSaveError):
        open_source(folder, tmp_path / "work")


def test_mixed_japanese_and_western_is_ok(tmp_path: Path) -> None:
    folder = fill(tmp_path / "mix")
    (folder / "save001.bin").write_bytes(japanese_bytes())
    assert open_source(folder, tmp_path / "work").kind is SourceKind.FOLDER


def test_japanese_single_file_reraises(tmp_path: Path) -> None:
    target = tmp_path / "save000.bin"
    target.write_bytes(japanese_bytes())
    with pytest.raises(JapaneseSaveError):
        open_source(target, tmp_path / "work")


@pytest.mark.filterwarnings("ignore:Duplicate name:UserWarning")
def test_zip_duplicate_names_refused(tmp_path: Path) -> None:
    archive = tmp_path / "dup.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("a", b"1")
        z.writestr("a", b"2")
    work = tmp_path / "work"
    with pytest.raises(UnsupportedSourceError):
        open_source(archive, work)


def test_zip_file_and_folder_clash_refused(tmp_path: Path) -> None:
    archive = make_zip(tmp_path / "clash.zip", {"a": b"1", "a/b": b"2"})
    with pytest.raises(UnsupportedSourceError):
        open_source(archive, tmp_path / "work")


def test_zip_failure_removes_extraction_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("dq7tt.sources.MAX_ZIP_BYTES", 120)
    archive = make_zip(tmp_path / "x.zip", {"a": b"x" * 100, "b": b"y" * 40})
    work = tmp_path / "work"
    monkeypatch.setattr("dq7tt.sources._check_zip", lambda a: a.infolist())
    with pytest.raises(UnsupportedSourceError):
        open_source(archive, work)
    assert not any(work.iterdir())


def test_save_names_matched_case_insensitively(tmp_path: Path) -> None:
    folder = tmp_path / "caps"
    folder.mkdir()
    (folder / "SAVE000.BIN").write_bytes(load_fixture(FIXTURE_SET, 0))
    assert open_source(folder, tmp_path / "work").kind is SourceKind.FOLDER


def test_zip_empty_parts_member_refused(tmp_path: Path) -> None:
    archive = make_zip(
        tmp_path / "dot.zip", {"save000.bin": load_fixture(FIXTURE_SET, 0), ".": b"x"}
    )
    work = tmp_path / "work"
    before = snapshot(tmp_path)
    with pytest.raises(UnsupportedSourceError):
        open_source(archive, work)
    assert snapshot(tmp_path) - {work} == before
    assert not work.exists() or not any(work.iterdir())


def test_zip_symlink_member_skipped(tmp_path: Path) -> None:
    archive = tmp_path / "link.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("save000.bin", load_fixture(FIXTURE_SET, 0))
        link = zipfile.ZipInfo("inner/link")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        z.writestr(link, "save000.bin")
    src = open_source(archive, tmp_path / "work")
    assert (src.save_dir / "save000.bin").is_file()
    assert not (src.save_dir / "inner").exists()
    assert not any(p.name == "link" for p in src.save_dir.rglob("*"))


def test_zip_without_saves_leaves_nothing_in_work_dir(tmp_path: Path) -> None:
    work = tmp_path / "work"
    plain = make_zip(tmp_path / "t.zip", {"inner/readme.txt": b"hello"})
    with pytest.raises(UnsupportedSourceError):
        open_source(plain, work)
    assert not any(work.iterdir())
    jp = make_zip(tmp_path / "jp.zip", {f"jp/{n}": japanese_bytes() for n in SAVE_FILENAMES})
    with pytest.raises(JapaneseSaveError):
        open_source(jp, work)
    assert not any(work.iterdir())
