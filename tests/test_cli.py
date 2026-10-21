import hashlib
import shutil
from pathlib import Path

import pytest

from dq7tt.cli import main
from dq7tt.database import TabletDatabase, describe
from dq7tt.folder import SaveFolder
from dq7tt.savefile import SaveFile, SlotRole
from dq7tt.tablet_list import ReceivedList
from tests.conftest import FIXTURES


def make_folder(tmp_path: Path, name: str, set_name: str) -> Path:
    dst = tmp_path / name
    shutil.copytree(FIXTURES / set_name, dst)
    (dst / "system.bin").write_bytes(b"system data")
    (dst / "cardinfo.bin").write_bytes(b"card data")
    return dst


def digest(folder: Path) -> dict[str, str]:
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(folder.iterdir())}


def others(tmp_path: Path, *known: str) -> list[Path]:
    return [p for p in tmp_path.iterdir() if p.name not in known]


def test_list_shows_names(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = make_folder(tmp_path, "us", "us_superkiefer")
    assert main(["list", str(src)]) == 0
    out = capsys.readouterr().out
    assert "Adventure log 1" in out
    assert "24/24" in out
    assert "Metal Medley" in out


def test_add_writes_new_folder_and_leaves_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    src = make_folder(tmp_path, "pal", "pal_superkiefer")
    before = digest(src)
    out = tmp_path / "result"
    assert main(["add", str(src), "--log", "3", "--tablet", "Mount Oddna", "--out", str(out)]) == 0
    assert str(out) in capsys.readouterr().out
    assert digest(src) == before
    saved = SaveFile.load(out / "save003.bin")
    assert saved.received.count == 10
    assert describe(saved.received.live[0], TabletDatabase.load())[0] == "Mount Oddna"
    assert saved.checksum_ok
    after = digest(out)
    for name in before:
        if name != "save003.bin":
            assert after[name] == before[name]


def test_add_default_output_is_sibling(tmp_path: Path) -> None:
    src = make_folder(tmp_path, "pal", "pal_superkiefer")
    assert main(["add", str(src), "--log", "3", "--tablet", "Mount Oddna"]) == 0
    (new,) = others(tmp_path, "pal")
    assert new.name.startswith("pal edited ")


def test_add_refuses_full_log(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = make_folder(tmp_path, "us", "us_superkiefer")
    assert main(["add", str(src), "--log", "1", "--tablet", "Mount Oddna"]) == 2
    assert "24 tablets" in capsys.readouterr().out
    assert others(tmp_path, "us") == []


def test_add_refuses_duplicate(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = make_folder(tmp_path, "us", "us_superkiefer")
    assert main(["add", str(src), "--log", "3", "--tablet", "Feral Forest"]) == 2
    assert "already" in capsys.readouterr().out
    assert others(tmp_path, "us") == []


def test_add_refuses_unknown_name(tmp_path: Path) -> None:
    src = make_folder(tmp_path, "pal", "pal_superkiefer")
    assert main(["add", str(src), "--log", "3", "--tablet", "No Such Place"]) == 2
    assert others(tmp_path, "pal") == []


CLEARS = 3


def copy_setup(tmp_path: Path) -> tuple[Path, Path, int]:
    """Two folders; slot 0 of the source log has a non-zero clear count."""
    src = make_folder(tmp_path, "us", "us_superkiefer")
    dst = make_folder(tmp_path, "pal", "pal_superkiefer")
    save = SaveFolder.open(src).files[SlotRole.LOG_1]
    lst = save.received
    slots = (lst.live[0].with_clear_count(CLEARS).raw, *lst.slots[1:])
    edited = save.with_received(ReceivedList(slots=slots, count=lst.count))
    (src / "save001.bin").write_bytes(edited.to_bytes())
    return src, dst, 0


def run_copy(src: Path, dst: Path, slot: int, out: Path, *extra: str) -> int:
    argv = ["copy", str(src), "--from-log", "1", "--slot", str(slot + 1)]
    argv += [str(dst), "--to-log", "3", "--out", str(out), *extra]
    return main(argv)


def test_copy_between_folders_preserves_clears(tmp_path: Path) -> None:
    src, dst, slot = copy_setup(tmp_path)
    before = (digest(src), digest(dst))
    record = SaveFolder.open(src).files[SlotRole.LOG_1].received.live[slot]
    out = tmp_path / "result"
    assert run_copy(src, dst, slot, out) == 0
    assert (digest(src), digest(dst)) == before
    saved = SaveFile.load(out / "save003.bin")
    assert saved.received.live[0].identity == record.identity
    assert saved.received.live[0].clear_count == CLEARS == record.clear_count
    assert saved.received.count == 10


def test_copy_reset_clears(tmp_path: Path) -> None:
    src, dst, slot = copy_setup(tmp_path)
    out = tmp_path / "result"
    assert run_copy(src, dst, slot, out, "--reset-clears") == 0
    assert SaveFile.load(out / "save003.bin").received.live[0].clear_count == 0


def test_copy_within_one_folder(tmp_path: Path) -> None:
    folder = make_folder(tmp_path, "us", "us_superkiefer")
    out = tmp_path / "result"
    argv = ["copy", str(folder), "--from-log", "1", "--slot", "1", str(folder)]
    argv += ["--to-log", "quick", "--allow-quick-save", "--out", str(out)]
    assert main(argv) == 0
    assert (out / "system.bin").read_bytes() == b"system data"
    assert SaveFile.load(out / "save000.bin").received.count == 7


def test_remove(tmp_path: Path) -> None:
    src = make_folder(tmp_path, "us", "us_superkiefer")
    out = tmp_path / "result"
    assert main(["remove", str(src), "--log", "1", "--slot", "1", "--out", str(out)]) == 0
    saved = SaveFile.load(out / "save001.bin")
    assert saved.received.count == 23
    assert saved.checksum_ok


def test_remove_slot_out_of_range(tmp_path: Path) -> None:
    src = make_folder(tmp_path, "us", "us_superkiefer")
    assert main(["remove", str(src), "--log", "3", "--slot", "24"]) == 2
    assert others(tmp_path, "us") == []


def test_refuses_output_inside_input(tmp_path: Path) -> None:
    src = make_folder(tmp_path, "pal", "pal_superkiefer")
    before = digest(src)
    argv = ["add", str(src), "--log", "3", "--tablet", "Mount Oddna", "--out", str(src / "x")]
    assert main(argv) == 2
    assert digest(src) == before
    assert not (src / "x").exists()


def test_refuses_existing_output(tmp_path: Path) -> None:
    src = make_folder(tmp_path, "pal", "pal_superkiefer")
    out = tmp_path / "taken"
    out.mkdir()
    (out / "keep.txt").write_text("keep")
    argv = ["add", str(src), "--log", "3", "--tablet", "Mount Oddna", "--out", str(out)]
    assert main(argv) == 2
    assert [p.name for p in out.iterdir()] == ["keep.txt"]


def test_quick_save_needs_flag(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = make_folder(tmp_path, "pal", "pal_superkiefer")
    argv = ["add", str(src), "--log", "quick", "--tablet", "Mount Oddna"]
    assert main(argv) == 2
    assert "--allow-quick-save" in capsys.readouterr().out
    assert others(tmp_path, "pal") == []
    assert main([*argv, "--allow-quick-save"]) == 0


def test_non_save_folder_exits_2(tmp_path: Path) -> None:
    (tmp_path / "empty").mkdir()
    assert main(["list", str(tmp_path / "empty")]) == 2


def test_copy_refuses_output_inside_source_folder(tmp_path: Path) -> None:
    src, dst, slot = copy_setup(tmp_path)
    before = (digest(src), digest(dst))
    assert run_copy(src, dst, slot, src / "x") == 2
    assert (digest(src), digest(dst)) == before
    assert not (src / "x").exists()
    assert sorted(p.name for p in src.iterdir()) == sorted(before[0])


def test_add_refuses_unverified_tablet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    src = make_folder(tmp_path, "pal", "pal_superkiefer")
    assert main(["add", str(src), "--log", "3", "--tablet", "Blimpton"]) == 2
    assert "tested" in capsys.readouterr().out
    assert others(tmp_path, "pal") == []


def test_cli_out_survives_cp1252(monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import sys

    from dq7tt.cli import out

    raw = io.BytesIO()
    wrapper = io.TextIOWrapper(raw, encoding="cp1252", newline=chr(10))
    monkeypatch.setattr(sys, "stdout", wrapper)
    out("Hero \ufffd")
    wrapper.flush()
    assert raw.getvalue() == b"Hero ?\n"
