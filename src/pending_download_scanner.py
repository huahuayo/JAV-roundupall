"""Scan pending-download library folders for actress directory names."""

from __future__ import annotations

from pathlib import Path

from src.library_location_settings import load_library_locations

PENDING_DOWNLOAD_KEY = "pending_download"
SYNCED_FOLDER_PREFIX = "1 "


def is_already_synced_folder(name: str) -> bool:
    return str(name or "").startswith(SYNCED_FOLDER_PREFIX)


def scan_pending_download_folders(roots: list[str] | None = None) -> tuple[list[dict[str, str]], list[str]]:
    """Return pending folder records and root paths that were scanned."""
    if roots is None:
        roots = load_library_locations().get(PENDING_DOWNLOAD_KEY, [])

    folders: list[dict[str, str]] = []
    valid_roots: list[str] = []
    seen_names: set[str] = set()

    for root in roots:
        root_path = Path(root)
        if not root_path.is_dir():
            continue
        valid_roots.append(str(root_path.resolve()))
        try:
            children = list(root_path.iterdir())
        except OSError:
            continue
        for child in children:
            if not child.is_dir():
                continue
            name = child.name.strip()
            if not name or name.startswith(".") or is_already_synced_folder(name):
                continue
            key = name.casefold()
            if key in seen_names:
                continue
            seen_names.add(key)
            folders.append(
                {
                    "folder_name": name,
                    "folder_path": str(child.resolve()),
                    "root": str(root_path.resolve()),
                }
            )

    return folders, valid_roots


def scan_pending_download_names(roots: list[str] | None = None) -> tuple[list[str], list[str]]:
    folders, valid_roots = scan_pending_download_folders(roots)
    return [item["folder_name"] for item in folders], valid_roots


def rename_synced_folder(folder_path: str) -> tuple[bool, str, str]:
    """Rename folder to `1 {original}`. Returns (ok, new_path, message)."""
    path = Path(str(folder_path or "").strip())
    if not path.is_dir():
        return False, "", "文件夹不存在"

    if is_already_synced_folder(path.name):
        return True, str(path.resolve()), "已是同步完成命名"

    new_path = path.parent / f"{SYNCED_FOLDER_PREFIX}{path.name}"
    if new_path.exists():
        return False, "", f"目标已存在: {new_path.name}"

    path.rename(new_path)
    return True, str(new_path.resolve()), "已重命名为 1 …"


def apply_synced_folder_renames(results: list[dict]) -> list[dict]:
    for item in results:
        if not (item.get("ok") and item.get("marked")):
            continue
        folder_path = str(item.get("folder_path") or "").strip()
        if not folder_path:
            continue
        ok, new_path, message = rename_synced_folder(folder_path)
        item["renamed"] = ok
        item["new_folder_path"] = new_path
        item["rename_message"] = message
        if ok and new_path:
            item["folder_path"] = new_path
            item["folder_name"] = Path(new_path).name
            if new_path != folder_path:
                from src.catalog_db import rebind_catalog_folder

                rebind_catalog_folder(folder_path, new_path)
    return results
