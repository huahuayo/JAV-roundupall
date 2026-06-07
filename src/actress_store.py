"""Persist JavDB collected actresses synced from the browser extension."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import get_project_root
from src.sticker_store import get_connection

logger = logging.getLogger(__name__)

COLLECTED_ACTRESSES_TXT = "收藏女优.txt"
META_LAST_SYNC_DATE = "actress_last_sync_date"
META_LAST_SYNC_AT = "actress_last_sync_at"
META_LAST_COUNT = "actress_last_count"


def init_actress_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS collected_actresses (
                javdb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                profile_url TEXT NOT NULL DEFAULT '',
                synced_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_collected_actresses_name ON collected_actresses(name);

            CREATE TABLE IF NOT EXISTS actress_sync_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _set_meta(key: str, value: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO actress_sync_meta (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (key, value),
        )
        conn.commit()


def _get_meta(key: str) -> str:
    init_actress_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM actress_sync_meta WHERE key = ?",
            (key,),
        ).fetchone()
    return str(row["value"]) if row else ""


def get_actress_sync_info() -> dict[str, Any]:
    return {
        "last_sync_date": _get_meta(META_LAST_SYNC_DATE),
        "last_sync_at": _get_meta(META_LAST_SYNC_AT),
        "last_count": int(_get_meta(META_LAST_COUNT) or "0"),
    }


def should_auto_sync_actresses_today() -> bool:
    init_actress_db()
    last_date = _get_meta(META_LAST_SYNC_DATE)
    return last_date != _today()


def sync_collected_actresses(actresses: list[dict[str, Any]], synced_at: str | None = None) -> int:
    """Replace collected actress list with the latest scrape."""
    init_actress_db()
    synced = synced_at or _now_iso()
    sync_date = synced[:10] if len(synced) >= 10 else _today()

    with get_connection() as conn:
        conn.execute("DELETE FROM collected_actresses")
        for item in actresses:
            javdb_id = str(item.get("javdb_id") or "").strip()
            name = str(item.get("name") or "").strip()
            if not javdb_id or not name:
                continue
            conn.execute(
                """
                INSERT INTO collected_actresses (javdb_id, name, profile_url, synced_at)
                VALUES (?, ?, ?, ?)
                """,
                (
                    javdb_id,
                    name,
                    str(item.get("profile_url") or ""),
                    synced,
                ),
            )
        conn.commit()

    count = len(list_collected_actresses())
    _set_meta(META_LAST_SYNC_DATE, sync_date)
    _set_meta(META_LAST_SYNC_AT, synced)
    _set_meta(META_LAST_COUNT, str(count))
    rewrite_collected_actresses_txt()
    logger.info("Synced %d collected actresses", count)
    return count


def list_collected_actresses() -> list[dict[str, Any]]:
    init_actress_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT javdb_id, name, profile_url, synced_at
            FROM collected_actresses
            ORDER BY name COLLATE NOCASE ASC
            """
        ).fetchall()
    return [
        {
            "javdb_id": row["javdb_id"],
            "name": row["name"],
            "profile_url": row["profile_url"],
            "synced_at": row["synced_at"],
        }
        for row in rows
    ]


def rewrite_collected_actresses_txt() -> None:
    init_actress_db()
    path = Path(get_project_root()) / COLLECTED_ACTRESSES_TXT
    rows = list_collected_actresses()
    info = get_actress_sync_info()

    lines = [
        f"# JAV Manager — {COLLECTED_ACTRESSES_TXT}",
        f"# 目录: {path}",
        f"# 更新: {_now_iso()}",
        f"# 同步时间: {info['last_sync_at'] or '-'}",
        f"# 数量: {len(rows)}",
        "",
    ]
    for row in rows:
        lines.append(f"{row['name']} | ID:{row['javdb_id']} | {row['profile_url'] or '-'}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote collected actresses list: %s (%d records)", path, len(rows))
