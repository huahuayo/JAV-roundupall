"""Scan video-cracked library folders for actress directories and video files."""

from __future__ import annotations

import re
from pathlib import Path

from src.library_location_settings import load_library_locations
from src.magnet_saved_scanner import scan_folder_subtitle_codes
from src.sync_folder_rename import strip_sync_status_prefix
from src.parser import (
    build_video_cracked_code_info,
    code_sort_key,
    extract_code_from_text,
    has_cracked_subtitle_burned_in_filename,
    has_subtitle_in_filename,
    has_uncensored_marker_in_filename,
    is_4k_in_filename,
    normalize_code,
    resolve_video_crack_status,
)

VIDEO_CRACKED_KEY = "video_cracked"
TRAILING_COUNT_SUFFIX = re.compile(r"\s+\d+$")
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
SYNC_LOG_PREFIX = "影片已破解同步"


def parse_video_cracked_folder_name(raw_name: str) -> dict[str, str]:
    raw = str(raw_name or "").strip()
    base = strip_sync_status_prefix(raw)
    actress_match_name = TRAILING_COUNT_SUFFIX.sub("", base).strip() or base
    return {
        "folder_name": raw,
        "actress_match_name": actress_match_name,
    }


def scan_video_cracked_folders(roots: list[str] | None = None) -> tuple[list[dict], list[str]]:
    """Return folder records with extracted video codes and cracked-state flags."""
    if roots is None:
        roots = load_library_locations().get(VIDEO_CRACKED_KEY, [])

    folders: list[dict] = []
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
            if not name or name.startswith("."):
                continue

            parsed = parse_video_cracked_folder_name(name)
            subtitle_codes = scan_folder_subtitle_codes(child)
            buckets: dict[str, dict] = {}

            for file_path in child.iterdir():
                if not file_path.is_file():
                    continue
                if file_path.name.startswith(SYNC_LOG_PREFIX):
                    continue
                suffix = file_path.suffix.lower()
                if suffix not in VIDEO_EXTENSIONS:
                    continue

                code = extract_code_from_text(file_path.stem)
                if not code:
                    continue

                normalized = normalize_code(code)
                is_uncensored = has_uncensored_marker_in_filename(file_path.name, normalized)
                is_4k = is_4k_in_filename(file_path.name)
                has_sub_name = has_subtitle_in_filename(file_path.name, normalized)
                has_uncensored_sub = has_cracked_subtitle_burned_in_filename(file_path.name, normalized)
                has_sub_file = normalized in subtitle_codes

                bucket = buckets.setdefault(
                    normalized,
                    {
                        "has_uncensored_file": False,
                        "has_uncensored_sub_in_name": False,
                        "has_censored_ch_file": False,
                        "has_subtitle_file": False,
                        "has_subtitle_name": False,
                        "is_4k": False,
                        "source_file": file_path.name,
                        "source_path": str(file_path.resolve()),
                        "uncensored_source_file": "",
                        "censored_ch_source_file": "",
                    },
                )

                if is_4k:
                    bucket["is_4k"] = True
                if has_sub_name:
                    bucket["has_subtitle_name"] = True
                if has_sub_file:
                    bucket["has_subtitle_file"] = True

                if is_uncensored:
                    bucket["has_uncensored_file"] = True
                    bucket["uncensored_source_file"] = file_path.name
                    bucket["source_file"] = file_path.name
                    bucket["source_path"] = str(file_path.resolve())
                    if has_uncensored_sub:
                        bucket["has_uncensored_sub_in_name"] = True
                elif has_sub_name:
                    bucket["has_censored_ch_file"] = True
                    if not bucket["censored_ch_source_file"]:
                        bucket["censored_ch_source_file"] = file_path.name
                    if not bucket["has_uncensored_file"]:
                        bucket["source_file"] = file_path.name
                        bucket["source_path"] = str(file_path.resolve())

            codes: list[dict] = []
            for normalized, bucket in buckets.items():
                crack_status = resolve_video_crack_status(
                    has_uncensored_file=bool(bucket["has_uncensored_file"]),
                    has_uncensored_sub_in_name=bool(bucket["has_uncensored_sub_in_name"]),
                    has_censored_ch_file=bool(bucket["has_censored_ch_file"]),
                    has_subtitle_file=bool(bucket["has_subtitle_file"]),
                )
                codes.append(
                    build_video_cracked_code_info(
                        code=normalized,
                        has_uncensored_file=bool(bucket["has_uncensored_file"]),
                        has_uncensored_sub_in_name=bool(bucket["has_uncensored_sub_in_name"]),
                        has_censored_ch_file=bool(bucket["has_censored_ch_file"]),
                        has_subtitle_file=bool(bucket["has_subtitle_file"]),
                        has_subtitle_name=bool(bucket["has_subtitle_name"]),
                        is_4k=bool(bucket["is_4k"]),
                        crack_status=crack_status,
                        source_file=str(bucket["source_file"]),
                        source_path=str(bucket.get("source_path") or ""),
                        uncensored_source_file=str(bucket["uncensored_source_file"]),
                        censored_ch_source_file=str(bucket["censored_ch_source_file"]),
                    )
                )

            if not codes:
                continue

            codes.sort(key=lambda item: code_sort_key(str(item.get("code") or "")))

            key = name.casefold()
            if key in seen_names:
                continue
            seen_names.add(key)

            folders.append(
                {
                    "folder_name": name,
                    "folder_path": str(child.resolve()),
                    "root": str(root_path.resolve()),
                    "codes": codes,
                    "actress_match_name": parsed["actress_match_name"],
                }
            )

    return folders, valid_roots
