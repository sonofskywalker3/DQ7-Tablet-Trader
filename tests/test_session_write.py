import zipfile
from pathlib import Path

import pytest
from conftest import load_fixture
from test_session import (
    CHECKPOINT_PATH,
    DB,
    ODDNA,
    OTHER_CHECKPOINT_PATH,
    SECOND_SET,
    edited,
    names,
    new_session,
    opened,
    tree_bytes,
)
from test_sources import AZAHAR_PATH, fill

import dq7tt.session_core as session_module
from dq7tt.apppaths import AppPaths
from dq7tt.constants import CHECKSUM_OFFSET, SAVE_FILENAMES
from dq7tt.database import TabletDatabase
from dq7tt.errors import SaveIOError, SessionError, ValidationError
from dq7tt.savefile import SlotRole
from dq7tt.session import Target
from dq7tt.validate import Severity


def test_write_makes_output_and_backup_and_resets_history(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    folder = tmp_path / CHECKPOINT_PATH
    before = tree_bytes(folder)
    session.add_from_database(Target(sid, SlotRole.LOG_3), ODDNA)
    expected = edited(session, sid, SlotRole.LOG_3).to_bytes()
    out = session.write(sid)
    assert out.parent == folder.parent
    assert (out / SAVE_FILENAMES[3]).read_bytes() == expected
    assert (out / SAVE_FILENAMES[1]).read_bytes() == before[SAVE_FILENAMES[1]]
    assert tree_bytes(folder) == before
    backups = list(AppPaths.under(tmp_path / "app").backups_dir.iterdir())
    assert len(backups) == 1
    assert not session.is_dirty(sid)
    assert not session.can_undo and not session.can_redo
    assert session.sources()[sid].original[SlotRole.LOG_3].to_bytes() == expected


def test_write_refuses_invalid_state(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    session.add_from_database(Target(sid, SlotRole.LOG_3), ODDNA)
    broken = TabletDatabase(tuple(t for t in DB.all() if t.name_en != ODDNA))
    session._db = broken  # the database no longer knows the tablet
    with pytest.raises(ValidationError):
        session.write(sid)
    assert session.is_dirty(sid)
    assert not (tmp_path / "app" / "data" / "backups").exists()


def test_write_with_other_source_dirty_keeps_history(tmp_path: Path) -> None:
    session = new_session(tmp_path)
    one = session.open(fill(tmp_path / CHECKPOINT_PATH))
    two = session.open(fill(tmp_path / OTHER_CHECKPOINT_PATH, SECOND_SET))
    session.add_from_database(Target(one, SlotRole.LOG_3), ODDNA)
    session.add_from_database(Target(two, SlotRole.LOG_3), ODDNA)
    session.write(one)
    assert not session.is_dirty(one)
    assert session.is_dirty(two)
    assert session.can_undo
    session.undo()
    assert not session.is_dirty(two)
    session.undo()
    assert session.is_dirty(one)
    assert ODDNA not in names(session, one, SlotRole.LOG_3)


def test_close_with_unsaved_edits_is_refused(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    session.add_from_database(Target(sid, SlotRole.LOG_3), ODDNA)
    with pytest.raises(SessionError):
        session.close(sid)
    assert sid in session.sources()
    session.close(sid, force=True)
    assert session.sources() == {}
    assert not session.can_undo
    with pytest.raises(SessionError):
        session.close(sid)


def test_close_drops_only_that_saves_steps(tmp_path: Path) -> None:
    session = new_session(tmp_path)
    one = session.open(fill(tmp_path / CHECKPOINT_PATH))
    two = session.open(fill(tmp_path / OTHER_CHECKPOINT_PATH, SECOND_SET))
    session.add_from_database(Target(one, SlotRole.LOG_3), ODDNA)
    session.add_from_database(Target(two, SlotRole.LOG_3), ODDNA)
    session.close(two, force=True)
    assert session.undo() == "Add Mount Oddna to adventure log 3"
    assert not session.is_dirty(one)
    assert not session.can_undo


def test_unknown_source_and_missing_role(tmp_path: Path) -> None:
    session = new_session(tmp_path)
    folder = tmp_path / "loose"
    folder.mkdir()
    (folder / SAVE_FILENAMES[2]).write_bytes(load_fixture("us_postgame", 2))
    sid = session.open(folder / SAVE_FILENAMES[2])
    assert set(session.sources()[sid].original) == {SlotRole.LOG_2}
    with pytest.raises(SessionError):
        session.remove(Target(sid, SlotRole.LOG_1), 0)
    with pytest.raises(SessionError):
        session.remove(Target(sid + 7, SlotRole.LOG_2), 0)


def test_put_into_azahar_after_write(tmp_path: Path) -> None:
    session = new_session(tmp_path)
    azahar = fill(tmp_path / AZAHAR_PATH)
    sid = session.open(azahar)
    with pytest.raises(SessionError):
        session.put_into_azahar(sid, sid)
    session.add_from_database(Target(sid, SlotRole.LOG_3), ODDNA)
    expected = edited(session, sid, SlotRole.LOG_3).to_bytes()
    out = session.write(sid)
    assert not out.resolve().is_relative_to(azahar.resolve())
    old = (azahar / SAVE_FILENAMES[3]).read_bytes()
    backup = session.put_into_azahar(sid, sid)
    assert (azahar / SAVE_FILENAMES[3]).read_bytes() == expected
    with zipfile.ZipFile(backup) as z:
        assert z.read(SAVE_FILENAMES[3]) == old
    assert not session.is_dirty(sid)


def test_put_into_azahar_from_another_source(tmp_path: Path) -> None:
    session = new_session(tmp_path)
    one = session.open(fill(tmp_path / CHECKPOINT_PATH))
    azahar = fill(tmp_path / AZAHAR_PATH, SECOND_SET)
    az = session.open(azahar)
    with pytest.raises(SessionError):
        session.put_into_azahar(one, one)
    session.add_from_database(Target(one, SlotRole.LOG_3), ODDNA)
    expected = edited(session, one, SlotRole.LOG_3).to_bytes()
    session.write(one)
    session.add_from_database(Target(az, SlotRole.LOG_3), ODDNA)
    with pytest.raises(SessionError):
        session.put_into_azahar(one, az)
    session.undo()
    session.put_into_azahar(one, az)
    assert (azahar / SAVE_FILENAMES[3]).read_bytes() == expected
    assert session.sources()[az].edited[SlotRole.LOG_3].to_bytes() == expected
    assert not session.is_dirty(az)


def test_write_with_no_changes_is_refused(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    folder = tmp_path / CHECKPOINT_PATH
    with pytest.raises(SessionError, match="There are no changes to write."):
        session.write(sid)
    assert not (tmp_path / "app" / "data" / "backups").exists()
    assert [p.name for p in folder.parent.iterdir()] == [folder.name]
    assert session.last_output(sid) is None


def test_untouched_role_with_bad_checksum_does_not_block_write(tmp_path: Path) -> None:
    folder = fill(tmp_path / CHECKPOINT_PATH)
    quick = folder / SAVE_FILENAMES[0]
    data = bytearray(quick.read_bytes())
    data[CHECKSUM_OFFSET] ^= 1
    quick.write_bytes(bytes(data))
    session = new_session(tmp_path)
    sid = session.open(folder)
    found = session.problems(sid)
    assert set(found) == {SlotRole.QUICK_SAVE, SlotRole.LOG_1, SlotRole.LOG_2, SlotRole.LOG_3}
    assert any(p.code == "CHECKSUM" for p in found[SlotRole.QUICK_SAVE])
    assert all(p.severity is Severity.WARNING for p in found[SlotRole.QUICK_SAVE])
    session.add_from_database(Target(sid, SlotRole.LOG_3), ODDNA)
    assert session.dirty_roles(sid) == {SlotRole.LOG_3}
    out = session.write(sid)
    assert session.last_output(sid) == out
    assert (out / SAVE_FILENAMES[0]).read_bytes() == bytes(data)
    assert (out / SAVE_FILENAMES[3]).read_bytes() == edited(session, sid, SlotRole.LOG_3).to_bytes()


def test_put_into_azahar_refused_while_source_has_newer_edits(tmp_path: Path) -> None:
    session = new_session(tmp_path)
    azahar = fill(tmp_path / AZAHAR_PATH)
    sid = session.open(azahar)
    session.add_from_database(Target(sid, SlotRole.LOG_3), ODDNA)
    session.write(sid)
    session.remove(Target(sid, SlotRole.LOG_2), 0)
    before = tree_bytes(azahar)
    with pytest.raises(SessionError, match="Write your latest changes first."):
        session.put_into_azahar(sid, sid)
    assert tree_bytes(azahar) == before


def _zip_of_saves(tmp_path: Path) -> Path:
    folder = fill(tmp_path / "zsrc")
    archive = tmp_path / "saves.zip"
    with zipfile.ZipFile(archive, "w") as z:
        for name in SAVE_FILENAMES:
            z.write(folder / name, name)
    return archive


def test_zip_extraction_removed_on_close(tmp_path: Path) -> None:
    session = new_session(tmp_path)
    work = AppPaths.under(tmp_path / "app").work_dir
    sid = session.open(_zip_of_saves(tmp_path))
    assert list(work.iterdir())
    session.close(sid)
    assert not list(work.iterdir())


def test_zip_extraction_removed_when_open_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(_: object) -> None:
        raise SaveIOError("cannot read")

    monkeypatch.setattr(session_module, "load_saves", broken)
    session = new_session(tmp_path)
    work = AppPaths.under(tmp_path / "app").work_dir
    with pytest.raises(SaveIOError):
        session.open(_zip_of_saves(tmp_path))
    assert not list(work.iterdir())
    assert session.sources() == {}


def test_second_write_keeps_edits_from_the_first(tmp_path: Path) -> None:
    session, sid = opened(tmp_path)
    folder = tmp_path / CHECKPOINT_PATH
    before = tree_bytes(folder)
    session.add_from_database(Target(sid, SlotRole.LOG_3), ODDNA)
    log3 = edited(session, sid, SlotRole.LOG_3).to_bytes()
    session.write(sid)
    session.remove(Target(sid, SlotRole.LOG_1), 0)
    log1 = edited(session, sid, SlotRole.LOG_1).to_bytes()
    second = session.write(sid)
    assert (second / SAVE_FILENAMES[3]).read_bytes() == log3
    assert (second / SAVE_FILENAMES[1]).read_bytes() == log1
    assert (second / SAVE_FILENAMES[2]).read_bytes() == before[SAVE_FILENAMES[2]]
    assert tree_bytes(folder) == before
    assert session.dirty_roles(sid) == set()


def test_write_put_edit_write_put_keeps_every_edit(tmp_path: Path) -> None:
    session = new_session(tmp_path)
    azahar = fill(tmp_path / AZAHAR_PATH)
    sid = session.open(azahar)
    session.add_from_database(Target(sid, SlotRole.LOG_3), ODDNA)
    log3 = edited(session, sid, SlotRole.LOG_3).to_bytes()
    session.write(sid)
    session.put_into_azahar(sid, sid)
    session.remove(Target(sid, SlotRole.LOG_1), 0)
    log1 = edited(session, sid, SlotRole.LOG_1).to_bytes()
    assert session.dirty_roles(sid) == {SlotRole.LOG_1}
    out = session.write(sid)
    assert (out / SAVE_FILENAMES[3]).read_bytes() == log3
    assert (out / SAVE_FILENAMES[1]).read_bytes() == log1
    session.put_into_azahar(sid, sid)
    assert (azahar / SAVE_FILENAMES[3]).read_bytes() == log3
    assert (azahar / SAVE_FILENAMES[1]).read_bytes() == log1


def test_write_after_undoing_past_a_write_matches_the_state(tmp_path: Path) -> None:
    session = new_session(tmp_path)
    one = session.open(fill(tmp_path / CHECKPOINT_PATH))
    two = session.open(fill(tmp_path / OTHER_CHECKPOINT_PATH, SECOND_SET))
    folder = tmp_path / CHECKPOINT_PATH
    before = tree_bytes(folder)
    session.add_from_database(Target(two, SlotRole.LOG_3), ODDNA)
    session.add_from_database(Target(one, SlotRole.LOG_3), ODDNA)
    session.write(one)
    session.undo()
    assert session.is_dirty(one)
    out = session.write(one)
    assert tree_bytes(out) == before
