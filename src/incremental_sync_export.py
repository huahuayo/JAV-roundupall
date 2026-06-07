"""Finalize one actress folder immediately after each sync step completes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.magnet_saved_scanner import apply_magnet_saved_folder_renames
from src.magnet_saved_store import write_magnet_saved_folder_log
from src.pending_download_scanner import PENDING_DOWNLOAD_KEY, apply_synced_folder_renames
from src.actress_folder_store import record_actress_folder_from_sync_result
from src.sync_folder_rename import apply_sync_folder_renames
from src.video_cracked_scanner import VIDEO_CRACKED_KEY
from src.video_downloaded_scanner import VIDEO_DOWNLOADED_KEY
from src.video_cracked_store import write_video_cracked_folder_log
from src.video_downloaded_store import write_video_downloaded_folder_log
from src.catalog_reader import append_catalog_entries
from src.no_subtitle_txt import write_folder_no_subtitle_txt
from src.video_metadata_store import apply_metadata_exports


def _folder_key(folder_path: str) -> str:
    return str(folder_path or "").strip().casefold()


def finalize_magnet_saved_folder(folder_result: dict[str, Any], *, session_id: str) -> dict[str, Any]:
    item = dict(folder_result or {})
    items = apply_magnet_saved_folder_renames([item])
    item = items[0] if items else item
    folder_path = str(item.get("folder_path") or "").strip()
    if folder_path:
        actress = item.get("actress") or {}
        folder_log = write_magnet_saved_folder_log(
            folder_path,
            session_id=session_id,
            actress_name=str(actress.get("name") or item.get("folder_name") or ""),
            code_results=item.get("code_results") or [],
        )
        if folder_log:
            item["folder_log_path"] = folder_log
        write_folder_no_subtitle_txt(folder_path, item.get("code_results") or [])
    record_actress_folder_from_sync_result(item, "magnet_saved")
    return item


def finalize_video_downloaded_folder(folder_result: dict[str, Any], *, session_id: str) -> dict[str, Any]:
    item = dict(folder_result or {})
    items = apply_sync_folder_renames([item])
    item = items[0] if items else item
    folder_path = str(item.get("folder_path") or "").strip()
    if folder_path:
        actress = item.get("actress") or {}
        folder_log = write_video_downloaded_folder_log(
            folder_path,
            session_id=session_id,
            actress_name=str(actress.get("name") or item.get("folder_name") or ""),
            code_results=item.get("code_results") or [],
        )
        if folder_log:
            item["folder_log_path"] = folder_log
        append_catalog_entries(
            folder_path,
            actress_name=str(actress.get("name") or item.get("actress_match_name") or item.get("folder_name") or ""),
            rows=[row for row in (item.get("code_results") or []) if row.get("ok")],
        )
        write_folder_no_subtitle_txt(folder_path, item.get("code_results") or [])
    record_actress_folder_from_sync_result(item, VIDEO_DOWNLOADED_KEY)
    return item


def finalize_video_cracked_folder(folder_result: dict[str, Any], *, session_id: str) -> dict[str, Any]:
    item = dict(folder_result or {})
    items = apply_sync_folder_renames([item])
    item = items[0] if items else item
    folder_path = str(item.get("folder_path") or "").strip()
    if folder_path:
        actress = item.get("actress") or {}
        folder_log = write_video_cracked_folder_log(
            folder_path,
            session_id=session_id,
            actress_name=str(actress.get("name") or item.get("folder_name") or ""),
            code_results=item.get("code_results") or [],
        )
        if folder_log:
            item["folder_log_path"] = folder_log
        append_catalog_entries(
            folder_path,
            actress_name=str(actress.get("name") or item.get("actress_match_name") or item.get("folder_name") or ""),
            rows=[row for row in (item.get("code_results") or []) if row.get("ok")],
        )
        write_folder_no_subtitle_txt(folder_path, item.get("code_results") or [])
    record_actress_folder_from_sync_result(item, VIDEO_CRACKED_KEY)
    return item


def finalize_pending_download_folder(folder_result: dict[str, Any], *, session_id: str) -> dict[str, Any]:
    item = dict(folder_result or {})
    items = apply_synced_folder_renames([item])
    item = items[0] if items else item
    folder_path = str(item.get("folder_path") or "").strip()
    if folder_path:
        folder_log = write_pending_download_folder_log(folder_path, session_id=session_id, result=item)
        if folder_log:
            item["folder_log_path"] = folder_log
    record_actress_folder_from_sync_result(item, PENDING_DOWNLOAD_KEY)
    return item

def finalize_metadata_folder(
    folder_result: dict[str, Any],
    *,
    library_kind: str,
    download_media: bool = True,
) -> dict[str, Any]:
    items = apply_metadata_exports(
        [dict(folder_result or {})],
        library_kind=library_kind,
        download_media=download_media,
    )
    return items[0] if items else dict(folder_result or {})


def write_pending_download_folder_log(folder_path: str, *, session_id: str, result: dict[str, Any]) -> str:
    path = Path(folder_path)
    if not path.is_dir():
        return ""

    stamp = session_id or ""
    log_path = path / f"待下载同步记录_{stamp}.txt"
    actress = result.get("actress") or {}
    if result.get("ok") and result.get("marked"):
        status = "成功"
        detail = "已在女优页标记「待下载」"
        rename_msg = str(result.get("rename_message") or "")
        if rename_msg:
            detail += f"；{rename_msg}"
    else:
        status = "失败"
        detail = str(result.get("error") or "收藏女优中未找到")

    lines = [
        "# JAV Manager — 待下载同步记录",
        f"# 女优文件夹: {path.name}",
        f"# 会话: {stamp}",
        f"# 状态: {status}",
        f"# javdb_id: {actress.get('javdb_id') or '-'}",
        f"# 女优: {actress.get('name') or '-'}",
        f"# 说明: {detail}",
        "",
    ]
    try:
        log_path.write_text("\n".join(lines), encoding="utf-8")
        return str(log_path)
    except OSError:
        return ""
