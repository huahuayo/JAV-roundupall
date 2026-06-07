"""Write/read 无字幕番号.txt for sync tasks and manual subtitle matching."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.parser import code_sort_key

NO_SUBTITLE_FILENAME = "无字幕番号.txt"


def codes_without_subtitle(code_results: list[dict[str, Any]]) -> list[str]:
    codes: list[str] = []
    seen: set[str] = set()
    for item in code_results or []:
        if not item.get("ok"):
            continue
        if item.get("has_subtitle"):
            continue
        code = str(item.get("code") or "").strip().upper()
        if not code or code in seen:
            continue
        seen.add(code)
        codes.append(code)
    return sorted(codes, key=code_sort_key)


def write_folder_no_subtitle_txt(folder_path: str | Path, code_results: list[dict[str, Any]]) -> str:
    root = Path(folder_path)
    if not root.is_dir():
        return ""
    codes = codes_without_subtitle(code_results)
    path = root / NO_SUBTITLE_FILENAME
    lines = codes if codes else ["# 暂无无字幕番号"]
    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(path.resolve())
    except OSError:
        return ""


def write_root_no_subtitle_txt(root_path: str | Path, folder_results: list[dict[str, Any]]) -> str:
    root = Path(root_path)
    if not root.is_dir():
        return ""
    codes: list[str] = []
    seen: set[str] = set()
    for folder in folder_results or []:
        for code in codes_without_subtitle(folder.get("code_results") or []):
            if code in seen:
                continue
            seen.add(code)
            codes.append(code)
    codes.sort(key=code_sort_key)
    path = root / NO_SUBTITLE_FILENAME
    lines = codes if codes else ["# 暂无无字幕番号"]
    try:
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return str(path.resolve())
    except OSError:
        return ""


def read_no_subtitle_codes(folder_path: str | Path) -> list[str]:
    path = Path(folder_path) / NO_SUBTITLE_FILENAME
    if not path.is_file():
        return []
    codes: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        codes.append(line.upper())
    return codes
