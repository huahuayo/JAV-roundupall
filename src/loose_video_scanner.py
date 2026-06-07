"""Scan loose-pending library roots for flat video files."""

from __future__ import annotations

from pathlib import Path

from src.catalog_reader import filter_pending_codes
from src.library_location_settings import load_library_locations
from src.magnet_saved_scanner import scan_folder_subtitle_codes
from src.parser import (
    code_sort_key,
    extract_actress_from_loose_filename,
    extract_code_from_text,
    has_cracked_subtitle_burned_in_filename,
    has_loose_uncensored_token,
    has_subtitle_in_filename,
    has_uncensored_marker_in_filename,
    is_4k_in_filename,
    normalize_code,
    resolve_video_crack_status,
    subtitle_marker_kind_in_filename,
)

LOOSE_PENDING_KEY = "loose_pending"
CLASSIFY_DIRNAME = "U字幕分类"
LOG_PREFIX = "散片处理记录"

VIDEO_EXTENSIONS = {
    ".mp4",
    ".mkv",
    ".avi",
    ".wmv",
    ".mov",
    ".flv",
    ".ts",
    ".m2ts",
    ".mpg",
    ".mpeg",
    ".webm",
    ".rmvb",
    ".iso",
}

SKIP_ENTRY_NAMES = {
    CLASSIFY_DIRNAME.casefold(),
    "元数据".casefold(),
    "封面".casefold(),
    "封面预览图".casefold(),
}


def _should_skip_entry(name: str) -> bool:
    text = str(name or "").strip()
    if not text or text.startswith("."):
        return True
    if text.casefold() in SKIP_ENTRY_NAMES:
        return True
    if text.startswith("#") or text.startswith("散片处理记录"):
        return True
    return False


def _scan_video_file(file_path: Path, subtitle_codes: set[str]) -> dict | None:
    code = extract_code_from_text(file_path.stem)
    if not code:
        return None

    normalized = normalize_code(code)
    has_uncensored = has_uncensored_marker_in_filename(file_path.name, normalized) or has_loose_uncensored_token(
        file_path.name
    )
    has_sub_name = has_subtitle_in_filename(file_path.name, normalized)
    has_uncensored_sub = has_cracked_subtitle_burned_in_filename(file_path.name, normalized)
    has_sub_file = normalized in subtitle_codes
    subtitle_kind = subtitle_marker_kind_in_filename(file_path.name, normalized)
    is_4k = is_4k_in_filename(file_path.name)

    has_censored_ch_file = bool(has_sub_name and not has_uncensored)
    crack_status = resolve_video_crack_status(
        has_uncensored_file=has_uncensored,
        has_uncensored_sub_in_name=has_uncensored_sub,
        has_censored_ch_file=has_censored_ch_file,
        has_subtitle_file=has_sub_file,
    )
    has_subtitle = bool(has_sub_name or has_sub_file or has_uncensored_sub)

    return {
        "code": normalized,
        "source_file": file_path.name,
        "source_path": str(file_path.resolve()),
        "filename_actress": extract_actress_from_loose_filename(file_path.name, normalized),
        "has_uncensored": has_uncensored,
        "has_subtitle_name": has_sub_name,
        "has_subtitle_file": has_sub_file,
        "has_uncensored_sub_in_name": has_uncensored_sub,
        "has_censored_ch_file": has_censored_ch_file,
        "subtitle_kind": subtitle_kind,
        "is_4k": is_4k,
        "has_subtitle": has_subtitle,
        "crack_status": crack_status,
    }


def scan_loose_video_roots(roots: list[str] | None = None) -> tuple[list[dict], list[str]]:
    if roots is None:
        roots = load_library_locations().get(LOOSE_PENDING_KEY, [])

    records: list[dict] = []
    valid_roots: list[str] = []

    for root in roots:
        root_path = Path(root)
        if not root_path.is_dir():
            continue
        valid_roots.append(str(root_path.resolve()))

        subtitle_codes = scan_folder_subtitle_codes(root_path)
        buckets: dict[str, dict] = {}

        try:
            entries = list(root_path.iterdir())
        except OSError:
            continue

        for entry in entries:
            if not entry.is_file():
                continue
            if _should_skip_entry(entry.name):
                continue
            if entry.suffix.lower() not in VIDEO_EXTENSIONS:
                continue

            item = _scan_video_file(entry, subtitle_codes)
            if not item:
                continue

            code = str(item["code"])
            existing = buckets.get(code)
            if not existing:
                buckets[code] = item
                continue

            for flag in (
                "has_uncensored",
                "has_subtitle_name",
                "has_subtitle_file",
                "has_uncensored_sub_in_name",
                "has_censored_ch_file",
                "is_4k",
                "has_subtitle",
            ):
                if item.get(flag):
                    existing[flag] = True
            if item.get("subtitle_kind") and not existing.get("subtitle_kind"):
                existing["subtitle_kind"] = item["subtitle_kind"]
            if item.get("has_uncensored"):
                existing["source_file"] = item["source_file"]
                existing["source_path"] = item["source_path"]
            existing["crack_status"] = resolve_video_crack_status(
                has_uncensored_file=bool(existing.get("has_uncensored")),
                has_uncensored_sub_in_name=bool(existing.get("has_uncensored_sub_in_name")),
                has_censored_ch_file=bool(existing.get("has_censored_ch_file")),
                has_subtitle_file=bool(existing.get("has_subtitle_file")),
            )

        items = sorted(buckets.values(), key=lambda row: code_sort_key(str(row.get("code") or "")))
        pending, skipped, has_catalog = filter_pending_codes(root_path, items)
        if not pending:
            continue

        records.append(
            {
                "root_path": str(root_path.resolve()),
                "root_name": root_path.name,
                "items": pending,
                "skipped_catalog_codes": [str(row.get("code") or "") for row in skipped],
                "catalog_skip_count": len(skipped),
                "has_catalog": has_catalog,
                "total_items_in_root": len(items),
            }
        )

    return records, valid_roots
