"""Shared post-sync actress folder rename utilities."""

from __future__ import annotations

import re
from pathlib import Path

SYNC_COMPLETE_PREFIX = "完成 "
SYNC_PARTIAL_PREFIX = re.compile(r"^!(\d+)\s+")
PENDING_SYNCED_PREFIX = re.compile(r"^1\s+")


def strip_sync_status_prefix(name: str) -> str:
    text = str(name or "").strip()
    if text.startswith(SYNC_COMPLETE_PREFIX):
        return text[len(SYNC_COMPLETE_PREFIX) :].strip()
    match = SYNC_PARTIAL_PREFIX.match(text)
    if match:
        return text[match.end() :].strip()
    pending = PENDING_SYNCED_PREFIX.match(text)
    if pending:
        return text[pending.end() :].strip()
    return text


def is_sync_complete_folder(name: str) -> bool:
    """Return True when folder is already fully synced (prefixed with 完成)."""
    return str(name or "").startswith(SYNC_COMPLETE_PREFIX)


def rename_sync_folder(folder_path: str, *, fail_count: int) -> tuple[bool, str, str]:
    """Rename folder to `完成 …` when all ok, or `!N …` when N codes failed."""
    path = Path(str(folder_path or "").strip())
    if not path.is_dir():
        return False, "", "文件夹不存在"

    base_name = strip_sync_status_prefix(path.name)
    if fail_count <= 0:
        new_name = f"{SYNC_COMPLETE_PREFIX}{base_name}"
        message = "已重命名为 完成 …"
    else:
        new_name = f"!{fail_count} {base_name}"
        message = f"已重命名为 !{fail_count} …"

    if path.name == new_name:
        return True, str(path.resolve()), "已是目标命名"

    new_path = path.parent / new_name
    if new_path.exists():
        return False, "", f"目标已存在: {new_name}"

    path.rename(new_path)
    return True, str(new_path.resolve()), message


def apply_sync_folder_renames(folder_results: list[dict]) -> list[dict]:
    """Rename actress folders after sync: 完成 (all ok) or !N (N failures)."""
    for item in folder_results:
        total = int(item.get("total_codes") or 0)
        if total <= 0:
            continue

        fail = int(item.get("fail_codes") or 0)
        folder_path = str(item.get("folder_path") or "").strip()
        if not folder_path:
            continue

        ok, new_path, message = rename_sync_folder(folder_path, fail_count=fail)
        item["renamed"] = ok
        item["new_folder_path"] = new_path
        item["rename_message"] = message
        item["synced"] = fail == 0
        if ok and new_path:
            item["folder_path"] = new_path
            item["folder_name"] = Path(new_path).name
            if new_path != folder_path:
                from src.catalog_db import rebind_catalog_folder

                rebind_catalog_folder(folder_path, new_path)
    return folder_results
