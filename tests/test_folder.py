import hashlib
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from dq7tt.errors import OutputExistsError, UnsupportedLayoutError
from dq7tt.folder import SaveFolder, default_output_path, write_edited
from dq7tt.savefile import SlotRole
from tests.conftest import FIXTURES


def make_folder(tmp_path: Path, name: str = "us", set_name: str = "us_superkiefer") -> Path:
    dst = tmp_path / name
    shutil.copytree(FIXTURES / set_name, dst)
    (dst / "system.bin").write_bytes(b"system data")
    (dst / "cardinfo.bin").write_bytes(b"card data")
    return dst


def digest(folder: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


def test_open_loads_four_roles(tmp_path: Path) -> None:
    folder = SaveFolder.open(make_folder(tmp_path))
    assert set(folder.files) == {
        SlotRole.QUICK_SAVE,
        SlotRole.LOG_1,
        SlotRole.LOG_2,
        SlotRole.LOG_3,
    }


def test_open_folder_without_saves_raises(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    (tmp_path / "empty" / "notes.txt").write_text("hi")
    with pytest.raises(UnsupportedLayoutError):
        SaveFolder.open(tmp_path / "empty")


def test_open_skips_bad_files_but_keeps_good(tmp_path: Path) -> None:
    src = make_folder(tmp_path)
    (src / "save002.bin").write_bytes(b"not a save")
    folder = SaveFolder.open(src)
    assert SlotRole.LOG_2 not in folder.files
    assert SlotRole.LOG_1 in folder.files


def test_default_output_path_is_sibling_with_timestamp(tmp_path: Path) -> None:
    out = default_output_path(tmp_path / "backup", datetime(2026, 10, 21, 13, 5, 9))
    assert out == tmp_path / "backup edited 20261021-130509"


def test_write_edited_copies_everything_and_replaces_edits(tmp_path: Path) -> None:
    src = make_folder(tmp_path)
    before = digest(src)
    log1 = SaveFolder.open(src).files[SlotRole.LOG_1]
    edited = log1.with_received(log1.received.remove(0))
    out = tmp_path / "out"
    write_edited(src, out, {SlotRole.LOG_1: edited})
    assert digest(src) == before
    after = digest(out)
    assert (out / "save001.bin").read_bytes() == edited.to_bytes()
    assert after["save001.bin"] != before["save001.bin"]
    for name in before:
        if name != "save001.bin":
            assert after[name] == before[name]
    assert set(after) == set(before)


def test_write_edited_refuses_existing_output(tmp_path: Path) -> None:
    src = make_folder(tmp_path)
    (tmp_path / "out").mkdir()
    with pytest.raises(OutputExistsError):
        write_edited(src, tmp_path / "out", {})


def test_write_edited_refuses_output_equal_or_inside_input(tmp_path: Path) -> None:
    src = make_folder(tmp_path)
    with pytest.raises(OutputExistsError):
        write_edited(src, src, {})
    with pytest.raises(OutputExistsError):
        write_edited(src, src / "inner", {})
    assert not (src / "inner").exists()


def test_write_edited_refuses_output_inside_protected_folder(tmp_path: Path) -> None:
    src = make_folder(tmp_path, "a")
    other = make_folder(tmp_path, "b")
    with pytest.raises(OutputExistsError):
        write_edited(src, other / "x", {}, protect=[other])
    assert not (other / "x").exists()
    assert [p.name for p in tmp_path.iterdir()] == ["a", "b"]


def test_failed_write_leaves_no_output_or_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = make_folder(tmp_path)
    log1 = SaveFolder.open(src).files[SlotRole.LOG_1]

    def boom(*_args: object, **_kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr("dq7tt.folder.os.replace", boom)
    with pytest.raises(OSError):
        write_edited(src, tmp_path / "out", {SlotRole.LOG_1: log1})
    assert [p.name for p in tmp_path.iterdir()] == ["us"]
