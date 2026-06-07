"""Persist actress folder paths discovered during library sync tasks."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from src.pending_download_scanner import PENDING_DOWNLOAD_KEY
from src.sticker_store import get_connection, init_sticker_db
from src.video_cracked_scanner import VIDEO_CRACKED_KEY
from src.video_downloaded_scanner import VIDEO_DOWNLOADED_KEY

MAGNET_SAVED_KEY = "magnet_saved"

LIBRARY_KIND_PRIORITY: tuple[str, ...] = (
    PENDING_DOWNLOAD_KEY,
    MAGNET_SAVED_KEY,
    VIDEO_DOWNLOADED_KEY,
    VIDEO_CRACKED_KEY,
)


def sanitize_actress_name(name: str) -> str:
    """Strip UI noise (newlines, video counts) from actress names used for paths."""
    text = str(name or "").replace("\r", "").strip()
    if not text:
        return ""
    if "\n" in text:
        text = text.split("\n", 1)[0].strip()
    text = re.sub(r"\s*\d+\s*部影片\s*$", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"[（(]\s*\d+\s*部\s*[）)]\s*$", "", text).strip()
    text = re.sub(r"\s+", " ", text).strip()
    return text

def init_actress_folder_db() -> None:
    init_sticker_db()
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS actress_folder_locations (
                actress_name TEXT NOT NULL DEFAULT '',
                javdb_id TEXT NOT NULL DEFAULT '',
                library_kind TEXT NOT NULL DEFAULT '',
                folder_path TEXT NOT NULL DEFAULT '',
                folder_name TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT '',
                PRIMARY KEY (actress_name COLLATE NOCASE, library_kind)
            );

            CREATE INDEX IF NOT EXISTS idx_actress_folder_javdb
                ON actress_folder_locations(javdb_id);
            """
        )


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_name_key(name: str) -> str:
    return sanitize_actress_name(name).casefold()


def record_actress_folder(
    *,
    actress_name: str,
    folder_path: str,
    library_kind: str,
    javdb_id: str = "",
    folder_name: str = "",
) -> dict[str, Any]:
    init_actress_folder_db()
    clean_name = sanitize_actress_name(actress_name)
    path_text = str(folder_path or "").strip()
    kind = str(library_kind or "").strip()
    if not clean_name or not path_text or not kind:
        raise ValueError("actress_folder_record_incomplete")

    row = {
        "actress_name": clean_name,
        "javdb_id": str(javdb_id or "").strip(),
        "library_kind": kind,
        "folder_path": path_text,
        "folder_name": str(folder_name or Path(path_text).name).strip(),
        "updated_at": _now_iso(),
    }

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO actress_folder_locations (
                actress_name, javdb_id, library_kind, folder_path, folder_name, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(actress_name, library_kind) DO UPDATE SET
                javdb_id = CASE
                    WHEN excluded.javdb_id != '' THEN excluded.javdb_id
                    ELSE actress_folder_locations.javdb_id
                END,
                folder_path = excluded.folder_path,
                folder_name = excluded.folder_name,
                updated_at = excluded.updated_at
            """,
            (
                row["actress_name"],
                row["javdb_id"],
                row["library_kind"],
                row["folder_path"],
                row["folder_name"],
                row["updated_at"],
            ),
        )
        if row["javdb_id"]:
            conn.execute(
                """
                UPDATE actress_folder_locations
                SET javdb_id = ?
                WHERE actress_name = ? COLLATE NOCASE AND javdb_id = ''
                """,
                (row["javdb_id"], row["actress_name"]),
            )
        conn.commit()
    return row


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "actress_name": row["actress_name"],
        "javdb_id": row["javdb_id"],
        "library_kind": row["library_kind"],
        "folder_path": row["folder_path"],
        "folder_name": row["folder_name"],
        "updated_at": row["updated_at"],
    }


def _path_exists(path_text: str) -> bool:
    text = str(path_text or "").strip()
    if not text:
        return False
    try:
        return Path(text).is_dir()
    except OSError:
        return False


def list_actress_folder_records(
    actress_name: str = "",
    *,
    javdb_id: str = "",
) -> list[dict[str, Any]]:
    init_actress_folder_db()
    clean_name = sanitize_actress_name(actress_name)
    javdb = str(javdb_id or "").strip()

    with get_connection() as conn:
        if javdb:
            rows = conn.execute(
                """
                SELECT actress_name, javdb_id, library_kind, folder_path, folder_name, updated_at
                FROM actress_folder_locations
                WHERE javdb_id = ? OR actress_name = ? COLLATE NOCASE
                ORDER BY updated_at DESC
                """,
                (javdb, clean_name),
            ).fetchall()
        elif clean_name:
            rows = conn.execute(
                """
                SELECT actress_name, javdb_id, library_kind, folder_path, folder_name, updated_at
                FROM actress_folder_locations
                WHERE actress_name = ? COLLATE NOCASE
                ORDER BY updated_at DESC
                """,
                (clean_name,),
            ).fetchall()
        else:
            return []

    records = [_row_to_dict(row) for row in rows]
    priority = {kind: index for index, kind in enumerate(LIBRARY_KIND_PRIORITY)}
    records.sort(key=lambda item: priority.get(str(item.get("library_kind") or ""), 99))
    return records


def lookup_actress_folder_record(
    actress_name: str,
    *,
    javdb_id: str = "",
) -> dict[str, Any] | None:
    records = list_actress_folder_records(actress_name, javdb_id=javdb_id)
    if not records:
        return None

    for record in records:
        path_text = str(record.get("folder_path") or "")
        if _path_exists(path_text):
            result = dict(record)
            result["source"] = "database"
            return result

    # UNC 等网络路径可能暂时无法 is_dir()，仍信任同步时写入的数据库记录。
    result = dict(records[0])
    result["source"] = "database"
    return result


def lookup_actress_folder_from_db(
    actress_name: str,
    *,
    javdb_id: str = "",
) -> Path | None:
    record = lookup_actress_folder_record(actress_name, javdb_id=javdb_id)
    if not record:
        return None
    return Path(str(record["folder_path"]))


def record_actress_folder_from_sync_result(item: dict[str, Any], library_kind: str) -> dict[str, Any] | None:
    from src.sync_folder_rename import strip_sync_status_prefix

    folder_path = str(item.get("folder_path") or item.get("new_folder_path") or "").strip()
    if not folder_path:
        return None

    actress = item.get("actress") or {}
    actress_name = sanitize_actress_name(
        str(
            actress.get("name")
            or item.get("actress_match_name")
            or strip_sync_status_prefix(str(item.get("folder_name") or ""))
            or ""
        )
    )
    if not actress_name:
        return None

    return record_actress_folder(
        actress_name=actress_name,
        folder_path=folder_path,
        library_kind=library_kind,
        javdb_id=str(actress.get("javdb_id") or item.get("javdb_id") or ""),
        folder_name=str(item.get("folder_name") or Path(folder_path).name),
    )
