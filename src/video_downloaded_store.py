"""Write video-downloaded sync summary logs."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.parser import code_sort_key

logger = logging.getLogger(__name__)

FOLDER_LOG_PREFIX = "影片已下载同步"
ROOT_LOG_PREFIX = "影片已下载同步总览"


def _sort_code_results(code_results: list[dict]) -> list[dict]:
    return sorted(code_results, key=lambda item: code_sort_key(str(item.get("code") or "")))


def _code_list(items: list[dict], predicate) -> list[str]:
    return [str(item.get("code") or "-") for item in items if predicate(item)]


def _join_codes(codes: list[str]) -> str:
    return ", ".join(codes) if codes else "-"


def _subtitle_label(item: dict) -> str:
    return "有字幕" if item.get("has_subtitle") else "无字幕"


def _four_k_label(item: dict) -> str:
    return "4K" if item.get("is_4k") else "-"


def _build_media_summary(sorted_results: list[dict]) -> list[str]:
    with_sub = _code_list(sorted_results, lambda item: item.get("has_subtitle"))
    without_sub = _code_list(sorted_results, lambda item: not item.get("has_subtitle"))
    four_k = _code_list(sorted_results, lambda item: item.get("is_4k"))
    sub_file = _code_list(sorted_results, lambda item: item.get("has_subtitle_file"))
    sub_name = _code_list(sorted_results, lambda item: item.get("has_subtitle_name"))

    return [
        "",
        "# 字幕汇总",
        f"# 有字幕 ({len(with_sub)}): {_join_codes(with_sub)}",
        f"# 无字幕 ({len(without_sub)}): {_join_codes(without_sub)}",
        f"# 字幕文件 srt/ass ({len(sub_file)}): {_join_codes(sub_file)}",
        f"# 文件名含 ch/c ({len(sub_name)}): {_join_codes(sub_name)}",
        "",
        "# 4K 汇总",
        f"# 4K 影片 ({len(four_k)}): {_join_codes(four_k)}",
        "",
    ]


def write_video_downloaded_folder_log(
    folder_path: str,
    *,
    session_id: str,
    actress_name: str,
    code_results: list[dict],
) -> str:
    path = Path(folder_path)
    if not path.is_dir():
        return ""

    stamp = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = path / f"{FOLDER_LOG_PREFIX}_{stamp}.txt"
    sorted_results = _sort_code_results(code_results)
    success = sum(1 for item in sorted_results if item.get("ok"))
    fail = len(sorted_results) - success

    lines = [
        f"# JAV Manager — {FOLDER_LOG_PREFIX}",
        f"# 女优文件夹: {path.name}",
        f"# 会话: {stamp}",
        f"# 女优: {actress_name}",
        f"# 番号总数: {len(sorted_results)}  ·  成功: {success}  ·  失败: {fail}",
        "# 格式: 番号 | 状态 | 字幕 | 4K | 说明",
        "",
    ]
    for item in sorted_results:
        code = str(item.get("code") or "-")
        if item.get("ok"):
            status = "成功"
            detail = "女优页与详情页已标记「已下载」，贴纸已隐藏，并写入桌面数据库"
        else:
            status = "失败"
            detail = str(item.get("error") or "未知错误")
        lines.append(
            f"{code} | {status} | {_subtitle_label(item)} | {_four_k_label(item)} | {detail}"
        )

    lines.extend(_build_media_summary(sorted_results))

    try:
        log_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Wrote video downloaded folder log: %s", log_path)
        return str(log_path)
    except OSError as exc:
        logger.warning("Failed to write folder log %s: %s", log_path, exc)
        return ""


def write_video_downloaded_root_logs(
    log_roots: list[str],
    *,
    session_id: str,
    started_at: str,
    finished_at: str,
    folder_results: list[dict[str, Any]],
    error: str = "",
) -> list[str]:
    written: list[str] = []
    stamp = session_id or datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ROOT_LOG_PREFIX}_{stamp}.txt"

    for root in log_roots:
        root_path = Path(root)
        if not root_path.is_dir():
            continue
        log_path = root_path / filename
        total_codes = sum(int(item.get("total_codes") or 0) for item in folder_results)
        total_success = sum(int(item.get("success_codes") or 0) for item in folder_results)
        total_fail = sum(int(item.get("fail_codes") or 0) for item in folder_results)

        lines = [
            f"# JAV Manager — {ROOT_LOG_PREFIX}",
            f"# 根目录: {root_path}",
            f"# 会话: {stamp}",
            f"# 开始: {started_at}",
            f"# 结束: {finished_at}",
            f"# 女优文件夹: {len(folder_results)}  ·  番号合计: {total_codes}  ·  成功: {total_success}  ·  失败: {total_fail}",
            "# 格式: 女优文件夹 | 番号总数 | 成功 | 失败 | 说明",
            "",
        ]
        if error:
            lines.extend([f"# 整体错误: {error}", ""])

        for item in folder_results:
            folder_name = str(item.get("folder_name") or "-")
            total = int(item.get("total_codes") or 0)
            success = int(item.get("success_codes") or 0)
            fail = int(item.get("fail_codes") or 0)
            if item.get("ok") or success > 0:
                detail = "同步完成" if fail == 0 else f"部分完成（{fail} 个未同步）"
                detail += "；女优页标记「已下载」"
                rename_msg = str(item.get("rename_message") or "")
                if rename_msg:
                    detail += f"；{rename_msg}"
                elif item.get("renamed") is False:
                    detail += "；重命名失败"
                if item.get("folder_log_path"):
                    detail += f"；详情见 {Path(str(item.get('folder_log_path'))).name}"
            else:
                detail = str(item.get("error") or "同步失败")
            lines.append(f"{folder_name} | {total} | {success} | {fail} | {detail}")

        lines.append("")
        try:
            log_path.write_text("\n".join(lines), encoding="utf-8")
            written.append(str(log_path))
            logger.info("Wrote video downloaded root log: %s", log_path)
        except OSError as exc:
            logger.warning("Failed to write root log %s: %s", log_path, exc)

    return written
