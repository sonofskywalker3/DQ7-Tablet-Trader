"""First run on Android: All files access, the Azahar folder, and the save opened at start."""

from pathlib import Path

from test_sources import AZAHAR_PATH, fill

from dq7tt.apppaths import AppPaths, Settings, load_settings, save_settings
from dq7tt_gui.model_setup import NOT_AZAHAR, SetupModel, SetupStep, screen_copy, setup_step
from dq7tt_gui.viewmodels import NoticeKind

US_SET = "us_postgame"


def paths_of(tmp_path: Path) -> AppPaths:
    return AppPaths.for_android(tmp_path / "private", tmp_path / "storage" / "DQ7 Tablet Trader")


def azahar_folder(tmp_path: Path) -> tuple[Path, Path]:
    """An Azahar user folder holding a US save; returns (user folder, save folder)."""
    user = tmp_path / "storage" / "Azahar"
    save = fill(user / AZAHAR_PATH.removeprefix("user/"), US_SET)
    return user, save


def test_step_needs_access_first(tmp_path: Path) -> None:
    user, _ = azahar_folder(tmp_path)
    paths = paths_of(tmp_path)
    save_settings(paths, Settings(azahar_dir=user))
    assert SetupModel(paths).step(has_access=False) is SetupStep.NEED_ACCESS
    assert setup_step(False, Settings(azahar_dir=user), None) is SetupStep.NEED_ACCESS


def test_step_needs_folder_when_none_remembered(tmp_path: Path) -> None:
    azahar_folder(tmp_path)
    assert SetupModel(paths_of(tmp_path)).step(has_access=True) is SetupStep.NEED_FOLDER
    assert setup_step(True, Settings(), None) is SetupStep.NEED_FOLDER


def test_step_needs_folder_when_remembered_folder_gone(tmp_path: Path) -> None:
    paths = paths_of(tmp_path)
    save_settings(paths, Settings(azahar_dir=tmp_path / "storage" / "Azahar"))
    model = SetupModel(paths)
    assert model.step(has_access=True) is SetupStep.NEED_FOLDER
    assert model.start_source() is None


def test_folder_picked_good_remembers_and_ready(tmp_path: Path) -> None:
    user, _ = azahar_folder(tmp_path)
    paths = paths_of(tmp_path)
    model = SetupModel(paths)
    assert model.step(has_access=True) is SetupStep.NEED_FOLDER
    assert model.folder_picked(user) is None
    assert load_settings(paths).azahar_dir == user
    assert model.step(has_access=True) is SetupStep.READY
    # A fresh start (a new model) goes straight to the window.
    assert SetupModel(paths).step(has_access=True) is SetupStep.READY


def test_folder_picked_bad_says_so_and_remembers_nothing(tmp_path: Path) -> None:
    azahar_folder(tmp_path)
    downloads = tmp_path / "storage" / "Download"
    downloads.mkdir(parents=True)
    paths = paths_of(tmp_path)
    model = SetupModel(paths)
    notice = model.folder_picked(downloads)
    assert notice is not None and notice.kind is NoticeKind.ERROR
    assert notice.text == (
        "There is no Dragon Quest VII save in that folder. Choose the Azahar folder, usually "
        "called Azahar, in internal storage."
    )
    assert notice.text == NOT_AZAHAR
    assert load_settings(paths).azahar_dir is None
    assert model.step(has_access=True) is SetupStep.NEED_FOLDER


def test_start_source_is_found_save(tmp_path: Path) -> None:
    user, save = azahar_folder(tmp_path)
    paths = paths_of(tmp_path)
    save_settings(paths, Settings(azahar_dir=user))
    model = SetupModel(paths)
    assert model.start_source() is None  # nothing checked yet
    assert model.step(has_access=True) is SetupStep.READY
    assert model.start_source() == save
    # Losing access forgets it: nothing may be opened without access.
    assert model.step(has_access=False) is SetupStep.NEED_ACCESS
    assert model.start_source() is None


def test_screen_copy_has_no_em_dashes() -> None:
    for step in (SetupStep.NEED_ACCESS, SetupStep.NEED_FOLDER):
        copy = screen_copy(step)
        assert "\N{EM DASH}" not in copy.title + copy.body + copy.button
    assert screen_copy(SetupStep.NEED_ACCESS).button == "Allow access"
    assert screen_copy(SetupStep.NEED_FOLDER).button == "Choose folder"
