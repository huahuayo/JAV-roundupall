"""Persist pending-download actress marks and sync logs."""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from src.sticker_store import get_connection, init_sticker_db

logger = logging.getLogger(__name__)

SYNC_LOG_PREFIX = "待下载同步记录"


def init_pending_download_db() -> None:
    init_sticker_db()
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pending_download_actresses (
                javdb_id TEXT PRIMARY KEY,
                name TEXT NOT NULL DEFAULT '',
                folder_name TEXT NOT NULL DEFAULT '',
                profile_url TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_pending_download_name
                ON pending_download_actresses(name);
            """
        )


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def record_pending_download_actress(payload: dict[str, Any]) -> dict[str, Any]:
    init_pending_download_db()
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
            INSERT INTO pending_download_actresses (
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


def get_pending_download_actresses_list() -> list[dict[str, Any]]:
    init_pending_download_db()
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT javdb_id, name, folder_name, profile_url, recorded_at
            FROM pending_download_actresses
            ORDER BY recorded_at DESC, name ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def write_pending_download_sync_logs(
    log_roots: list[str],
    *,
    session_id: str,
    started_at: str,
    finished_at: str,
    scan_roots: list[str],
    folder_names: list[str],
    results: list[dict[str, Any]],
    error: str = "",
) -> list[str]:
    """Write sync log TXT under each pending-download root. Returns written paths."""
    written: list[str] = []
    stamp = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{SYNC_LOG_PREFIX}_{stamp}.txt"

    success_count = sum(1 for item in results if item.get("ok") and item.get("marked"))
    fail_count = len(results) - success_count

    for root in log_roots:
        root_path = Path(root)
        if not root_path.is_dir():
            continue
        path = root_path / filename
        lines = [
            f"# JAV Manager — {SYNC_LOG_PREFIX}",
            f"# 文件: {path}",
            f"# 会话: {session_id}",
            f"# 开始: {started_at}",
            f"# 结束: {finished_at}",
            f"# 扫描根目录: {', '.join(scan_roots) if scan_roots else '-'}",
            f"# 待对照文件夹: {len(folder_names)}  ·  成功: {success_count}  ·  失败/未匹配: {fail_count}",
            "# 格式: 文件夹名 | 状态 | javdb_id | 女优名 | 说明",
            "",
        ]
        if error:
            lines.append(f"# 整体错误: {error}")
            lines.append("")

        for item in results:
            folder_name = str(item.get("folder_name") or "-")
            if item.get("ok") and item.get("marked"):
                status = "成功"
                rename_msg = str(item.get("rename_message") or "")
                detail = "已在女优页标记「待下载」"
                if rename_msg:
                    detail += f"；{rename_msg}"
                elif item.get("renamed") is False:
                    detail += "；重命名失败"
            elif item.get("ok") and not item.get("marked"):
                status = "失败"
                detail = str(item.get("error") or "标记失败")
            elif item.get("ok"):
                status = "失败"
                detail = str(item.get("error") or "未知错误")
            else:
                status = "失败"
                detail = str(item.get("error") or "收藏女优中未找到")

            actress = item.get("actress") or {}
            javdb_id = str(actress.get("javdb_id") or item.get("javdb_id") or "-")
            actress_name = str(actress.get("name") or item.get("name") or "-")
            lines.append(f"{folder_name} | {status} | {javdb_id} | {actress_name} | {detail}")

        lines.append("")
        try:
            path.write_text("\n".join(lines), encoding="utf-8")
            written.append(str(path))
            logger.info("Wrote pending download sync log: %s", path)
        except OSError as exc:
            logger.warning("Failed to write sync log %s: %s", path, exc)

    return written
