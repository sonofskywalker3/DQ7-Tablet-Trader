"""Where the app keeps its files, and the small settings file."""

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs

from dq7tt.errors import SaveIOError

logger = logging.getLogger(__name__)

APP_NAME = "DQ7 Tablet Trader"
SETTINGS_FILE = "settings.json"
BANK_FOLDER = "bank"
BACKUPS_FOLDER = "backups"
WORK_FOLDER = "work"
EDITED_FOLDER = "edited"
UNDER_DATA_FOLDER = "data"
KEY_BANK_DIR = "bank_dir"
KEY_LAST_SOURCES = "last_sources"
JSON_INDENT = 2


@dataclass(frozen=True)
class AppPaths:
    """Folders the app uses. Nothing here creates them; writers do that lazily."""

    data_dir: Path
    bank_dir: Path
    backups_dir: Path
    edited_dir: Path
    work_dir: Path

    @classmethod
    def _build(cls, data_dir: Path, edited_dir: Path) -> "AppPaths":
        return cls(
            data_dir=data_dir,
            bank_dir=data_dir / BANK_FOLDER,
            backups_dir=data_dir / BACKUPS_FOLDER,
            edited_dir=edited_dir,
            work_dir=data_dir / WORK_FOLDER,
        )

    @classmethod
    def default(cls) -> "AppPaths":
        data_dir = platformdirs.user_data_path(APP_NAME, appauthor=False)
        edited = platformdirs.user_documents_path() / APP_NAME / EDITED_FOLDER
        return cls._build(data_dir, edited)

    @classmethod
    def under(cls, root: Path) -> "AppPaths":
        return cls._build(root / UNDER_DATA_FOLDER, root / EDITED_FOLDER)


@dataclass
class Settings:
    bank_dir: Path | None = None
    last_sources: list[Path] = field(default_factory=list)


def _settings_file(paths: AppPaths) -> Path:
    return paths.data_dir / SETTINGS_FILE


def load_settings(paths: AppPaths) -> Settings:
    """Read settings; a missing file gives defaults, a corrupt one logs and gives defaults."""
    file = _settings_file(paths)
    try:
        raw = file.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Settings()
    except (OSError, UnicodeDecodeError) as exc:
        logger.warning("Could not read settings file %s: %s", file, exc)
        return Settings()
    try:
        data = json.loads(raw)
        bank = data.get(KEY_BANK_DIR)
        sources = data.get(KEY_LAST_SOURCES, [])
        if (bank is not None and not isinstance(bank, str)) or not isinstance(sources, list):
            raise TypeError("unexpected settings shape")
        return Settings(
            bank_dir=Path(bank) if bank else None,
            last_sources=[Path(s) for s in sources],
        )
    except (ValueError, TypeError, AttributeError) as exc:
        logger.warning("Ignoring corrupt settings file %s: %s", file, exc)
        return Settings()


def save_settings(paths: AppPaths, settings: Settings) -> None:
    """Write settings atomically (temp file in the same folder, then replace)."""
    file = _settings_file(paths)
    payload = {
        KEY_BANK_DIR: str(settings.bank_dir) if settings.bank_dir else None,
        KEY_LAST_SOURCES: [str(p) for p in settings.last_sources],
    }
    tmp_name: str | None = None
    try:
        paths.data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=paths.data_dir, suffix=".tmp", delete=False
        ) as tmp:
            tmp_name = tmp.name
            json.dump(payload, tmp, indent=JSON_INDENT)
        os.replace(tmp_name, file)
    except OSError as exc:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)
        raise SaveIOError(f"Could not save settings to {file}: {exc}") from exc


def effective_bank_dir(paths: AppPaths, settings: Settings) -> Path:
    return settings.bank_dir if settings.bank_dir else paths.bank_dir
