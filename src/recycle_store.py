"""Recycle bin: move deleted videos to folder-local 回收站 and track restore."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.sticker_store import get_connection

RECYCLE_DIRNAME = "回收站"
SETTINGS_AUTO_DAYS = "recycle_auto_cleanup_days"


def init_recycle_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS recycle_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                folder_path TEXT NOT NULL DEFAULT '',
                recycle_path TEXT NOT NULL DEFAULT '',
                moved_files TEXT NOT NULL DEFAULT '[]',
                reason TEXT NOT NULL DEFAULT '',
                deleted_at TEXT NOT NULL,
                restored INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_recycle_deleted ON recycle_items(deleted_at);
            CREATE INDEX IF NOT EXISTS idx_recycle_restored ON recycle_items(restored);

            CREATE TABLE IF NOT EXISTS recycle_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL DEFAULT ''
            );
            """
        )


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_auto_cleanup_days(default: int = 30) -> int:
    init_recycle_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT value FROM recycle_settings WHERE key = ?",
            (SETTINGS_AUTO_DAYS,),
        ).fetchone()
    if not row:
        return default
    try:
        return max(int(str(row["value"])), 0)
    except ValueError:
        return default


def set_auto_cleanup_days(days: int) -> None:
    init_recycle_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO recycle_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (SETTINGS_AUTO_DAYS, str(max(int(days), 0))),
        )
        conn.commit()


def list_recycle_items(*, include_restored: bool = False) -> list[dict[str, Any]]:
    init_recycle_db()
    query = """
        SELECT id, code, title, folder_path, recycle_path, moved_files, reason, deleted_at, restored
        FROM recycle_items
    """
    if not include_restored:
        query += " WHERE restored = 0"
    query += " ORDER BY deleted_at DESC, id DESC"
    with get_connection() as conn:
        rows = conn.execute(query).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["moved_files"] = json.loads(str(item.get("moved_files") or "[]"))
        except json.JSONDecodeError:
            item["moved_files"] = []
        out.append(item)
    return out


def move_video_to_recycle(
    *,
    code: str,
    title: str,
    folder_path: str,
    video_path: str,
    reason: str,
    extra_paths: list[str] | None = None,
) -> dict[str, Any]:
    init_recycle_db()
    root = Path(folder_path)
    if not root.is_dir():
        raise FileNotFoundError(f"找不到影片目录: {folder_path}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    recycle_root = root / RECYCLE_DIRNAME
    recycle_root.mkdir(parents=True, exist_ok=True)
    dest_dir = recycle_root / f"{code}_{stamp}"
    dest_dir.mkdir(parents=True, exist_ok=True)

    candidates = [video_path, *(extra_paths or [])]
    moved: list[dict[str, str]] = []
    for raw in candidates:
        src = Path(str(raw or ""))
        if not src.is_file():
            continue
        target = dest_dir / src.name
        if target.exists():
            target = dest_dir / f"{stamp}_{src.name}"
        shutil.move(str(src), str(target))
        moved.append({"original": str(src), "recycle": str(target)})

    if not moved:
        try:
            dest_dir.rmdir()
        except OSError:
            pass
        raise FileNotFoundError("没有可移动到回收站的文件")

    with get_connection() as conn:
        cur = conn.execute(
            """
            INSERT INTO recycle_items (
                code, title, folder_path, recycle_path, moved_files, reason, deleted_at, restored
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                code,
                title,
                str(root),
                str(dest_dir),
                json.dumps(moved, ensure_ascii=False),
                reason,
                _now(),
            ),
        )
        conn.commit()
        item_id = int(cur.lastrowid)
    return {"ok": True, "id": item_id, "recycle_path": str(dest_dir), "moved": moved}


def restore_recycle_item(item_id: int) -> dict[str, Any]:
    init_recycle_db()
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM recycle_items WHERE id = ? AND restored = 0",
            (item_id,),
        ).fetchone()
        if not row:
            return {"ok": False, "message": "记录不存在或已恢复"}
        try:
            moved = json.loads(str(row["moved_files"] or "[]"))
        except json.JSONDecodeError:
            moved = []
        restored_count = 0
        for entry in moved:
            src = Path(str(entry.get("recycle") or ""))
            dst = Path(str(entry.get("original") or ""))
            if not src.is_file():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists():
                dst = dst.parent / f"restored_{dst.name}"
            shutil.move(str(src), str(dst))
            restored_count += 1
        conn.execute("UPDATE recycle_items SET restored = 1 WHERE id = ?", (item_id,))
        conn.commit()
    recycle_path = Path(str(row["recycle_path"]))
    if recycle_path.is_dir() and not any(recycle_path.iterdir()):
        recycle_path.rmdir()
    return {"ok": True, "restored_count": restored_count}


def clear_recycle_bin(*, delete_files: bool = True) -> int:
    init_recycle_db()
    items = list_recycle_items(include_restored=False)
    removed = 0
    for item in items:
        if delete_files:
            recycle_path = Path(str(item.get("recycle_path") or ""))
            if recycle_path.is_dir():
                shutil.rmtree(recycle_path, ignore_errors=True)
        with get_connection() as conn:
            conn.execute("DELETE FROM recycle_items WHERE id = ?", (int(item["id"]),))
            conn.commit()
        removed += 1
    return removed


def run_auto_cleanup() -> int:
    days = get_auto_cleanup_days()
    if days <= 0:
        return 0
    cutoff = datetime.now() - timedelta(days=days)
    removed = 0
    for item in list_recycle_items(include_restored=False):
        deleted_at = str(item.get("deleted_at") or "")
        try:
            when = datetime.strptime(deleted_at, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        if when > cutoff:
            continue
        recycle_path = Path(str(item.get("recycle_path") or ""))
        if recycle_path.is_dir():
            shutil.rmtree(recycle_path, ignore_errors=True)
        with get_connection() as conn:
            conn.execute("DELETE FROM recycle_items WHERE id = ?", (int(item["id"]),))
            conn.commit()
        removed += 1
    return removed
