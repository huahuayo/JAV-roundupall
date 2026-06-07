"""Rename, classify, and log loose video files after JavDB marking."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from src.catalog_reader import append_catalog_entries
from src.loose_video_scanner import CLASSIFY_DIRNAME, LOG_PREFIX
from src.parser import extract_code_from_text, normalize_code, refresh_loose_media_flags, resolve_loose_actress_name

logger = logging.getLogger(__name__)

SUBTITLE_EXTENSIONS = (".srt", ".ass", ".ssa", ".sub")

INVALID_STEM_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _sanitize_stem(text: str) -> str:
    value = INVALID_STEM_CHARS.sub("_", str(text or "").strip())
    value = re.sub(r"\s+", " ", value).strip(" .")
    return value or "_"


def _rename_suffix_parts(item: dict[str, Any]) -> list[str]:
    parts: list[str] = []
    if item.get("has_uncensored"):
        parts.append("u")
    subtitle_kind = str(item.get("subtitle_kind") or "").lower()
    if subtitle_kind == "ch":
        parts.append("ch")
    elif subtitle_kind == "c":
        parts.append("c")
    elif item.get("has_subtitle_file") and not item.get("has_subtitle_name"):
        parts.append("c")
    if item.get("is_4k"):
        parts.append("4k")
    return parts


def build_loose_target_stem(code: str, actress_name: str, item: dict[str, Any]) -> str:
    actress = _sanitize_stem(actress_name or "未知")
    suffix = _rename_suffix_parts(item)
    parts = [_sanitize_stem(code), actress, *suffix]
    return " ".join(part for part in parts if part)


def should_move_to_classify_folder(item: dict[str, Any]) -> bool:
    if not item.get("has_uncensored"):
        return False
    if item.get("has_subtitle_file") or item.get("has_subtitle_name"):
        return True
    return bool(str(item.get("subtitle_kind") or "").strip())


def _subtitle_siblings(video_path: Path) -> list[Path]:
    if not video_path.is_file():
        return []
    stem = video_path.stem
    parent = video_path.parent
    siblings: list[Path] = []
    for path in parent.iterdir():
        if not path.is_file() or path == video_path:
            continue
        if path.suffix.lower() not in SUBTITLE_EXTENSIONS:
            continue
        if path.stem == stem or path.stem.startswith(f"{stem}."):
            siblings.append(path)
    return siblings


def _move_related_subtitles(src_video: Path, dest_video: Path) -> None:
    if src_video.resolve() == dest_video.resolve():
        return
    old_stem = src_video.stem
    new_stem = dest_video.stem
    for subtitle in _subtitle_siblings(src_video):
        target = dest_video.with_name(subtitle.name.replace(old_stem, new_stem, 1))
        counter = 1
        while target.exists() and target.resolve() != subtitle.resolve():
            target = dest_video.with_name(f"{target.stem}_{counter}{target.suffix}")
            counter += 1
        if target.resolve() != subtitle.resolve():
            subtitle.rename(target)


def _rename_item_files(root: Path, item: dict[str, Any], actress_name: str) -> dict[str, Any]:
    item = refresh_loose_media_flags(item)
    source_file = str(item.get("source_file") or "")
    code = normalize_code(str(item.get("code") or ""))
    if not source_file or not code:
        return {"ok": False, "error": "缺少源文件或番号", **item}

    src_path = root / source_file
    if not src_path.is_file():
        return {"ok": False, "error": "源文件不存在", **item}

    target_stem = build_loose_target_stem(code, actress_name, item)
    target_path = root / f"{target_stem}{src_path.suffix}"
    if target_path.resolve() != src_path.resolve():
        counter = 1
        while target_path.exists() and target_path.resolve() != src_path.resolve():
            target_path = root / f"{target_stem}_{counter}{src_path.suffix}"
            counter += 1
        if target_path.resolve() != src_path.resolve():
            _move_related_subtitles(src_path, target_path)
            src_path.rename(target_path)

    updated = dict(item)
    updated["source_file"] = target_path.name
    updated["source_path"] = str(target_path.resolve())
    updated["renamed_to"] = target_path.name
    updated["ok"] = True
    return updated


def _move_to_classify(root: Path, item: dict[str, Any]) -> dict[str, Any]:
    if not should_move_to_classify_folder(item):
        return item

    classify_dir = root / CLASSIFY_DIRNAME
    classify_dir.mkdir(parents=True, exist_ok=True)
    source_file = str(item.get("source_file") or "")
    src_path = root / source_file
    if not src_path.is_file():
        return item

    dest_path = classify_dir / src_path.name
    counter = 1
    while dest_path.exists():
        dest_path = classify_dir / f"{src_path.stem}_{counter}{src_path.suffix}"
        counter += 1
    _move_related_subtitles(src_path, dest_path)
    src_path.rename(dest_path)

    updated = dict(item)
    updated["source_file"] = dest_path.name
    updated["source_path"] = str(dest_path.resolve())
    updated["classified_to"] = str(dest_path.relative_to(root))
    return updated


def write_loose_root_log(root_path: str, *, session_id: str, item_results: list[dict[str, Any]]) -> str:
    root = Path(root_path)
    if not root.is_dir():
        return ""

    stamp = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = root / f"{LOG_PREFIX}_{stamp}.txt"
    success = sum(1 for item in item_results if item.get("ok"))
    fail = len(item_results) - success

    lines = [
        f"# JAV Manager — {LOG_PREFIX}",
        f"# 目录: {root}",
        f"# 会话: {stamp}",
        f"# 番号总数: {len(item_results)}  ·  成功: {success}  ·  失败: {fail}",
        "# 格式: 番号 | 状态 | 字幕 | 破解 | 4K | 新文件名 | 说明",
        "",
    ]
    for item in item_results:
        code = str(item.get("code") or "-")
        if item.get("ok"):
            status = "成功"
            detail = "已标记并处理文件"
            if item.get("classified_to"):
                detail += f"；已移入 {item['classified_to']}"
        else:
            status = "失败"
            detail = str(item.get("error") or "未知错误")
        sub = "有字幕" if item.get("has_subtitle") else "无字幕"
        crack = "已破解" if item.get("has_uncensored") else "-"
        four_k = "4K" if item.get("is_4k") else "-"
        renamed = str(item.get("renamed_to") or item.get("source_file") or "-")
        lines.append(f"{code} | {status} | {sub} | {crack} | {four_k} | {renamed} | {detail}")

    try:
        log_path.write_text("\n".join(lines), encoding="utf-8")
        return str(log_path)
    except OSError as exc:
        logger.warning("Failed to write loose log %s: %s", log_path, exc)
        return ""


def finalize_loose_root(root_result: dict[str, Any], *, session_id: str) -> dict[str, Any]:
    item = dict(root_result or {})
    root_path = str(item.get("root_path") or "")
    root = Path(root_path)
    if not root.is_dir():
        item["ok"] = False
        item["error"] = "目录不存在"
        return item

    item_results = item.get("item_results") or []
    if not isinstance(item_results, list):
        item_results = []

    processed: list[dict[str, Any]] = []
    for row in item_results:
        current = dict(row)
        if not current.get("ok"):
            processed.append(current)
            continue

        current = refresh_loose_media_flags(current)
        actress_name = resolve_loose_actress_name(
            filename_actress=str(current.get("filename_actress") or ""),
            javdb_actress=str(current.get("actress") or current.get("actresses") or ""),
        )

        try:
            renamed = _rename_item_files(root, current, actress_name)
            if renamed.get("ok"):
                renamed = _move_to_classify(root, renamed)
            processed.append(renamed)
        except OSError as exc:
            processed.append({**current, "ok": False, "error": str(exc)})

    success_items = [row for row in processed if row.get("ok")]
    append_catalog_entries(
        root_path,
        actress_name="散片",
        rows=success_items,
    )

    log_path = write_loose_root_log(root_path, session_id=session_id, item_results=processed)
    if log_path:
        item["folder_log_path"] = log_path

    item["item_results"] = processed
    item["success_items"] = len(success_items)
    item["fail_items"] = len(processed) - len(success_items)
    item["ok"] = len(success_items) > 0
    item["error"] = "" if item["ok"] else "全部散片处理失败"
    return item
