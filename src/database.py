"""SQLite persistence for videos, favorites, and settings."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from src.config import APP_DIR, CONFIG_PATH
from src.state_db import get_state_db_path
from src.scanner import ScannedVideo


@dataclass
class VideoRecord:
    id: int
    path: str
    filename: str
    code: str | None
    title: str | None
    size_bytes: int
    folder: str
    favorite: bool
    rating: int
    notes: str


def ensure_app_dirs() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_app_dirs()
    conn = sqlite3.connect(get_state_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
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
            );

            CREATE INDEX IF NOT EXISTS idx_videos_code ON videos(code);
            CREATE INDEX IF NOT EXISTS idx_videos_favorite ON videos(favorite);
            CREATE INDEX IF NOT EXISTS idx_videos_rating ON videos(rating);
            """
        )


def load_library_paths() -> list[str]:
    if not CONFIG_PATH.exists():
        return []
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    return [p for p in data.get("library_paths", []) if Path(p).is_dir()]


def save_library_paths(paths: list[str]) -> None:
    ensure_app_dirs()
    existing = {}
    if CONFIG_PATH.exists():
        existing = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    existing["library_paths"] = paths
    CONFIG_PATH.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")


def upsert_videos(scanned: list[ScannedVideo]) -> int:
    """Insert or update scanned videos. Returns count of rows touched."""
    if not scanned:
        return 0

    with get_connection() as conn:
        count = 0
        for item in scanned:
            conn.execute(
                """
                INSERT INTO videos (path, filename, code, title, size_bytes, folder)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    filename = excluded.filename,
                    code = excluded.code,
                    title = excluded.title,
                    size_bytes = excluded.size_bytes,
                    folder = excluded.folder
                """,
                (item.path, item.filename, item.code, item.title, item.size_bytes, item.folder),
            )
            count += 1
        conn.commit()
    return count


def list_videos(
    *,
    search: str = "",
    favorites_only: bool = False,
    min_rating: int = 0,
) -> list[VideoRecord]:
    query = """
        SELECT id, path, filename, code, title, size_bytes, folder,
               favorite, rating, notes
        FROM videos
        WHERE 1=1
    """
    params: list[object] = []

    if search.strip():
        like = f"%{search.strip()}%"
        query += " AND (code LIKE ? OR filename LIKE ? OR title LIKE ? OR folder LIKE ? OR notes LIKE ?)"
        params.extend([like, like, like, like, like])

    if favorites_only:
        query += " AND favorite = 1"

    if min_rating > 0:
        query += " AND rating >= ?"
        params.append(min_rating)

    query += " ORDER BY favorite DESC, rating DESC, code ASC, filename ASC"

    with get_connection() as conn:
        rows = conn.execute(query, params).fetchall()

    return [
        VideoRecord(
            id=row["id"],
            path=row["path"],
            filename=row["filename"],
            code=row["code"],
            title=row["title"],
            size_bytes=row["size_bytes"],
            folder=row["folder"],
            favorite=bool(row["favorite"]),
            rating=row["rating"],
            notes=row["notes"],
        )
        for row in rows
    ]


def set_favorite(video_id: int, favorite: bool) -> None:
    with get_connection() as conn:
        conn.execute("UPDATE videos SET favorite = ? WHERE id = ?", (int(favorite), video_id))
        conn.commit()


def set_rating(video_id: int, rating: int) -> None:
    rating = max(0, min(5, rating))
    with get_connection() as conn:
        conn.execute("UPDATE videos SET rating = ? WHERE id = ?", (rating, video_id))
        conn.commit()


def find_videos_by_code(code: str) -> list[VideoRecord]:
    if not code:
        return []
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, path, filename, code, title, size_bytes, folder,
                   favorite, rating, notes
            FROM videos
            WHERE code = ?
            ORDER BY favorite DESC, rating DESC
            """,
            (code.upper(),),
        ).fetchall()
    return [
        VideoRecord(
            id=row["id"],
            path=row["path"],
            filename=row["filename"],
            code=row["code"],
            title=row["title"],
            size_bytes=row["size_bytes"],
            folder=row["folder"],
            favorite=bool(row["favorite"]),
            rating=row["rating"],
            notes=row["notes"],
        )
        for row in rows
    ]


def get_stats() -> dict[str, int]:
    with get_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        favorites = conn.execute("SELECT COUNT(*) FROM videos WHERE favorite = 1").fetchone()[0]
        coded = conn.execute("SELECT COUNT(*) FROM videos WHERE code IS NOT NULL").fetchone()[0]
    return {"total": total, "favorites": favorites, "coded": coded}
