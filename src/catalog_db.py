"""Persist per-folder catalog task state in the unified state database."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from src.catalog_reader import CatalogEntry
from src.parser import normalize_code
from src.state_db import get_state_connection, init_catalog_db


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _row_to_entry(row: Any) -> CatalogEntry:
    return CatalogEntry(
        code=str(row["code"]),
        title=str(row["title"] or "-"),
        detail_url=str(row["detail_url"] or "-"),
        local_file=str(row["local_file"] or "-"),
        date=str(row["added_date"] or "-"),
        metadata_done=bool(row["metadata_done"]),
        media_done=bool(row["media_done"]),
        javdb_done=bool(row["javdb_done"]),
    )


def read_catalog_from_db(folder_path: str | Path) -> dict[str, CatalogEntry]:
    init_catalog_db()
    key = str(folder_path or "").strip()
    if not key:
        return {}
    entries = _query_catalog_by_folder(key)
    if entries:
        return entries
    return _rebind_catalog_folder_by_actress(key)


def _query_catalog_by_folder(folder_path: str) -> dict[str, CatalogEntry]:
    with get_state_connection() as conn:
        rows = conn.execute(
            """
            SELECT code, title, detail_url, local_file, added_date,
                   metadata_done, media_done, javdb_done
            FROM catalog_entries
            WHERE folder_path = ?
            ORDER BY code
            """,
            (folder_path,),
        ).fetchall()
    return {str(row["code"]): _row_to_entry(row) for row in rows}


def _rebind_catalog_folder_by_actress(folder_path: str) -> dict[str, CatalogEntry]:
    from src.sync_folder_rename import strip_sync_status_prefix

    target = Path(folder_path)
    if not target.is_dir() and not target.parent.is_dir():
        return {}

    actress_name = strip_sync_status_prefix(target.name)
    if not actress_name:
        return {}
    with get_state_connection() as conn:
        old_rows = conn.execute(
            """
            SELECT DISTINCT folder_path
            FROM catalog_entries
            WHERE actress_name = ? COLLATE NOCASE
            """,
            (actress_name,),
        ).fetchall()
    old_paths = [str(row["folder_path"]) for row in old_rows if str(row["folder_path"]) != folder_path]
    if len(old_paths) != 1:
        return {}
    rebind_catalog_folder(old_paths[0], folder_path)
    return _query_catalog_by_folder(folder_path)


def rebind_catalog_folder(old_path: str | Path, new_path: str | Path) -> int:
    init_catalog_db()
    old_key = str(old_path or "").strip()
    new_key = str(new_path or "").strip()
    if not old_key or not new_key or old_key == new_key:
        return 0
    stamp = _now_iso()
    with get_state_connection() as conn:
        cur = conn.execute(
            """
            UPDATE catalog_entries
            SET folder_path = ?, updated_at = ?
            WHERE folder_path = ?
            """,
            (new_key, stamp, old_key),
        )
        conn.commit()
        return int(cur.rowcount or 0)


def replace_catalog_in_db(
    folder_path: str | Path,
    entries: dict[str, CatalogEntry],
    *,
    actress_name: str = "",
    library_kind: str = "",
) -> None:
    init_catalog_db()
    key = str(folder_path or "").strip()
    if not key:
        return
    stamp = _now_iso()
    with get_state_connection() as conn:
        conn.execute("DELETE FROM catalog_entries WHERE folder_path = ?", (key,))
        for code in sorted(entries.keys(), key=lambda item: item.upper()):
            entry = entries[code]
            conn.execute(
                """
                INSERT INTO catalog_entries (
                    folder_path, code, actress_name, library_kind, title, detail_url,
                    local_file, added_date, metadata_done, media_done, javdb_done, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    key,
                    entry.code,
                    actress_name or Path(key).name,
                    library_kind,
                    entry.title or "-",
                    entry.detail_url or "-",
                    entry.local_file or "-",
                    entry.date or "-",
                    int(entry.metadata_done),
                    int(entry.media_done),
                    int(entry.javdb_done),
                    stamp,
                ),
            )
        conn.commit()


def upsert_catalog_entries_in_db(
    folder_path: str | Path,
    entries: dict[str, CatalogEntry],
    *,
    actress_name: str = "",
    library_kind: str = "",
) -> int:
    init_catalog_db()
    key = str(folder_path or "").strip()
    if not key or not entries:
        return 0
    stamp = _now_iso()
    touched = 0
    with get_state_connection() as conn:
        for code, entry in entries.items():
            normalized = normalize_code(code)
            if not normalized:
                continue
            conn.execute(
                """
                INSERT INTO catalog_entries (
                    folder_path, code, actress_name, library_kind, title, detail_url,
                    local_file, added_date, metadata_done, media_done, javdb_done, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(folder_path, code) DO UPDATE SET
                    actress_name = excluded.actress_name,
                    library_kind = CASE
                        WHEN excluded.library_kind != '' THEN excluded.library_kind
                        ELSE catalog_entries.library_kind
                    END,
                    title = excluded.title,
                    detail_url = excluded.detail_url,
                    local_file = excluded.local_file,
                    added_date = CASE
                        WHEN excluded.added_date != '-' THEN excluded.added_date
                        ELSE catalog_entries.added_date
                    END,
                    metadata_done = excluded.metadata_done,
                    media_done = excluded.media_done,
                    javdb_done = excluded.javdb_done,
                    updated_at = excluded.updated_at
                """,
                (
                    key,
                    normalized,
                    actress_name or Path(key).name,
                    library_kind,
                    entry.title or "-",
                    entry.detail_url or "-",
                    entry.local_file or "-",
                    entry.date or "-",
                    int(entry.metadata_done),
                    int(entry.media_done),
                    int(entry.javdb_done),
                    stamp,
                ),
            )
            touched += 1
        conn.commit()
    return touched


def list_all_catalog_entries() -> list[dict[str, Any]]:
    init_catalog_db()
    with get_state_connection() as conn:
        rows = conn.execute(
            """
            SELECT folder_path, code, actress_name, library_kind, title, detail_url,
                   local_file, added_date, metadata_done, media_done, javdb_done, updated_at
            FROM catalog_entries
            ORDER BY folder_path, code
            """
        ).fetchall()
    return [dict(row) for row in rows]
