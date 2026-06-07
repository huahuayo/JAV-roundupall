"""Persist JavDB preview-sticker actions from the browser extension."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from src.config import APP_DIR, get_project_root
from src.state_db import get_state_connection as _state_connection, get_state_db_path

logger = logging.getLogger(__name__)

ACTION_BLOCKED = "blocked"
ACTION_VERIFIED = "verified"
ACTION_DOWNLOADED = "downloaded"
ACTION_MARKED = "marked"

BLOCKED_SERIES_TXT = "已屏蔽系列.txt"
BLOCKED_TITLE_KEYWORDS_TXT = "屏蔽标题关键词.txt"

TXT_FILENAMES = {
    ACTION_BLOCKED: "已屏蔽.txt",
    ACTION_VERIFIED: "已鉴定.txt",
    ACTION_DOWNLOADED: "已下载.txt",
}

LIST_ACTIONS = (ACTION_BLOCKED, ACTION_VERIFIED, ACTION_DOWNLOADED)


def ensure_dirs() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    get_project_root().mkdir(parents=True, exist_ok=True)


def get_connection() -> sqlite3.Connection:
    ensure_dirs()
    return _state_connection()


def init_sticker_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS sticker_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                action_type TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                release_date TEXT NOT NULL DEFAULT '',
                detail_url TEXT NOT NULL DEFAULT '',
                page_url TEXT NOT NULL DEFAULT '',
                page_title TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL,
                UNIQUE(code, action_type)
            );

            CREATE INDEX IF NOT EXISTS idx_sticker_code ON sticker_records(code);
            CREATE INDEX IF NOT EXISTS idx_sticker_action ON sticker_records(action_type);

            CREATE TABLE IF NOT EXISTS blocked_series (
                series TEXT PRIMARY KEY,
                reason TEXT NOT NULL DEFAULT '',
                page_url TEXT NOT NULL DEFAULT '',
                page_title TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS blocked_title_keywords (
                keyword TEXT PRIMARY KEY,
                page_url TEXT NOT NULL DEFAULT '',
                page_title TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL
            );
            """
        )


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "code": row["code"],
        "title": row["title"],
        "release_date": row["release_date"],
        "detail_url": row["detail_url"],
        "page_url": row["page_url"],
        "page_title": row["page_title"],
        "reason": row["reason"],
        "recorded_at": row["recorded_at"],
    }


def _series_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "series": row["series"],
        "reason": row["reason"],
        "page_url": row["page_url"],
        "page_title": row["page_title"],
        "recorded_at": row["recorded_at"],
    }


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


def record_blocked_series(payload: dict[str, Any]) -> dict[str, Any]:
    init_sticker_db()
    series = normalize_series(str(payload.get("series") or payload.get("code") or ""))
    if not series:
        raise ValueError("series_required")

    row = {
        "series": series,
        "reason": str(payload.get("reason") or ""),
        "page_url": str(payload.get("page_url") or ""),
        "page_title": str(payload.get("page_title") or ""),
        "recorded_at": str(payload.get("recorded_at") or _now_iso()),
    }

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO blocked_series (series, reason, page_url, page_title, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(series) DO UPDATE SET
                reason = excluded.reason,
                page_url = excluded.page_url,
                page_title = excluded.page_title,
                recorded_at = excluded.recorded_at
            """,
            (
                row["series"],
                row["reason"],
                row["page_url"],
                row["page_title"],
                row["recorded_at"],
            ),
        )
        conn.commit()

    _rewrite_blocked_series_txt()
    return row


def remove_blocked_series(series: str) -> None:
    init_sticker_db()
    normalized = normalize_series(series)
    if not normalized:
        return

    with get_connection() as conn:
        conn.execute("DELETE FROM blocked_series WHERE series = ?", (normalized,))
        conn.commit()

    _rewrite_blocked_series_txt()


def _rewrite_blocked_series_txt() -> None:
    init_sticker_db()
    txt_dir = get_txt_dir()
    txt_dir.mkdir(parents=True, exist_ok=True)
    path = txt_dir / BLOCKED_SERIES_TXT

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT series, reason, page_url, page_title, recorded_at
            FROM blocked_series
            ORDER BY recorded_at DESC, series ASC
            """
        ).fetchall()

    lines = [
        f"# JAV Manager — {BLOCKED_SERIES_TXT}",
        f"# 目录: {path}",
        f"# 更新: {_now_iso()}",
        "# 格式: 系列 | 原因 | 页面 | 记录时间",
        "",
    ]
    for row in rows:
        parts = [
            row["series"],
            f"原因:{row['reason'] or '-'}",
            f"页面:{row['page_url'] or '-'}",
            f"记录:{row['recorded_at']}",
        ]
        lines.append(" | ".join(parts))
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote blocked series list: %s (%d records)", path, len(rows))


def get_blocked_series_list() -> list[dict[str, Any]]:
    init_sticker_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT series, reason, page_url, page_title, recorded_at
            FROM blocked_series
            ORDER BY recorded_at DESC
            """
        ).fetchall()
    return [_series_row_to_dict(row) for row in rows]


def normalize_title_keyword(raw: str) -> str:
    return str(raw or "").strip()


def _title_keyword_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "keyword": row["keyword"],
        "page_url": row["page_url"],
        "page_title": row["page_title"],
        "recorded_at": row["recorded_at"],
    }


def record_blocked_title_keyword(payload: dict[str, Any]) -> dict[str, Any]:
    init_sticker_db()
    keyword = normalize_title_keyword(str(payload.get("keyword") or ""))
    if not keyword:
        raise ValueError("keyword_required")

    row = {
        "keyword": keyword,
        "page_url": str(payload.get("page_url") or ""),
        "page_title": str(payload.get("page_title") or ""),
        "recorded_at": str(payload.get("recorded_at") or _now_iso()),
    }

    with get_connection() as conn:
        existing = conn.execute(
            "SELECT keyword FROM blocked_title_keywords WHERE LOWER(keyword) = LOWER(?)",
            (keyword,),
        ).fetchone()
        if existing:
            row["keyword"] = existing["keyword"]

        conn.execute(
            """
            INSERT INTO blocked_title_keywords (keyword, page_url, page_title, recorded_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(keyword) DO UPDATE SET
                page_url = excluded.page_url,
                page_title = excluded.page_title,
                recorded_at = excluded.recorded_at
            """,
            (
                row["keyword"],
                row["page_url"],
                row["page_title"],
                row["recorded_at"],
            ),
        )
        conn.commit()

    _rewrite_blocked_title_keywords_txt()
    return row


def remove_blocked_title_keyword(keyword: str) -> None:
    init_sticker_db()
    normalized = normalize_title_keyword(keyword)
    if not normalized:
        return

    with get_connection() as conn:
        conn.execute(
            "DELETE FROM blocked_title_keywords WHERE LOWER(keyword) = LOWER(?)",
            (normalized,),
        )
        conn.commit()

    _rewrite_blocked_title_keywords_txt()


def _rewrite_blocked_title_keywords_txt() -> None:
    init_sticker_db()
    txt_dir = get_txt_dir()
    txt_dir.mkdir(parents=True, exist_ok=True)
    path = txt_dir / BLOCKED_TITLE_KEYWORDS_TXT

    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT keyword, page_url, page_title, recorded_at
            FROM blocked_title_keywords
            ORDER BY recorded_at DESC, keyword ASC
            """
        ).fetchall()

    lines = [
        f"# JAV Manager — {BLOCKED_TITLE_KEYWORDS_TXT}",
        f"# 目录: {path}",
        f"# 更新: {_now_iso()}",
        "# 格式: 关键词 | 页面 | 记录时间",
        "",
    ]
    for row in rows:
        parts = [
            row["keyword"],
            f"页面:{row['page_url'] or '-'}",
            f"记录:{row['recorded_at']}",
        ]
        lines.append(" | ".join(parts))
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote blocked title keywords list: %s (%d records)", path, len(rows))


def get_blocked_title_keywords_list() -> list[dict[str, Any]]:
    init_sticker_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT keyword, page_url, page_title, recorded_at
            FROM blocked_title_keywords
            ORDER BY recorded_at DESC, keyword ASC
            """
        ).fetchall()
    return [_title_keyword_row_to_dict(row) for row in rows]


def get_txt_dir() -> Path:
    """Directory where sticker list txt files are written (exe / project root)."""
    return Path(get_project_root())


EXCLUSIVE_STICKER_ACTIONS = (
    ACTION_BLOCKED,
    ACTION_VERIFIED,
    ACTION_DOWNLOADED,
    ACTION_MARKED,
)


def _clear_other_exclusive_actions(code: str, keep_action: str) -> None:
    normalized = code.strip().upper()
    if not normalized:
        return
    with get_connection() as conn:
        for action_type in EXCLUSIVE_STICKER_ACTIONS:
            if action_type == keep_action:
                continue
            conn.execute(
                "DELETE FROM sticker_records WHERE code = ? AND action_type = ?",
                (normalized, action_type),
            )
        conn.commit()


def record_sticker_action(action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Insert or update a sticker record. Returns the stored row."""
    code = str(payload.get("code", "")).strip().upper()
    if action_type in EXCLUSIVE_STICKER_ACTIONS and code:
        _clear_other_exclusive_actions(code, action_type)
    row = _upsert_record(action_type, payload)
    if action_type in EXCLUSIVE_STICKER_ACTIONS:
        for other in EXCLUSIVE_STICKER_ACTIONS:
            if other in TXT_FILENAMES and other != action_type:
                _rewrite_txt(other)
    if action_type in TXT_FILENAMES:
        _rewrite_txt(action_type)
    return row


def _upsert_record(action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    init_sticker_db()
    code = str(payload.get("code", "")).strip().upper()
    if not code:
        raise ValueError("code_required")

    recorded_at = str(payload.get("recorded_at") or _now_iso())
    row = {
        "code": code,
        "action_type": action_type,
        "title": str(payload.get("title") or ""),
        "release_date": str(payload.get("release_date") or ""),
        "detail_url": str(payload.get("detail_url") or ""),
        "page_url": str(payload.get("page_url") or ""),
        "page_title": str(payload.get("page_title") or ""),
        "reason": str(payload.get("reason") or ""),
        "recorded_at": recorded_at,
    }

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO sticker_records (
                code, action_type, title, release_date, detail_url,
                page_url, page_title, reason, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(code, action_type) DO UPDATE SET
                title = excluded.title,
                release_date = excluded.release_date,
                detail_url = excluded.detail_url,
                page_url = excluded.page_url,
                page_title = excluded.page_title,
                reason = excluded.reason,
                recorded_at = excluded.recorded_at
            """,
            (
                row["code"],
                row["action_type"],
                row["title"],
                row["release_date"],
                row["detail_url"],
                row["page_url"],
                row["page_title"],
                row["reason"],
                row["recorded_at"],
            ),
        )
        conn.commit()

    return {k: v for k, v in row.items() if k != "action_type"}


def import_bulk_from_extension(data: dict[str, Any]) -> int:
    """Merge extension-local sticker data into the desktop database."""
    init_sticker_db()
    mapping = {
        "blocked": ACTION_BLOCKED,
        "verified": ACTION_VERIFIED,
        "downloaded": ACTION_DOWNLOADED,
        "marked": ACTION_MARKED,
    }
    count = 0
    for key, action_type in mapping.items():
        entries = data.get(key) or {}
        if not isinstance(entries, dict):
            continue
        for code, record in entries.items():
            if not record:
                continue
            payload = dict(record)
            payload["code"] = str(payload.get("code") or code).strip().upper()
            if not payload["code"]:
                continue
            _upsert_record(action_type, payload)
            count += 1

    series_entries = data.get("blockedSeries") or {}
    if isinstance(series_entries, dict):
        for series, record in series_entries.items():
            if not record:
                continue
            payload = dict(record)
            payload["series"] = str(payload.get("series") or series).strip()
            if not payload["series"]:
                continue
            record_blocked_series(payload)
            count += 1

    keyword_entries = data.get("blockedTitleKeywords") or {}
    if isinstance(keyword_entries, dict):
        for keyword, record in keyword_entries.items():
            if not record:
                continue
            payload = dict(record)
            payload["keyword"] = str(payload.get("keyword") or keyword).strip()
            if not payload["keyword"]:
                continue
            record_blocked_title_keyword(payload)
            count += 1

    from src.actress_profile_store import import_profile_bulk_from_extension

    count += import_profile_bulk_from_extension(data)

    from src.pending_download_store import record_pending_download_actress

    pending_entries = data.get("pendingDownloadActresses") or {}
    if isinstance(pending_entries, dict):
        for javdb_id, record in pending_entries.items():
            if not record:
                continue
            payload = dict(record)
            payload["javdb_id"] = str(payload.get("javdb_id") or javdb_id).strip()
            if not payload["javdb_id"]:
                continue
            record_pending_download_actress(payload)
            count += 1

    regenerate_all_txt_files()
    return count


def regenerate_all_txt_files() -> None:
    """Rewrite all sticker list txt files from the database."""
    init_sticker_db()
    for action_type in LIST_ACTIONS:
        _rewrite_txt(action_type)
    _rewrite_blocked_series_txt()
    _rewrite_blocked_title_keywords_txt()


def remove_sticker_action(action_type: str, code: str) -> None:
    init_sticker_db()
    normalized = code.strip().upper()
    if not normalized:
        return

    with get_connection() as conn:
        conn.execute(
            "DELETE FROM sticker_records WHERE code = ? AND action_type = ?",
            (normalized, action_type),
        )
        conn.commit()

    if action_type in TXT_FILENAMES:
        _rewrite_txt(action_type)


def _format_txt_line(row: sqlite3.Row) -> str:
    parts = [
        row["code"],
        row["title"] or "-",
        f"日期:{row['release_date'] or '-'}",
        f"详情:{row['detail_url'] or '-'}",
        f"页面:{row['page_url'] or '-'}",
        f"记录:{row['recorded_at']}",
    ]
    if row["action_type"] == ACTION_BLOCKED and row["reason"]:
        parts.insert(3, f"原因:{row['reason']}")
    return " | ".join(parts)


def _rewrite_txt(action_type: str) -> None:
    filename = TXT_FILENAMES.get(action_type)
    if not filename:
        return

    txt_dir = get_txt_dir()
    txt_dir.mkdir(parents=True, exist_ok=True)
    path = txt_dir / filename
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT code, action_type, title, release_date, detail_url,
                   page_url, page_title, reason, recorded_at
            FROM sticker_records
            WHERE action_type = ?
            ORDER BY recorded_at DESC, code ASC
            """,
            (action_type,),
        ).fetchall()

    lines = [
        f"# JAV Manager — {filename}",
        f"# 目录: {path}",
        f"# 更新: {_now_iso()}",
        "",
    ]
    lines.extend(_format_txt_line(row) for row in rows)
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote sticker list: %s (%d records)", path, len(rows))


def get_sync_payload() -> dict[str, list[dict[str, Any]]]:
    init_sticker_db()
    result: dict[str, list[dict[str, Any]]] = {
        ACTION_BLOCKED: [],
        ACTION_VERIFIED: [],
        ACTION_DOWNLOADED: [],
        ACTION_MARKED: [],
        "blocked_series": [],
        "blocked_title_keywords": [],
    }

    with get_connection() as conn:
        for action_type in LIST_ACTIONS + (ACTION_MARKED,):
            rows = conn.execute(
                """
                SELECT code, title, release_date, detail_url, page_url,
                       page_title, reason, recorded_at
                FROM sticker_records
                WHERE action_type = ?
                ORDER BY recorded_at DESC
                """,
                (action_type,),
            ).fetchall()
            result[action_type] = [_row_to_dict(row) for row in rows]

    result["blocked_series"] = get_blocked_series_list()
    result["blocked_title_keywords"] = get_blocked_title_keywords_list()

    from src.actress_profile_store import (
        get_blocked_actress_series_list,
        get_blocked_actresses_list,
        get_mediocre_actresses_list,
    )

    result["blocked_actresses"] = get_blocked_actresses_list()
    result["blocked_actress_series"] = get_blocked_actress_series_list()
    result["mediocre_actresses"] = get_mediocre_actresses_list()

    from src.pending_download_store import get_pending_download_actresses_list

    result["pending_download_actresses"] = get_pending_download_actresses_list()

    from src.magnet_saved_actress_store import get_magnet_saved_actresses_list

    result["magnet_saved_actresses"] = get_magnet_saved_actresses_list()

    from src.magnet_saved_video_store import get_magnet_saved_videos_list

    result["magnet_saved_videos"] = get_magnet_saved_videos_list()

    from src.video_downloaded_actress_store import get_video_downloaded_actresses_list
    from src.video_downloaded_video_store import get_video_downloaded_videos_list

    result["video_downloaded_actresses"] = get_video_downloaded_actresses_list()
    result["video_downloaded_videos"] = get_video_downloaded_videos_list()

    from src.video_cracked_actress_store import get_video_cracked_actresses_list
    from src.video_cracked_video_store import get_video_cracked_videos_list

    result["video_cracked_actresses"] = get_video_cracked_actresses_list()
    result["video_cracked_videos"] = get_video_cracked_videos_list()

    from src.catalog_db import list_all_catalog_entries

    result["catalog_entries"] = list_all_catalog_entries()

    from src.actress_store import list_collected_actresses

    result["collected_actresses"] = list_collected_actresses()
    return result
