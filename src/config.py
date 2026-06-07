"""Application paths and constants."""

import sys
from pathlib import Path

APP_NAME = "JAV一网打尽"
APP_VERSION = "0.2.0"

APP_DIR = Path.home() / ".jav-manager"
CONFIG_PATH = APP_DIR / "config.json"
DB_PATH = APP_DIR / "library.db"
DEFAULT_STATE_DB_NAME = "jav_manager_state.db"

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".wmv", ".mov", ".m4v", ".ts", ".flv"}

DEFAULT_WINDOW_SIZE = "1200x900"
BRIDGE_DEFAULT_PORT = 17892


def get_project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def get_extension_dir() -> Path:
    return get_project_root() / "extension"


def get_app_icon_path() -> Path | None:
    if getattr(sys, "frozen", False):
        bundled = Path(getattr(sys, "_MEIPASS", "")) / "app-icon.ico"
        if bundled.is_file():
            return bundled
    for candidate in (
        get_project_root() / "packaging" / "app-icon.ico",
        Path(__file__).resolve().parent.parent / "packaging" / "app-icon.ico",
    ):
        if candidate.is_file():
            return candidate
    return None
