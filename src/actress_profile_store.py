"""Blocked / mediocre JavDB actress profiles from the browser extension."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import APP_DIR, get_project_root
from src.sticker_store import get_connection, get_txt_dir, init_sticker_db

logger = logging.getLogger(__name__)

BLOCKED_ACTRESSES_TXT = "屏蔽女优.txt"
BLOCKED_ACTRESS_SERIES_TXT = "因屏蔽女优屏蔽的番号.txt"
MEDIOCRE_ACTRESSES_TXT = "中庸女优.txt"


def init_actress_profile_db() -> None:
    init_sticker_db()
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS blocked_actresses (
                javdb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                aliases TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                page_url TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS blocked_actress_series (
                series TEXT PRIMARY KEY,
                actress_javdb_id TEXT NOT NULL DEFAULT '',
                actress_name TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_blocked_actress_series_actress
                ON blocked_actress_series(actress_javdb_id);

            CREATE TABLE IF NOT EXISTS mediocre_actresses (
                javdb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                complaints TEXT NOT NULL DEFAULT '',
                page_url TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL
            );
            """
        )


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def normalize_series(raw: str) -> str:
    text = str(raw or "").strip().upper()
    if not text:
        return ""
    if text.startswith("FC2-PPV"):
        return "FC2-PPV"
    if text.startswith("HEYZO"):
        return "HEYZO"
    if "-" in text:
        return text.split("-", 1)[0]
    return text


def record_blocked_actress(payload: dict[str, Any]) -> dict[str, Any]:
    init_actress_profile_db()
    javdb_id = str(payload.get("javdb_id") or "").strip()
    if not javdb_id:
        raise ValueError("javdb_id_required")

    recorded_at = str(payload.get("recorded_at") or _now_iso())
    reason = str(payload.get("reason") or "")
    name = str(payload.get("name") or "")
    aliases = str(payload.get("aliases") or "")
    page_url = str(payload.get("page_url") or "")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO blocked_actresses (javdb_id, name, aliases, reason, page_url, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(javdb_id) DO UPDATE SET
                name = excluded.name,
                aliases = excluded.aliases,
                reason = excluded.reason,
                page_url = excluded.page_url,
                recorded_at = excluded.recorded_at
            """,
            (javdb_id, name, aliases, reason, page_url, recorded_at),
        )

        series_list = payload.get("series") or []
        if isinstance(series_list, list):
            for item in series_list:
                if isinstance(item, str):
                    series = normalize_series(item)
                elif isinstance(item, dict):
                    series = normalize_series(str(item.get("series") or ""))
                else:
                    continue
                if not series:
                    continue
                conn.execute(
                    """
                    INSERT INTO blocked_actress_series (
                        series, actress_javdb_id, actress_name, reason, recorded_at
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(series) DO UPDATE SET
                        actress_javdb_id = excluded.actress_javdb_id,
                        actress_name = excluded.actress_name,
                        reason = excluded.reason,
                        recorded_at = excluded.recorded_at
                    """,
                    (series, javdb_id, name, reason, recorded_at),
                )
        conn.commit()

    rewrite_blocked_actress_txt_files()
    return {
        "javdb_id": javdb_id,
        "name": name,
        "reason": reason,
        "recorded_at": recorded_at,
    }


def remove_blocked_actress(javdb_id: str) -> None:
    init_actress_profile_db()
    actor_id = str(javdb_id or "").strip()
    if not actor_id:
        return
    with get_connection() as conn:
        conn.execute("DELETE FROM blocked_actress_series WHERE actress_javdb_id = ?", (actor_id,))
        conn.execute("DELETE FROM blocked_actresses WHERE javdb_id = ?", (actor_id,))
        conn.commit()
    rewrite_blocked_actress_txt_files()


def record_mediocre_actress(payload: dict[str, Any]) -> dict[str, Any]:
    init_actress_profile_db()
    javdb_id = str(payload.get("javdb_id") or "").strip()
    if not javdb_id:
        raise ValueError("javdb_id_required")

    recorded_at = str(payload.get("recorded_at") or _now_iso())
    row = {
        "javdb_id": javdb_id,
        "name": str(payload.get("name") or ""),
        "complaints": str(payload.get("complaints") or ""),
        "page_url": str(payload.get("page_url") or ""),
        "recorded_at": recorded_at,
    }

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO mediocre_actresses (javdb_id, name, complaints, page_url, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(javdb_id) DO UPDATE SET
                name = excluded.name,
                complaints = excluded.complaints,
                page_url = excluded.page_url,
                recorded_at = excluded.recorded_at
            """,
            (
                row["javdb_id"],
                row["name"],
                row["complaints"],
                row["page_url"],
                row["recorded_at"],
            ),
        )
        conn.commit()

    rewrite_mediocre_actresses_txt()
    return row


def rewrite_blocked_actress_txt_files() -> None:
    init_actress_profile_db()
    txt_dir = get_txt_dir()
    txt_dir.mkdir(parents=True, exist_ok=True)

    with get_connection() as conn:
        actress_rows = conn.execute(
            """
            SELECT javdb_id, name, aliases, reason, page_url, recorded_at
            FROM blocked_actresses
            ORDER BY recorded_at DESC, name ASC
            """
        ).fetchall()
        series_rows = conn.execute(
            """
            SELECT series, actress_javdb_id, actress_name, reason, recorded_at
            FROM blocked_actress_series
            ORDER BY recorded_at DESC, series ASC
            """
        ).fetchall()

    blocked_path = txt_dir / BLOCKED_ACTRESSES_TXT
    lines = [
        f"# JAV Manager — {BLOCKED_ACTRESSES_TXT}",
        f"# 目录: {blocked_path}",
        f"# 更新: {_now_iso()}",
        "",
    ]
    for row in actress_rows:
        lines.append(
            " | ".join(
                [
                    row["name"] or row["javdb_id"],
                    f"ID:{row['javdb_id']}",
                    f"别名:{row['aliases'] or '-'}",
                    f"原因:{row['reason'] or '-'}",
                    f"页面:{row['page_url'] or '-'}",
                    f"记录:{row['recorded_at']}",
                ]
            )
        )
    lines.append("")
    blocked_path.write_text("\n".join(lines), encoding="utf-8")

    series_path = txt_dir / BLOCKED_ACTRESS_SERIES_TXT
    lines = [
        f"# JAV Manager — {BLOCKED_ACTRESS_SERIES_TXT}",
        f"# 目录: {series_path}",
        f"# 更新: {_now_iso()}",
        "",
    ]
    for row in series_rows:
        lines.append(
            " | ".join(
                [
                    row["series"],
                    f"女优:{row['actress_name'] or '-'}",
                    f"ID:{row['actress_javdb_id']}",
                    f"原因:{row['reason'] or '-'}",
                    f"记录:{row['recorded_at']}",
                ]
            )
        )
    lines.append("")
    series_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info(
        "Wrote blocked actress files: %d actresses, %d series",
        len(actress_rows),
        len(series_rows),
    )


def rewrite_mediocre_actresses_txt() -> None:
    init_actress_profile_db()
    path = get_txt_dir() / MEDIOCRE_ACTRESSES_TXT
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT javdb_id, name, complaints, page_url, recorded_at
            FROM mediocre_actresses
            ORDER BY recorded_at DESC, name ASC
            """
        ).fetchall()

    lines = [
        f"# JAV Manager — {MEDIOCRE_ACTRESSES_TXT}",
        f"# 目录: {path}",
        f"# 更新: {_now_iso()}",
        "",
    ]
    for row in rows:
        lines.append(
            " | ".join(
                [
                    row["name"] or row["javdb_id"],
                    f"ID:{row['javdb_id']}",
                    f"槽点:{row['complaints'] or '-'}",
                    f"页面:{row['page_url'] or '-'}",
                    f"记录:{row['recorded_at']}",
                ]
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def rewrite_all_profile_txt_files() -> None:
    rewrite_blocked_actress_txt_files()
    rewrite_mediocre_actresses_txt()


def get_blocked_actresses_list() -> list[dict[str, Any]]:
    init_actress_profile_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT javdb_id, name, aliases, reason, page_url, recorded_at
            FROM blocked_actresses ORDER BY recorded_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_blocked_actress_series_list() -> list[dict[str, Any]]:
    init_actress_profile_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT series, actress_javdb_id, actress_name, reason, recorded_at
            FROM blocked_actress_series ORDER BY recorded_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_mediocre_actresses_list() -> list[dict[str, Any]]:
    init_actress_profile_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT javdb_id, name, complaints, page_url, recorded_at
            FROM mediocre_actresses ORDER BY recorded_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def import_profile_bulk_from_extension(data: dict[str, Any]) -> int:
    init_actress_profile_db()
    count = 0

    blocked = data.get("blockedActresses") or {}
    if isinstance(blocked, dict):
        for aid, record in blocked.items():
            if not record:
                continue
            payload = dict(record)
            payload["javdb_id"] = str(payload.get("javdb_id") or aid)
            series = payload.get("series") or []
            if isinstance(series, dict):
                series = list(series.keys())
            payload["series"] = series
            record_blocked_actress(payload)
            count += 1

    series_map = data.get("blockedActressSeries") or {}
    if isinstance(series_map, dict):
        for series, record in series_map.items():
            if not record:
                continue
            payload = dict(record)
            payload["javdb_id"] = str(payload.get("actress_javdb_id") or payload.get("javdb_id") or "")
            payload["name"] = str(payload.get("actress_name") or payload.get("name") or "")
            payload["reason"] = str(payload.get("reason") or "")
            payload["series"] = [str(payload.get("series") or series)]
            if payload["javdb_id"]:
                record_blocked_actress(payload)
                count += 1

    mediocre = data.get("mediocreActresses") or {}
    if isinstance(mediocre, dict):
        for aid, record in mediocre.items():
            if not record:
                continue
            payload = dict(record)
            payload["javdb_id"] = str(payload.get("javdb_id") or aid)
            record_mediocre_actress(payload)
            count += 1

    rewrite_all_profile_txt_files()
    return count
