"""Export per-folder metadata: 目录.txt, 封面/{番号}/, 元数据/."""

from __future__ import annotations

import base64
import logging
import re
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.catalog_reader import CATALOG_FILENAME, upsert_catalog_rows
from src.parser import CRACK_STATUS_LABELS, normalize_code

logger = logging.getLogger(__name__)

COVERS_DIRNAME = "封面"
PREVIEWS_DIRNAME = "封面预览图"  # legacy, previews now live under 封面/{番号}/
METADATA_DIRNAME = "元数据"
LEGACY_METADATA_DIRNAME = "命名元数据"
INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
MULTISPACE = re.compile(r"\s+")

LIBRARY_DOWNLOADED = "video_downloaded"
LIBRARY_CRACKED = "video_cracked"


def sanitize_filename(name: str, *, max_len: int = 180) -> str:
    text = INVALID_FILENAME_CHARS.sub("_", str(name or "").strip())
    text = MULTISPACE.sub(" ", text).strip(" .")
    if not text:
        return "_"
    if len(text) > max_len:
        return text[:max_len].rstrip(" .")
    return text


def resolve_local_file_path(row: dict[str, Any], folder_root: Path) -> str:
    source_path = str(row.get("source_path") or "").strip()
    if source_path:
        return source_path
    source_file = str(row.get("source_file") or "").strip()
    if not source_file:
        return ""
    candidate = folder_root / source_file
    if candidate.is_file():
        return str(candidate.resolve())
    return source_file


def _now_date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _now_datetime() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _cover_extension(cover_url: str) -> str:
    path = urlparse(str(cover_url or "")).path.lower()
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        if path.endswith(ext):
            return ext if ext != ".jpeg" else ".jpg"
    return ".jpg"


def write_metadata_asset(folder_path: str, relative_path: str, content_base64: str) -> dict[str, Any]:
    root = Path(folder_path)
    if not root.is_dir():
        return {"ok": False, "message": "folder_not_found"}

    rel = str(relative_path or "").replace("\\", "/").strip().lstrip("/")
    if not rel or ".." in rel.split("/"):
        return {"ok": False, "message": "invalid_relative_path"}

    dest = root / rel
    if dest.is_file():
        return {"ok": True, "path": str(dest), "skipped": True}

    try:
        data = base64.b64decode(str(content_base64 or ""), validate=False)
    except (ValueError, TypeError):
        return {"ok": False, "message": "invalid_base64"}
    if not data:
        return {"ok": False, "message": "empty_content"}

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        dest.write_bytes(data)
        return {"ok": True, "path": str(dest)}
    except OSError as exc:
        logger.warning("Failed to write metadata asset %s: %s", dest, exc)
        return {"ok": False, "message": str(exc)}


def _download_image(url: str, dest: Path, *, referer: str = "") -> bool:
    image_url = str(url or "").strip()
    if not image_url:
        return False
    if dest.is_file():
        return True

    dest.parent.mkdir(parents=True, exist_ok=True)
    referers: list[str] = []
    for ref in (referer, "https://www.javbus.com/", "https://javdb.com/"):
        text = str(ref or "").strip()
        if text and text not in referers:
            referers.append(text)
    if not referers:
        referers.append("https://www.javbus.com/")

    for ref in referers:
        req = urllib.request.Request(
            image_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
                ),
                "Referer": ref,
                "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = resp.read()
            if not data:
                continue
            dest.write_bytes(data)
            return True
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            logger.warning("Image download failed %s -> %s (referer=%s): %s", image_url, dest, ref, exc)
    return False


def _append_row_note(row: dict[str, Any], note: str) -> None:
    text = str(note or "").strip()
    if not text:
        return
    existing = str(row.get("error") or "").strip()
    if text in existing:
        return
    row["error"] = f"{existing}；{text}" if existing else text


def _code_subfolder(row: dict[str, Any]) -> str:
    code = normalize_code(str(row.get("code") or ""))
    return sanitize_filename(code) if code else "_"


def _cover_media_dir(root: Path, row: dict[str, Any]) -> Path:
    return root / COVERS_DIRNAME / _code_subfolder(row)


def _cover_dest(root: Path, row: dict[str, Any]) -> Path:
    ext = _cover_extension(str(row.get("cover_url") or ""))
    return _cover_media_dir(root, row) / f"cover{ext}"


def _preview_dest(root: Path, row: dict[str, Any], index: int, preview_url: str) -> Path:
    ext = _cover_extension(preview_url)
    return _cover_media_dir(root, row) / f"{index:02d}{ext}"


def _summarize_local_media(root: Path, row: dict[str, Any]) -> tuple[str, str, list[str]]:
    media_dir = _cover_media_dir(root, row)
    rel_dir = f"{COVERS_DIRNAME}/{_code_subfolder(row)}"
    cover_file = ""
    preview_files: list[str] = []
    if not media_dir.is_dir():
        return rel_dir, cover_file, preview_files
    for path in sorted(media_dir.iterdir()):
        if not path.is_file():
            continue
        name = path.name
        lower = name.lower()
        if lower.startswith("cover."):
            cover_file = name
            continue
        if lower[:2].isdigit():
            preview_files.append(name)
    return rel_dir, cover_file, preview_files


def _metadata_file_path(root: Path, row: dict[str, Any], actress_name: str) -> Path:
    code = normalize_code(str(row.get("code") or ""))
    actress = str(row.get("actresses") or actress_name or "").split("、")[0].strip() or actress_name
    metadata_name = sanitize_filename(f"{code} {actress}") + ".txt"
    return _metadata_root(root) / metadata_name


def _is_metadata_done(root: Path, row: dict[str, Any], actress_name: str) -> bool:
    path = _metadata_file_path(root, row, actress_name)
    return path.is_file() and path.stat().st_size > 0


def _is_media_done(root: Path, row: dict[str, Any]) -> bool:
    _, cover_file, preview_files = _summarize_local_media(root, row)
    if not cover_file:
        return False
    preview_urls = row.get("preview_urls") or []
    if not isinstance(preview_urls, list):
        preview_urls = []
    expected = len([url for url in preview_urls if str(url or "").strip()])
    if expected == 0:
        return True
    return len(preview_files) >= expected


def _update_catalog_task_flags(
    root: Path,
    *,
    actress_name: str,
    rows: list[dict[str, Any]],
    update_metadata: bool = True,
    update_media: bool = True,
) -> int:
    updates: list[dict[str, Any]] = []
    for row in rows:
        code = normalize_code(str(row.get("code") or ""))
        if not code:
            continue
        entry: dict[str, Any] = {**row, "code": code}
        if update_metadata:
            entry["metadata_done"] = _is_metadata_done(root, row, actress_name)
        if update_media:
            entry["media_done"] = _is_media_done(root, row)
        updates.append(entry)
    if not updates:
        return 0
    return upsert_catalog_rows(root, actress_name=actress_name, rows=updates)


def _ensure_media_layout(root: Path, row: dict[str, Any], actress_name: str) -> None:
    del actress_name
    (root / COVERS_DIRNAME).mkdir(parents=True, exist_ok=True)
    _cover_media_dir(root, row).mkdir(parents=True, exist_ok=True)


def _image_referer(row: dict[str, Any]) -> str:
    cover_url = str(row.get("cover_url") or "").lower()
    javbus_url = str(row.get("javbus_url") or "").strip()
    detail_url = str(row.get("detail_url") or "").strip()
    if "javbus" in cover_url or "buscdn" in cover_url or "dmm.co.jp" in cover_url:
        return javbus_url or detail_url or "https://www.javbus.com/"
    return detail_url or javbus_url or "https://javdb.com/"


def _download_missing_media_assets(
    root: Path,
    *,
    actress_name: str,
    rows: list[dict[str, Any]],
) -> tuple[int, int]:
    covers_added = 0
    previews_added = 0
    referer_cache: dict[str, str] = {}

    for row in rows:
        if not row.get("ok"):
            continue
        code = normalize_code(str(row.get("code") or ""))
        if not code:
            continue

        referer = referer_cache.get(code) or _image_referer(row)
        referer_cache[code] = referer

        cover_url = str(row.get("cover_url") or "").strip()
        if cover_url:
            cover_dest = _cover_dest(root, row)
            if cover_dest.is_file():
                covers_added += 1
            elif _download_image(cover_url, cover_dest, referer=referer):
                covers_added += 1
            else:
                _append_row_note(row, "封面下载失败")

        preview_urls = row.get("preview_urls") or []
        if not isinstance(preview_urls, list):
            continue
        for index, preview_url in enumerate(preview_urls, start=1):
            url = str(preview_url or "").strip()
            if not url:
                continue
            preview_dest = _preview_dest(root, row, index, url)
            if preview_dest.is_file():
                previews_added += 1
                continue
            if _download_image(url, preview_dest, referer=referer):
                previews_added += 1
            else:
                _append_row_note(row, f"预览图{index:02d}下载失败")

        rel_dir, cover_file, preview_files = _summarize_local_media(root, row)
        row["cover_dir"] = rel_dir
        row["cover_file"] = cover_file
        row["preview_files"] = preview_files
        row["preview_count"] = len(preview_files)

    return covers_added, previews_added


def _metadata_root(folder_root: Path) -> Path:
    current = folder_root / METADATA_DIRNAME
    legacy = folder_root / LEGACY_METADATA_DIRNAME
    if legacy.is_dir() and not current.is_dir():
        try:
            legacy.rename(current)
        except OSError:
            return legacy
    return current


def _build_metadata_txt_lines(
    row: dict[str, Any],
    *,
    actress_name: str,
    library_kind: str,
    folder_root: Path,
) -> list[str]:
    cover_dir, cover_file, preview_files = _summarize_local_media(folder_root, row)
    preview_label = "、".join(preview_files) if preview_files else "-"
    lines = [
        f"番号: {row.get('code') or '-'}",
        f"标题: {row.get('title') or '-'}",
        f"女优: {row.get('actresses') or actress_name or '-'}",
        f"日期: {row.get('release_date') or row.get('releaseDate') or '-'}",
        f"时长: {row.get('duration') or '-'}",
        f"导演: {row.get('director') or '-'}",
        f"片商: {row.get('studio') or '-'}",
        f"系列: {row.get('series') or '-'}",
        f"评分: {row.get('rating') or '-'}",
        f"类别: {row.get('categories') or '-'}",
        f"详情页: {row.get('detail_url') or row.get('javbus_url') or '-'}",
        f"JavBus: {row.get('javbus_url') or '-'}",
        f"数据来源: {row.get('metadata_source') or '-'}",
        f"本地文件: {resolve_local_file_path(row, folder_root) or '-'}",
        f"有字幕: {'是' if row.get('has_subtitle') else '否'}",
        f"是否4K: {'是' if row.get('is_4k') else '否'}",
    ]
    if library_kind == LIBRARY_CRACKED:
        status = str(row.get("crack_status_label") or CRACK_STATUS_LABELS.get(str(row.get("crack_status") or ""), "-"))
        lines.extend(
            [
                f"是否: {'是' if row.get('has_uncensored_file') else '否'}",
                f"破解状态: {status}",
            ]
        )
    else:
        lines.append("是否: 否")
    lines.extend(
        [
            f"封面目录: {cover_dir or '-'}",
            f"封面文件: {cover_file or '-'}",
            f"预览图: {preview_label}",
            f"预览图数量: {len(preview_files) if preview_files else int(row.get('preview_count') or 0)}",
            f"记录时间: {_now_datetime()}",
        ]
    )
    if row.get("error"):
        lines.append(f"备注: {row.get('error')}")
    return lines


def export_folder_metadata(
    folder_path: str,
    *,
    actress_name: str,
    library_kind: str,
    code_results: list[dict[str, Any]],
    download_media: bool = True,
) -> dict[str, Any]:
    root = Path(folder_path)
    if not root.is_dir():
        return {
            "ok": False,
            "error": "文件夹不存在",
            "catalog_added": 0,
            "covers_added": 0,
            "previews_added": 0,
            "metadata_added": 0,
        }

    catalog_path = root / CATALOG_FILENAME
    metadata_root = _metadata_root(root)

    successful_rows = [row for row in code_results if row.get("ok") and normalize_code(str(row.get("code") or ""))]
    catalog_rows = [
        row
        for row in code_results
        if normalize_code(str(row.get("code") or ""))
        and (
            row.get("ok")
            or str(row.get("detail_url") or row.get("javbus_url") or "").strip()
        )
    ]

    metadata_added = 0
    metadata_updated = 0
    metadata_root.mkdir(parents=True, exist_ok=True)

    for row in successful_rows:
        _ensure_media_layout(root, row, actress_name)

    covers_added = 0
    previews_added = 0
    if download_media:
        covers_added, previews_added = _download_missing_media_assets(
            root,
            actress_name=actress_name,
            rows=successful_rows,
        )

    for row in catalog_rows:
        code = normalize_code(str(row.get("code") or ""))
        actress = str(row.get("actresses") or actress_name or "").split("、")[0].strip() or actress_name
        metadata_name = sanitize_filename(f"{code} {actress}") + ".txt"
        metadata_path = metadata_root / metadata_name
        should_write = row.get("ok") or not metadata_path.is_file()
        if not should_write:
            continue
        metadata_path.write_text(
            "\n".join(_build_metadata_txt_lines(row, actress_name=actress_name, library_kind=library_kind, folder_root=root)),
            encoding="utf-8",
        )
        if row.get("ok"):
            metadata_updated += 1
        else:
            metadata_added += 1

    catalog_updated = _update_catalog_task_flags(
        root,
        actress_name=actress_name,
        rows=catalog_rows,
        update_media=download_media,
    )

    return {
        "ok": True,
        "catalog_path": str(catalog_path),
        "catalog_added": catalog_updated,
        "catalog_skipped": 0,
        "covers_added": covers_added,
        "previews_added": previews_added,
        "metadata_added": metadata_added,
        "metadata_updated": metadata_updated,
        "metadata_dir": str(metadata_root),
        "media_download_pending": not download_media,
    }


def download_folder_metadata_assets(
    folder_path: str,
    *,
    actress_name: str,
    library_kind: str,
    code_results: list[dict[str, Any]],
) -> dict[str, Any]:
    root = Path(folder_path)
    if not root.is_dir():
        return {"ok": False, "covers_added": 0, "previews_added": 0}

    metadata_root = _metadata_root(root)
    successful_rows = [row for row in code_results if row.get("ok") and normalize_code(str(row.get("code") or ""))]
    catalog_rows = [
        row
        for row in code_results
        if normalize_code(str(row.get("code") or ""))
        and (
            row.get("ok")
            or str(row.get("detail_url") or row.get("javbus_url") or "").strip()
        )
    ]

    for row in successful_rows:
        _ensure_media_layout(root, row, actress_name)

    covers_added, previews_added = _download_missing_media_assets(
        root,
        actress_name=actress_name,
        rows=successful_rows,
    )

    metadata_updated = 0
    for row in catalog_rows:
        code = normalize_code(str(row.get("code") or ""))
        actress = str(row.get("actresses") or actress_name or "").split("、")[0].strip() or actress_name
        metadata_name = sanitize_filename(f"{code} {actress}") + ".txt"
        metadata_path = metadata_root / metadata_name
        if not metadata_path.is_file() and not row.get("ok"):
            continue
        metadata_path.write_text(
            "\n".join(_build_metadata_txt_lines(row, actress_name=actress_name, library_kind=library_kind, folder_root=root)),
            encoding="utf-8",
        )
        metadata_updated += 1

    catalog_media_updated = _update_catalog_task_flags(
        root,
        actress_name=actress_name,
        rows=catalog_rows,
        update_metadata=False,
        update_media=True,
    )

    return {
        "ok": True,
        "covers_added": covers_added,
        "previews_added": previews_added,
        "metadata_updated": metadata_updated,
        "catalog_media_updated": catalog_media_updated,
    }


def apply_metadata_exports(
    folder_results: list[dict[str, Any]],
    *,
    library_kind: str,
    download_media: bool = True,
) -> list[dict[str, Any]]:
    for item in folder_results:
        actress = item.get("actress") or {}
        actress_name = str(actress.get("name") or item.get("actress_match_name") or item.get("folder_name") or "")
        code_results = item.get("code_results") or []
        export_result = export_folder_metadata(
            str(item.get("folder_path") or ""),
            actress_name=actress_name,
            library_kind=library_kind,
            code_results=code_results if isinstance(code_results, list) else [],
            download_media=download_media,
        )
        item["metadata_export"] = export_result
    return folder_results
