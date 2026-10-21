import json
import os
import zipfile
from pathlib import Path

import pytest
from test_cli import digest, make_folder
from test_sources import AZAHAR_PATH, fill

import dq7tt.cli_common as cli_common
import dq7tt.folder as folder_module
from dq7tt.apppaths import AppPaths
from dq7tt.bank import BANK_EXTENSION, Bank
from dq7tt.cli import main
from dq7tt.cli_common import label
from dq7tt.constants import SAVE_FILENAMES
from dq7tt.database import TabletDatabase
from dq7tt.savefile import SaveFile, SlotRole
from dq7tt.session import Session
from dq7tt.validate import Problem, Severity

SET = "us_superkiefer"


def bank_of(tmp_path: Path) -> Bank:
    return Bank(AppPaths.under(tmp_path / "app").bank_dir)


def run(tmp_path: Path, *argv: str) -> int:
    return main(["--app-dir", str(tmp_path / "app"), *argv])


def test_list_accepts_a_zip(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    folder = make_folder(tmp_path, "us", SET)
    archive = tmp_path / "backup.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for name in SAVE_FILENAMES:
            z.write(folder / name, name)
    assert run(tmp_path, "list", str(archive)) == 0
    assert "Adventure log 1" in capsys.readouterr().out


def test_add_to_single_file_writes_sibling_bin(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "pal", "pal_superkiefer")
    single = tmp_path / "solo" / "save003.bin"
    single.parent.mkdir()
    single.write_bytes((folder / "save003.bin").read_bytes())
    before = single.read_bytes()
    argv = ["add", str(single), "--log", "3", "--tablet", "Mount Oddna"]
    assert run(tmp_path, *argv) == 0
    assert single.read_bytes() == before
    (new,) = [p for p in single.parent.iterdir() if p != single]
    assert new.suffix == ".bin"
    assert SaveFile.load(new).received.count == SaveFile.load(single).received.count + 1


def test_azahar_source_output_lands_under_edited_folder(tmp_path: Path) -> None:
    save_dir = fill(tmp_path / AZAHAR_PATH, "pal_superkiefer")
    before = digest(save_dir)
    assert run(tmp_path, "add", str(save_dir), "--log", "3", "--tablet", "Mount Oddna") == 0
    assert digest(save_dir) == before
    (written,) = list(AppPaths.under(tmp_path / "app").edited_dir.iterdir())
    assert SaveFile.load(written / "save003.bin").received.count == 10
    assert list((tmp_path / "app" / "data" / "backups").glob("*.zip"))


def test_backup_is_taken_before_writing_with_out(tmp_path: Path) -> None:
    src = make_folder(tmp_path, "pal", "pal_superkiefer")
    out = tmp_path / "result"
    argv = ["add", str(src), "--log", "3", "--tablet", "Mount Oddna", "--out", str(out)]
    assert run(tmp_path, *argv) == 0
    (backup,) = (tmp_path / "app" / "data" / "backups").glob("*.zip")
    assert "save003.bin" in zipfile.ZipFile(backup).namelist()


def test_warnings_print_before_the_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    warning = Problem(Severity.WARNING, "x", "Careful now")
    monkeypatch.setattr(
        Session, "problems", lambda self, sid: {r: [warning] for r in self.sources()[sid].edited}
    )
    src = make_folder(tmp_path, "pal", "pal_superkiefer")
    assert run(tmp_path, "add", str(src), "--log", "3", "--tablet", "Mount Oddna") == 0
    text = capsys.readouterr().out
    assert text.index("Warning: Careful now") < text.index("Wrote ")


def build_world(tmp_path: Path) -> Path:
    fill(tmp_path / "world" / AZAHAR_PATH.removeprefix("user/"), SET)
    fill(tmp_path / "world/3ds/Checkpoint/saves/0x18EF0 DRAGON QUEST VII/slot1", SET)
    return tmp_path / "world"


def test_scan_prints_one_line_per_source(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world = build_world(tmp_path)
    assert run(tmp_path, "scan", str(world)) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    print("\n".join(lines))
    assert len(lines) == 2
    assert any("Azahar save (US)" in line for line in lines)
    assert all("Adventure log 1" in line and "24/24" in line for line in lines)


def test_scan_with_nothing_found(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "empty").mkdir()
    assert run(tmp_path, "scan", str(tmp_path / "empty")) == 0
    assert "No Dragon Quest VII saves found" in capsys.readouterr().out


def test_bank_import_list_export_add(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = make_folder(tmp_path, "us", SET)
    assert run(tmp_path, "bank", "import", str(src), "--log", "1", "--folder", "Mine") == 0
    assert "24" in capsys.readouterr().out
    bank = bank_of(tmp_path)
    assert bank.folders() == ["Mine"]
    assert len(bank.list("Mine")) == 24

    assert run(tmp_path, "bank", "list", "Mine") == 0
    assert "Metal Medley" in capsys.readouterr().out

    assert run(tmp_path, "bank", "list") == 0
    listing = capsys.readouterr().out
    print(listing)
    assert "Mine" in listing and "Metal Medley" in listing

    assert run(tmp_path, "bank", "export", str(src), "--log", "1", "--slot", "1") == 0
    assert BANK_EXTENSION in capsys.readouterr().out
    assert len(bank.list("")) == 1


def test_bank_add_by_name_inside_the_bank(tmp_path: Path) -> None:
    bank = bank_of(tmp_path)
    db = TabletDatabase.load()
    pal = make_folder(tmp_path, "pal", "pal_superkiefer")
    path = bank.add(db.by_name("Mount Oddna").record, "", db, "test", "US", True)
    out = tmp_path / "result"
    argv = ["bank", "add", str(pal), "--log", "3", "--file", path.name, "--out", str(out)]
    assert run(tmp_path, *argv) == 0
    assert SaveFile.load(out / "save003.bin").received.count == 10


def test_bank_add_refuses_a_corrupt_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pal = make_folder(tmp_path, "pal", "pal_superkiefer")
    bad = tmp_path / f"bad{BANK_EXTENSION}"
    bad.write_text(json.dumps({"format": 99}))
    argv = ["bank", "add", str(pal), "--log", "3", "--file", str(bad)]
    assert run(tmp_path, *argv) == 2
    assert "Refused" in capsys.readouterr().out
    assert [p.name for p in tmp_path.iterdir() if "edited" in p.name] == []


def test_bank_export_slot_out_of_range(tmp_path: Path) -> None:
    src = make_folder(tmp_path, "us", SET)
    assert run(tmp_path, "bank", "export", str(src), "--log", "3", "--slot", "99") == 2


def test_azahar_put(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    target = fill(tmp_path / AZAHAR_PATH)
    (target / "system.bin").write_bytes(b"old system")
    edited = make_folder(tmp_path, "edited", SET)
    assert run(tmp_path, "azahar", "put", str(edited), str(target)) == 0
    text = capsys.readouterr().out.strip()
    assert Path(text).suffix == ".zip" and Path(text).is_file()
    assert (target / "save001.bin").read_bytes() == (edited / "save001.bin").read_bytes()


def test_azahar_put_refuses_non_azahar(tmp_path: Path) -> None:
    edited = make_folder(tmp_path, "edited", "us_postgame")
    plain = make_folder(tmp_path, "plain", SET)
    assert run(tmp_path, "azahar", "put", str(edited), str(plain)) == 2


def test_default_app_dir_is_used_without_the_option(tmp_path: Path) -> None:
    src = make_folder(tmp_path, "pal", "pal_superkiefer")
    assert main(["add", str(src), "--log", "3", "--tablet", "Mount Oddna"]) == 0
    assert os.path.isdir(AppPaths.default().backups_dir)


def backups(tmp_path: Path) -> list[Path]:
    return list((tmp_path / "app" / "data" / "backups").glob("*.zip"))


def test_out_inside_input_leaves_no_backup(tmp_path: Path) -> None:
    src = make_folder(tmp_path, "pal", "pal_superkiefer")
    before = digest(src)
    argv = ["add", str(src), "--log", "3", "--tablet", "Mount Oddna", "--out", str(src / "x")]
    assert run(tmp_path, *argv) == 2
    assert digest(src) == before
    assert backups(tmp_path) == []


def test_out_that_exists_leaves_no_backup(tmp_path: Path) -> None:
    src = make_folder(tmp_path, "pal", "pal_superkiefer")
    taken = tmp_path / "taken"
    taken.mkdir()
    argv = ["add", str(src), "--log", "3", "--tablet", "Mount Oddna", "--out", str(taken)]
    assert run(tmp_path, *argv) == 2
    assert backups(tmp_path) == []


def test_out_with_single_file_is_refused(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "pal", "pal_superkiefer")
    single = tmp_path / "solo.bin"
    single.write_bytes((folder / "save003.bin").read_bytes())
    argv = ["add", str(single), "--log", "3", "--tablet", "Mount Oddna"]
    assert run(tmp_path, *argv, "--out", str(tmp_path / "res")) == 2
    assert backups(tmp_path) == []
    assert not (tmp_path / "res").exists()


def test_scan_skips_a_save_it_cannot_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    world = build_world(tmp_path)
    real_load = SaveFile.load

    def locked(path: Path) -> SaveFile:
        if "Checkpoint" in str(path):
            raise PermissionError(13, "Permission denied")
        return real_load(path)

    monkeypatch.setattr(folder_module.SaveFile, "load", staticmethod(locked))
    assert run(tmp_path, "scan", str(world)) == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert len(lines) == 1 and "Azahar save (US)" in lines[0]


def test_role_labels_come_from_the_core_names() -> None:
    assert label(SlotRole.QUICK_SAVE) == "Quick save"
    assert [label(r) for r in (SlotRole.LOG_1, SlotRole.LOG_2, SlotRole.LOG_3)] == [
        "Adventure log 1",
        "Adventure log 2",
        "Adventure log 3",
    ]
    assert not hasattr(cli_common, "ROLE_LABELS")


def test_bank_import_marks_save_tablets_real(tmp_path: Path) -> None:
    src = make_folder(tmp_path, "us", SET)
    assert run(tmp_path, "bank", "import", str(src), "--log", "1") == 0
    assert all(t.from_real_save for t in bank_of(tmp_path).list(""))
