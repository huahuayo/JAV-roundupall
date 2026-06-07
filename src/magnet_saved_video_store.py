"""Persist magnet-saved marks on individual video detail pages."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from src.sticker_store import get_connection, init_sticker_db

logger = logging.getLogger(__name__)

STORAGE_LOCAL = "local_magnet"
STORAGE_115 = "115"


def init_magnet_saved_video_db() -> None:
    init_sticker_db()
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS magnet_saved_videos (
                code TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                storage_type TEXT NOT NULL DEFAULT 'local_magnet',
                has_subtitle INTEGER NOT NULL DEFAULT 0,
                is_4k INTEGER NOT NULL DEFAULT 0,
                detail_url TEXT NOT NULL DEFAULT '',
                folder_name TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_magnet_saved_video_storage
                ON magnet_saved_videos(storage_type);
            """
        )


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def record_magnet_saved_video(payload: dict[str, Any]) -> dict[str, Any]:
    init_magnet_saved_video_db()
    code = str(payload.get("code") or "").strip().upper()
    if not code:
        raise ValueError("code_required")

    storage_type = str(payload.get("storage_type") or STORAGE_LOCAL).strip()
    if storage_type not in (STORAGE_LOCAL, STORAGE_115):
        storage_type = STORAGE_LOCAL

    row = {
        "code": code,
        "title": str(payload.get("title") or ""),
        "storage_type": storage_type,
        "has_subtitle": 1 if payload.get("has_subtitle") else 0,
        "is_4k": 1 if payload.get("is_4k") else 0,
        "detail_url": str(payload.get("detail_url") or ""),
        "folder_name": str(payload.get("folder_name") or ""),
        "recorded_at": str(payload.get("recorded_at") or _now_iso()),
    }

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO magnet_saved_videos (
                code, title, storage_type, has_subtitle, is_4k,
                detail_url, folder_name, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                title = excluded.title,
                storage_type = excluded.storage_type,
                has_subtitle = excluded.has_subtitle,
                is_4k = excluded.is_4k,
                detail_url = excluded.detail_url,
                folder_name = excluded.folder_name,
                recorded_at = excluded.recorded_at
            """,
            (
                row["code"],
                row["title"],
                row["storage_type"],
                row["has_subtitle"],
                row["is_4k"],
                row["detail_url"],
                row["folder_name"],
                row["recorded_at"],
            ),
        )
        conn.commit()
    return row


def get_magnet_saved_videos_list() -> list[dict[str, Any]]:
    init_magnet_saved_video_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT code, title, storage_type, has_subtitle, is_4k,
                   detail_url, folder_name, recorded_at
            FROM magnet_saved_videos
            ORDER BY recorded_at DESC, code ASC
            """
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["has_subtitle"] = bool(item.get("has_subtitle"))
        item["is_4k"] = bool(item.get("is_4k"))
        result.append(item)
    return result
