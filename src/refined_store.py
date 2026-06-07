"""Persist user-marked refined (加精) videos."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.sticker_store import get_connection


def init_refined_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS refined_videos (
                code TEXT NOT NULL,
                folder_path TEXT NOT NULL DEFAULT '',
                video_path TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL,
                PRIMARY KEY (code, folder_path)
            );
            CREATE INDEX IF NOT EXISTS idx_refined_code ON refined_videos(code);
            """
        )


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def add_refined_video(
    *,
    code: str,
    folder_path: str = "",
    video_path: str = "",
    title: str = "",
) -> None:
    init_refined_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO refined_videos (code, folder_path, video_path, title, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(code, folder_path) DO UPDATE SET
                video_path = excluded.video_path,
                title = excluded.title,
                recorded_at = excluded.recorded_at
            """,
            (code, folder_path, video_path, title, _now()),
        )
        conn.commit()


def remove_refined_video(*, code: str, folder_path: str = "") -> None:
    init_refined_db()
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM refined_videos WHERE code = ? AND folder_path = ?",
            (code, folder_path),
        )
        conn.commit()


def is_refined_video(*, code: str, folder_path: str = "") -> bool:
    init_refined_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM refined_videos WHERE code = ? AND folder_path = ? LIMIT 1",
            (code, folder_path),
        ).fetchone()
        return row is not None


def list_refined_videos() -> list[dict[str, Any]]:
    init_refined_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT code, folder_path, video_path, title, recorded_at
            FROM refined_videos
            ORDER BY recorded_at DESC, code ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]
