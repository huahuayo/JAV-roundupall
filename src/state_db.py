"""Unified portable SQLite database for all user operations (not media/metadata files)."""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path

from src.config import APP_DIR

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_STATE_DB_NAME = "jav_manager_state.db"
LEGACY_STICKER_DB = APP_DIR / "extension_stickers.db"
LEGACY_LIBRARY_DB = APP_DIR / "library.db"


def _read_config() -> dict:
    from src.bridge_settings import _read_config as read

    return read()


def _write_config(data: dict) -> None:
    from src.bridge_settings import _write_config as write

    write(data)


def get_state_db_path() -> Path:
    raw = str(_read_config().get("state_db_path") or "").strip().strip('"').strip("'")
    if raw:
        path = Path(raw)
        lowered = str(path).lower().replace("/", "\\")
        if "pytest" in lowered or "\\temp\\" in lowered:
            data = _read_config()
            data.pop("state_db_path", None)
            _write_config(data)
        else:
            return path
    return APP_DIR / DEFAULT_STATE_DB_NAME


def set_state_db_path(path: str) -> Path:
    text = str(path or "").strip().strip('"').strip("'")
    data = _read_config()
    if text:
        data["state_db_path"] = str(Path(text))
    else:
        data.pop("state_db_path", None)
    _write_config(data)
    return get_state_db_path()


def ensure_state_dirs() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    db_path = get_state_db_path()
    if db_path.parent and str(db_path.parent) not in ("", "."):
        db_path.parent.mkdir(parents=True, exist_ok=True)


def get_state_connection() -> sqlite3.Connection:
    ensure_state_dirs()
    conn = sqlite3.connect(get_state_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_catalog_db() -> None:
    with get_state_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS catalog_entries (
                folder_path TEXT NOT NULL,
                code TEXT NOT NULL,
                actress_name TEXT NOT NULL DEFAULT '',
                library_kind TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                detail_url TEXT NOT NULL DEFAULT '',
                local_file TEXT NOT NULL DEFAULT '',
                added_date TEXT NOT NULL DEFAULT '',
                metadata_done INTEGER NOT NULL DEFAULT 0,
                media_done INTEGER NOT NULL DEFAULT 0,
                javdb_done INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (folder_path, code)
            );

            CREATE INDEX IF NOT EXISTS idx_catalog_code ON catalog_entries(code);
            CREATE INDEX IF NOT EXISTS idx_catalog_folder ON catalog_entries(folder_path);

            CREATE TABLE IF NOT EXISTS schema_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
            """
        )
        conn.execute(
            """
            INSERT INTO schema_meta(key, value) VALUES ('schema_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (str(SCHEMA_VERSION),),
        )
        conn.commit()


def _merge_legacy_library_tables(target: Path) -> None:
    if not LEGACY_LIBRARY_DB.is_file() or not target.is_file():
        return
    if target.resolve() == LEGACY_LIBRARY_DB.resolve():
        return
    try:
        with sqlite3.connect(target) as dest:
            dest.execute(f"ATTACH DATABASE ? AS legacy_lib", (str(LEGACY_LIBRARY_DB),))
            dest.execute(
                """
                CREATE TABLE IF NOT EXISTS videos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    path TEXT NOT NULL UNIQUE,
                    filename TEXT NOT NULL,
                    code TEXT,
                    title TEXT,
                    size_bytes INTEGER NOT NULL DEFAULT 0,
                    folder TEXT NOT NULL,
                    favorite INTEGER NOT NULL DEFAULT 0,
                    rating INTEGER NOT NULL DEFAULT 0,
                    notes TEXT NOT NULL DEFAULT ''
                )
                """
            )
            dest.execute(
                """
                INSERT OR IGNORE INTO videos (
                    path, filename, code, title, size_bytes, folder, favorite, rating, notes
                )
                SELECT path, filename, code, title, size_bytes, folder, favorite, rating, notes
                FROM legacy_lib.videos
                """
            )
            dest.commit()
    except sqlite3.Error as exc:
        logger.warning("Could not merge legacy library.db: %s", exc)


def migrate_legacy_databases() -> None:
    target = get_state_db_path()
    if target.is_file() and target.stat().st_size > 0:
        _merge_legacy_library_tables(target)
        return

    if LEGACY_STICKER_DB.is_file():
        try:
            shutil.copy2(LEGACY_STICKER_DB, target)
            logger.info("Migrated legacy extension_stickers.db -> %s", target)
        except OSError as exc:
            logger.warning("Could not copy legacy sticker database: %s", exc)

    if not target.is_file():
        ensure_state_dirs()
        sqlite3.connect(target).close()

    _merge_legacy_library_tables(target)


def init_state_database() -> None:
    """Create or migrate the unified operations database and all tables."""
    migrate_legacy_databases()

    from src.database import init_db
    from src.sticker_store import init_sticker_db
    from src.actress_store import init_actress_db
    from src.actress_profile_store import init_actress_profile_db
    from src.actress_folder_store import init_actress_folder_db
    from src.pending_download_store import init_pending_download_db
    from src.refined_store import init_refined_db
    from src.recycle_store import init_recycle_db
    from src.custom_tools_store import init_custom_tools_db
    from src.magnet_saved_actress_store import init_magnet_saved_actress_db
    from src.magnet_saved_video_store import init_magnet_saved_video_db
    from src.video_downloaded_actress_store import init_video_downloaded_actress_db
    from src.video_downloaded_video_store import init_video_downloaded_video_db
    from src.video_cracked_actress_store import init_video_cracked_actress_db
    from src.video_cracked_video_store import init_video_cracked_video_db

    init_sticker_db()
    init_actress_db()
    init_actress_profile_db()
    init_actress_folder_db()
    init_pending_download_db()
    init_refined_db()
    init_recycle_db()
    init_custom_tools_db()
    init_magnet_saved_actress_db()
    init_magnet_saved_video_db()
    init_video_downloaded_actress_db()
    init_video_downloaded_video_db()
    init_video_cracked_actress_db()
    init_video_cracked_video_db()
    init_catalog_db()
    init_db()


def clear_all_state_data() -> dict:
    """Clear all rows in the state database (keep schema), vacuum file, rewrite txt exports."""
    init_state_database()
    db_path = get_state_db_path()
    with get_state_connection() as conn:
        rows = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
        for row in rows:
            table = str(row[0] or "").strip()
            if not table or table == "schema_meta":
                continue
            try:
                conn.execute(f'DELETE FROM "{table}"')
            except sqlite3.Error as exc:
                logger.warning("Could not clear table %s: %s", table, exc)
        try:
            conn.execute("DELETE FROM sqlite_sequence")
        except sqlite3.Error:
            pass
        conn.commit()

    try:
        with sqlite3.connect(db_path) as vacuum_conn:
            vacuum_conn.execute("VACUUM")
    except sqlite3.Error as exc:
        logger.warning("VACUUM after clear failed: %s", exc)

    from src.sticker_store import get_sync_payload, regenerate_all_txt_files
    from src.actress_store import rewrite_collected_actresses_txt
    from src.actress_profile_store import rewrite_all_profile_txt_files
    from src.config_sanitize import reset_user_path_settings

    reset_user_path_settings()
    regenerate_all_txt_files()
    rewrite_collected_actresses_txt()
    rewrite_all_profile_txt_files()
    return get_sync_payload()
