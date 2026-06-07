"""Persist magnet-saved actress marks (local magnet vs 115 storage)."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from typing import Any

from src.sticker_store import get_connection, init_sticker_db

logger = logging.getLogger(__name__)

STORAGE_LOCAL = "local_magnet"
STORAGE_115 = "115"


def init_magnet_saved_actress_db() -> None:
    init_sticker_db()
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS magnet_saved_actresses (
                javdb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                folder_name TEXT NOT NULL DEFAULT '',
                profile_url TEXT NOT NULL DEFAULT '',
                storage_type TEXT NOT NULL DEFAULT 'local_magnet',
                recorded_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_magnet_saved_actress_name
                ON magnet_saved_actresses(name);
            """
        )


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def record_magnet_saved_actress(payload: dict[str, Any]) -> dict[str, Any]:
    init_magnet_saved_actress_db()
    javdb_id = str(payload.get("javdb_id") or "").strip()
    if not javdb_id:
        raise ValueError("javdb_id_required")

    storage_type = str(payload.get("storage_type") or STORAGE_LOCAL).strip()
    if storage_type not in (STORAGE_LOCAL, STORAGE_115):
        storage_type = STORAGE_LOCAL

    row = {
        "javdb_id": javdb_id,
        "name": str(payload.get("name") or ""),
        "folder_name": str(payload.get("folder_name") or ""),
        "profile_url": str(payload.get("profile_url") or ""),
        "storage_type": storage_type,
        "recorded_at": str(payload.get("recorded_at") or _now_iso()),
    }

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO magnet_saved_actresses (
                javdb_id, name, folder_name, profile_url, storage_type, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(javdb_id) DO UPDATE SET
                name = excluded.name,
                folder_name = excluded.folder_name,
                profile_url = excluded.profile_url,
                storage_type = excluded.storage_type,
                recorded_at = excluded.recorded_at
            """,
            (
                row["javdb_id"],
                row["name"],
                row["folder_name"],
                row["profile_url"],
                row["storage_type"],
                row["recorded_at"],
            ),
        )
        conn.commit()
    return row


def get_magnet_saved_actresses_list() -> list[dict[str, Any]]:
    init_magnet_saved_actress_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT javdb_id, name, folder_name, profile_url, storage_type, recorded_at
            FROM magnet_saved_actresses
            ORDER BY recorded_at DESC, name ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]
