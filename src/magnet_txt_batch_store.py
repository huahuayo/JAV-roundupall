"""Batch magnet TXT output for marked videos on an actress profile."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.actress_folder_store import lookup_actress_folder_from_db, sanitize_actress_name
from src.library_location_settings import load_library_locations
from src.library_media_loader import _display_actress_name
from src.magnet_txt_store import sanitize_magnet_txt_filename
from src.magnet_saved_scanner import MAGNET_SAVED_KEY, parse_magnet_saved_folder_name
from src.no_subtitle_txt import NO_SUBTITLE_FILENAME, read_no_subtitle_codes
from src.pending_download_scanner import PENDING_DOWNLOAD_KEY
from src.sync_folder_rename import strip_sync_status_prefix
from src.video_cracked_scanner import VIDEO_CRACKED_KEY, parse_video_cracked_folder_name
from src.video_downloaded_scanner import VIDEO_DOWNLOADED_KEY, parse_video_downloaded_folder_name

_CODE_RE = re.compile(r"^[A-Z]{1,10}-\d{1,5}[A-Z]?$", re.IGNORECASE)
_SECTION_ALIASES = {
    "4k资源": "four_k",
    "4k": "four_k",
    "字幕资源": "subtitle",
    "高清资源": "hd",
    "无合适资源": "none",
    "无匹配资源": "none",
    "什么都没匹配到": "none",
}


def _normalize_actress_key(name: str) -> str:
    return sanitize_actress_name(name).casefold()


LIBRARY_ACTRESS_KEYS = (
    PENDING_DOWNLOAD_KEY,
    MAGNET_SAVED_KEY,
    VIDEO_DOWNLOADED_KEY,
    VIDEO_CRACKED_KEY,
)


def _actress_key_from_folder_name(folder_name: str, actress_match_name: str = "") -> str:
    if actress_match_name:
        key = _normalize_actress_key(actress_match_name)
        if key:
            return key
    display = _display_actress_name(folder_name, "")
    key = _normalize_actress_key(display)
    if key:
        return key
    return _normalize_actress_key(strip_sync_status_prefix(folder_name))


def find_actress_folder(actress_name: str, *, javdb_id: str = "") -> Path | None:
    clean = sanitize_actress_name(actress_name)
    if not clean and not javdb_id:
        return None

    db_path = lookup_actress_folder_from_db(clean, javdb_id=javdb_id)
    if db_path is not None:
        return db_path

    target = _normalize_actress_key(clean)
    if not target:
        return None

    locs = load_library_locations()
    for lib_key in LIBRARY_ACTRESS_KEYS:
        for root in locs.get(lib_key, []):
            root_path = Path(root)
            if not root_path.is_dir():
                continue
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

                actress_match = ""
                if lib_key == MAGNET_SAVED_KEY:
                    actress_match = str(parse_magnet_saved_folder_name(name).get("actress_match_name") or "")
                elif lib_key == VIDEO_DOWNLOADED_KEY:
                    actress_match = str(parse_video_downloaded_folder_name(name).get("actress_match_name") or "")
                elif lib_key == VIDEO_CRACKED_KEY:
                    actress_match = str(parse_video_cracked_folder_name(name).get("actress_match_name") or "")

                if _actress_key_from_folder_name(name, actress_match) == target:
                    return child

    return None


def resolve_actress_folder(actress_name: str, *, create: bool = False, javdb_id: str = "") -> Path:
    clean = sanitize_actress_name(actress_name)
    if not clean:
        raise ValueError("缺少女优名称")
    found = find_actress_folder(clean, javdb_id=javdb_id)
    if found is None:
        raise FileNotFoundError(
            f"未在库目录（待下载/磁链已保存/已下载/已破解）中找到女优文件夹：{clean}"
        )
    if create:
        found.mkdir(parents=True, exist_ok=True)
    return found


def write_magnet_batch_files(
    folder_path: str | Path,
    files: dict[str, str],
    *,
    merge: bool = True,
    processed_codes: list[str] | None = None,
) -> dict[str, str]:
    base = Path(folder_path)
    base.mkdir(parents=True, exist_ok=True)
    written: dict[str, str] = {}
    processed = {str(code or "").strip().upper() for code in (processed_codes or []) if str(code or "").strip()}
    for raw_name, content in (files or {}).items():
        safe_name = sanitize_magnet_txt_filename(str(raw_name or "output.txt"))
        path = base / safe_name
        text = str(content or "")
        if merge:
            if safe_name == "总结.txt":
                existing = path.read_text(encoding="utf-8") if path.is_file() else ""
                new_summary = _summary_dict_from_batch_text(text)
                text = build_merged_summary_text(existing, new_summary, processed)
            elif safe_name in ("破解.txt", "待匹配字幕.txt"):
                text = merge_magnet_link_file(path, text)
        if text and not text.endswith("\n"):
            text += "\n"
        path.write_text(text, encoding="utf-8")
        written[safe_name] = str(path.resolve())
    return written


def _read_magnet_link_lines(path: Path) -> list[str]:
    if not path.is_file():
        return []
    lines: list[str] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("magnet:?"):
            lines.append(line)
    return lines


def merge_magnet_link_file(path: Path, new_content: str) -> str:
    merged: list[str] = []
    seen: set[str] = set()
    for line in _read_magnet_link_lines(path):
        if line not in seen:
            seen.add(line)
            merged.append(line)
    for raw_line in str(new_content or "").splitlines():
        line = raw_line.strip()
        if not line.startswith("magnet:?"):
            continue
        if line in seen:
            continue
        seen.add(line)
        merged.append(line)
    return "\n".join(merged)


def _summary_dict_from_batch_text(text: str) -> dict[str, list[str]]:
    parsed = parse_magnet_summary_txt(text)
    return {
        "fourK": list(parsed.get("four_k") or []),
        "subtitle": list(parsed.get("subtitle") or []),
        "hd": list(parsed.get("hd") or []),
        "none": list(parsed.get("none") or []),
    }


def build_merged_summary_text(
    existing_text: str,
    new_summary: dict[str, list[str]],
    processed_codes: set[str],
) -> str:
    existing = parse_magnet_summary_txt(existing_text or "")
    sections: dict[str, set[str]] = {
        "four_k": {str(code).upper() for code in (existing.get("four_k") or [])},
        "subtitle": {str(code).upper() for code in (existing.get("subtitle") or [])},
        "hd": {str(code).upper() for code in (existing.get("hd") or [])},
        "none": {str(code).upper() for code in (existing.get("none") or [])},
    }
    new_map = {
        "four_k": {str(code).upper() for code in (new_summary.get("fourK") or [])},
        "subtitle": {str(code).upper() for code in (new_summary.get("subtitle") or [])},
        "hd": {str(code).upper() for code in (new_summary.get("hd") or [])},
        "none": {str(code).upper() for code in (new_summary.get("none") or [])},
    }

    for code in processed_codes:
        if not code:
            continue
        for bucket in sections.values():
            bucket.discard(code)
        placed = False
        for key in ("four_k", "subtitle", "hd", "none"):
            if code in new_map[key]:
                sections[key].add(code)
                placed = True
                break
        if not placed:
            sections["none"].add(code)

    lines: list[str] = []
    lines.append("4K资源：")
    lines.extend(sorted(sections["four_k"]))
    lines.append("")
    lines.append("字幕资源：")
    lines.extend(sorted(sections["subtitle"]))
    lines.append("")
    lines.append("高清资源：")
    lines.extend(sorted(sections["hd"]))
    lines.append("")
    lines.append("无合适资源：")
    lines.extend(sorted(sections["none"]))
    return "\n".join(lines).strip() + "\n"


def _looks_like_code(text: str) -> bool:
    token = str(text or "").strip().upper()
    if not token:
        return False
    if _CODE_RE.match(token):
        return True
    return bool(re.match(r"^[A-Z]{2,10}\d{2,5}[A-Z]?$", token))


def parse_magnet_summary_txt(text: str) -> dict[str, Any]:
    sections: dict[str, list[str]] = {
        "four_k": [],
        "subtitle": [],
        "hd": [],
        "none": [],
    }
    current: str | None = None
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.endswith("：") or line.endswith(":"):
            header = line.rstrip("：:").strip().casefold().replace(" ", "")
            current = _SECTION_ALIASES.get(header)
            continue
        if current and _looks_like_code(line):
            code = line.upper()
            if code not in sections[current]:
                sections[current].append(code)

    manual_rows: list[dict[str, str]] = []
    for code in sections["four_k"]:
        manual_rows.append({"code": code, "category": "4K"})
    for code in sections["hd"]:
        manual_rows.append({"code": code, "category": "高清无字幕"})
    for code in sections["none"]:
        manual_rows.append({"code": code, "category": "无合适资源"})

    return {
        **sections,
        "manual_match": manual_rows,
    }


def read_magnet_summary_file(folder_path: str | Path) -> dict[str, Any]:
    base = Path(folder_path)
    summary_path = base / "总结.txt"
    if not summary_path.is_file():
        raise FileNotFoundError("未找到总结.txt")
    parsed = parse_magnet_summary_txt(summary_path.read_text(encoding="utf-8"))
    parsed["path"] = str(summary_path.resolve())
    return parsed


def read_manual_subtitle_file(actress_name: str, *, pending_download: bool = False) -> dict[str, Any]:
    folder = find_actress_folder(actress_name)
    if folder is None or not folder.is_dir():
        raise FileNotFoundError(f"未找到女优文件夹：{actress_name}")
    if pending_download:
        parsed = read_magnet_summary_file(folder)
        parsed["folder_path"] = str(folder.resolve())
        parsed["source"] = "总结.txt"
        return parsed
    codes = read_no_subtitle_codes(folder)
    subtitle_path = folder / NO_SUBTITLE_FILENAME
    return {
        "four_k": [],
        "subtitle": [],
        "hd": [],
        "none": codes,
        "manual_match": [{"code": code, "category": "无字幕"} for code in codes],
        "path": str(subtitle_path.resolve()) if subtitle_path.is_file() else "",
        "folder_path": str(folder.resolve()),
        "source": NO_SUBTITLE_FILENAME,
    }
