"""Persist video-cracked actress marks on JavDB profile pages."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.sticker_store import get_connection, init_sticker_db


def init_video_cracked_actress_db() -> None:
    init_sticker_db()
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS video_cracked_actresses (
                javdb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                folder_name TEXT NOT NULL DEFAULT '',
                profile_url TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_video_cracked_actress_name
                ON video_cracked_actresses(name);
            """
        )


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def record_video_cracked_actress(payload: dict[str, Any]) -> dict[str, Any]:
    init_video_cracked_actress_db()
    javdb_id = str(payload.get("javdb_id") or "").strip()
    if not javdb_id:
        raise ValueError("javdb_id_required")

    row = {
        "javdb_id": javdb_id,
        "name": str(payload.get("name") or ""),
        "folder_name": str(payload.get("folder_name") or ""),
        "profile_url": str(payload.get("profile_url") or ""),
        "recorded_at": str(payload.get("recorded_at") or _now_iso()),
    }

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO video_cracked_actresses (
                javdb_id, name, folder_name, profile_url, recorded_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(javdb_id) DO UPDATE SET
                name = excluded.name,
                folder_name = excluded.folder_name,
                profile_url = excluded.profile_url,
                recorded_at = excluded.recorded_at
            """,
            (
                row["javdb_id"],
                row["name"],
                row["folder_name"],
                row["profile_url"],
                row["recorded_at"],
            ),
        )
        conn.commit()
    return row


def get_video_cracked_actresses_list() -> list[dict[str, Any]]:
    init_video_cracked_actress_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT javdb_id, name, folder_name, profile_url, recorded_at
            FROM video_cracked_actresses
            ORDER BY recorded_at DESC, name ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]
