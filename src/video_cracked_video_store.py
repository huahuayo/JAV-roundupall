"""Persist video-cracked marks on individual JavDB detail pages."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.parser import CRACK_STATUS_LABELS
from src.sticker_store import get_connection, init_sticker_db


def init_video_cracked_video_db() -> None:
    init_sticker_db()
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS video_cracked_videos (
                code TEXT PRIMARY KEY,
                title TEXT NOT NULL DEFAULT '',
                crack_status TEXT NOT NULL DEFAULT 'pending_crack',
                has_subtitle INTEGER NOT NULL DEFAULT 0,
                is_4k INTEGER NOT NULL DEFAULT 0,
                has_subtitle_file INTEGER NOT NULL DEFAULT 0,
                has_uncensored_file INTEGER NOT NULL DEFAULT 0,
                detail_url TEXT NOT NULL DEFAULT '',
                folder_name TEXT NOT NULL DEFAULT '',
                source_file TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_video_cracked_video_folder
                ON video_cracked_videos(folder_name);
            """
        )


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def record_video_cracked_video(payload: dict[str, Any]) -> dict[str, Any]:
    init_video_cracked_video_db()
    code = str(payload.get("code") or "").strip().upper()
    if not code:
        raise ValueError("code_required")

    crack_status = str(payload.get("crack_status") or "pending_crack").strip() or "pending_crack"
    row = {
        "code": code,
        "title": str(payload.get("title") or ""),
        "crack_status": crack_status,
        "crack_status_label": str(
            payload.get("crack_status_label") or CRACK_STATUS_LABELS.get(crack_status, crack_status)
        ),
        "has_subtitle": 1 if payload.get("has_subtitle") else 0,
        "is_4k": 1 if payload.get("is_4k") else 0,
        "has_subtitle_file": 1 if payload.get("has_subtitle_file") else 0,
        "has_uncensored_file": 1 if payload.get("has_uncensored_file") else 0,
        "detail_url": str(payload.get("detail_url") or ""),
        "folder_name": str(payload.get("folder_name") or ""),
        "source_file": str(payload.get("source_file") or ""),
        "recorded_at": str(payload.get("recorded_at") or _now_iso()),
    }

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO video_cracked_videos (
                code, title, crack_status, has_subtitle, is_4k,
                has_subtitle_file, has_uncensored_file,
                detail_url, folder_name, source_file, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code) DO UPDATE SET
                title = excluded.title,
                crack_status = excluded.crack_status,
                has_subtitle = excluded.has_subtitle,
                is_4k = excluded.is_4k,
                has_subtitle_file = excluded.has_subtitle_file,
                has_uncensored_file = excluded.has_uncensored_file,
                detail_url = excluded.detail_url,
                folder_name = excluded.folder_name,
                source_file = excluded.source_file,
                recorded_at = excluded.recorded_at
            """,
            (
                row["code"],
                row["title"],
                row["crack_status"],
                row["has_subtitle"],
                row["is_4k"],
                row["has_subtitle_file"],
                row["has_uncensored_file"],
                row["detail_url"],
                row["folder_name"],
                row["source_file"],
                row["recorded_at"],
            ),
        )
        conn.commit()

    row["has_subtitle"] = bool(row["has_subtitle"])
    row["is_4k"] = bool(row["is_4k"])
    row["has_subtitle_file"] = bool(row["has_subtitle_file"])
    row["has_uncensored_file"] = bool(row["has_uncensored_file"])
    return row


def get_video_cracked_videos_list() -> list[dict[str, Any]]:
    init_video_cracked_video_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT code, title, crack_status, has_subtitle, is_4k,
                   has_subtitle_file, has_uncensored_file,
                   detail_url, folder_name, source_file, recorded_at
            FROM video_cracked_videos
            ORDER BY recorded_at DESC, code ASC
            """
        ).fetchall()

    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["has_subtitle"] = bool(item.get("has_subtitle"))
        item["is_4k"] = bool(item.get("is_4k"))
        item["has_subtitle_file"] = bool(item.get("has_subtitle_file"))
        item["has_uncensored_file"] = bool(item.get("has_uncensored_file"))
        item["crack_status_label"] = CRACK_STATUS_LABELS.get(
            str(item.get("crack_status") or ""),
            str(item.get("crack_status") or ""),
        )
        result.append(item)
    return result
