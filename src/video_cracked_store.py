"""Write video-cracked sync summary logs."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from src.parser import (
    CRACK_STATUS_CRACKED,
    CRACK_STATUS_CRACKED_SUB_PENDING_BURN,
    CRACK_STATUS_LABELS,
    CRACK_STATUS_PENDING_CRACK,
    CRACK_STATUS_PENDING_EXTRACT_SUB,
    code_sort_key,
)

logger = logging.getLogger(__name__)

FOLDER_LOG_PREFIX = "影片已破解同步"
ROOT_LOG_PREFIX = "影片已破解同步总览"


def _sort_code_results(code_results: list[dict]) -> list[dict]:
    return sorted(code_results, key=lambda item: code_sort_key(str(item.get("code") or "")))


def _code_list(items: list[dict], predicate) -> list[str]:
    return [str(item.get("code") or "-") for item in items if predicate(item)]


def _join_codes(codes: list[str]) -> str:
    return ", ".join(codes) if codes else "-"


def _subtitle_label(item: dict) -> str:
    status = str(item.get("crack_status") or "")
    if status == CRACK_STATUS_CRACKED_SUB_PENDING_BURN:
        return "外挂字幕待烧录"
    if status == CRACK_STATUS_PENDING_EXTRACT_SUB:
        return "待提取字幕"
    return "有字幕" if item.get("has_subtitle") else "无字幕"


def _four_k_label(item: dict) -> str:
    return "4K" if item.get("is_4k") else "-"


def _crack_status_label(item: dict) -> str:
    return str(
        item.get("crack_status_label")
        or CRACK_STATUS_LABELS.get(str(item.get("crack_status") or ""), "-")
    )


def _detail_note(item: dict) -> str:
    if not item.get("ok"):
        return str(item.get("error") or "未知错误")

    status = str(item.get("crack_status") or "")
    parts = ["女优页与详情页已标记，并写入桌面数据库"]
    source = str(item.get("source_file") or "").strip()
    uncensored = str(item.get("uncensored_source_file") or "").strip()
    censored_ch = str(item.get("censored_ch_source_file") or "").strip()

    if status == CRACK_STATUS_CRACKED:
        parts.append("文件名含 -U/-UC/restored，马赛克已去除")
        if item.get("has_uncensored_sub_in_name"):
            parts.append("字幕已烧录（-UC）")
        elif item.get("has_subtitle"):
            parts.append("字幕已就绪")
    elif status == CRACK_STATUS_CRACKED_SUB_PENDING_BURN:
        parts.append(f"破解文件 {uncensored or source} 含 -U，但存在外挂 srt/ass，字幕尚未烧录")
    elif status == CRACK_STATUS_PENDING_EXTRACT_SUB:
        parts.append(f"待从 {censored_ch or source} 提取字幕（文件名含 -C/-CH，尚无 -U 破解版）")
    elif status == CRACK_STATUS_PENDING_CRACK:
        parts.append(f"文件 {source or '-'} 尚无 -U/-UC 标记，待破解")

    if item.get("is_4k"):
        parts.append("4K")
    return "；".join(parts)


def _build_media_summary(sorted_results: list[dict]) -> list[str]:
    cracked = _code_list(sorted_results, lambda item: item.get("crack_status") == CRACK_STATUS_CRACKED)
    pending_burn = _code_list(
        sorted_results,
        lambda item: item.get("crack_status") == CRACK_STATUS_CRACKED_SUB_PENDING_BURN,
    )
    pending_extract = _code_list(
        sorted_results,
        lambda item: item.get("crack_status") == CRACK_STATUS_PENDING_EXTRACT_SUB,
    )
    pending_crack = _code_list(
        sorted_results,
        lambda item: item.get("crack_status") == CRACK_STATUS_PENDING_CRACK,
    )
    with_sub = _code_list(sorted_results, lambda item: item.get("has_subtitle"))
    without_sub = _code_list(sorted_results, lambda item: not item.get("has_subtitle"))
    four_k = _code_list(sorted_results, lambda item: item.get("is_4k"))
    sub_file = _code_list(sorted_results, lambda item: item.get("has_subtitle_file"))
    uncensored = _code_list(sorted_results, lambda item: item.get("has_uncensored_file"))

    return [
        "",
        "# 破解状态汇总",
        f"# 已破解 ({len(cracked)}): {_join_codes(cracked)}",
        f"# 已破解·字幕待烧录 ({len(pending_burn)}): {_join_codes(pending_burn)}",
        f"# 待提取字幕 ({len(pending_extract)}): {_join_codes(pending_extract)}",
        f"# 待破解 ({len(pending_crack)}): {_join_codes(pending_crack)}",
        f"# 文件名含 -U/-UC ({len(uncensored)}): {_join_codes(uncensored)}",
        "",
        "# 字幕汇总",
        f"# 有字幕/可烧录 ({len(with_sub)}): {_join_codes(with_sub)}",
        f"# 无字幕 ({len(without_sub)}): {_join_codes(without_sub)}",
        f"# 外挂字幕文件 srt/ass ({len(sub_file)}): {_join_codes(sub_file)}",
        "",
        "# 4K 汇总",
        f"# 4K 影片 ({len(four_k)}): {_join_codes(four_k)}",
        "",
        "# 说明",
        "# -U / -UC：文件名中番号后的标记，表示马赛克已破解；-UC 表示字幕已烧录",
        "# 已破解·字幕待烧录：已有 -U 文件且文件夹内有同名 srt/ass，但文件名尚无 -UC",
        "# 待提取字幕：存在带 -C/-CH 的有码文件，尚无 -U 破解版",
        "# 待破解：未发现 -U/-UC 标记",
        "",
    ]


def write_video_cracked_folder_log(
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
        "# 格式: 番号 | 状态 | 破解状态 | 字幕 | 4K | 说明",
        "",
    ]
    for item in sorted_results:
        code = str(item.get("code") or "-")
        status = "成功" if item.get("ok") else "失败"
        lines.append(
            f"{code} | {status} | {_crack_status_label(item)} | {_subtitle_label(item)} | "
            f"{_four_k_label(item)} | {_detail_note(item)}"
        )

    lines.extend(_build_media_summary(sorted_results))

    try:
        log_path.write_text("\n".join(lines), encoding="utf-8")
        logger.info("Wrote video cracked folder log: %s", log_path)
        return str(log_path)
    except OSError as exc:
        logger.warning("Failed to write folder log %s: %s", log_path, exc)
        return ""


def write_video_cracked_root_logs(
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
                detail += "；女优页标记「已破解」"
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
            logger.info("Wrote video cracked root log: %s", log_path)
        except OSError as exc:
            logger.warning("Failed to write root log %s: %s", log_path, exc)

    return written
