"""Settings tab layout: sync tasks (left) + extension/browser (right)."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

import customtkinter as ctk

from src.library_location_settings import load_library_locations
from src.loose_video_scanner import LOOSE_PENDING_KEY
from src.magnet_saved_scanner import MAGNET_SAVED_KEY
from src.magnet_txt_settings import get_magnet_txt_output_dir
from src.state_db import get_state_db_path
from src.pending_download_scanner import PENDING_DOWNLOAD_KEY
from src.video_cracked_scanner import VIDEO_CRACKED_KEY
from src.video_downloaded_scanner import VIDEO_DOWNLOADED_KEY
from src.ui.theme import (
    ACCENT_SOFT,
    BORDER,
    SURFACE_ALT,
    TEXT,
    TEXT_MUTED,
    accent_button,
    body_font,
    card_frame,
    ghost_button,
    section_font,
    style_progress,
    title_font,
)

if TYPE_CHECKING:
    from src.app import JavManagerApp

SETTINGS_SYNC_KEYS: tuple[tuple[str, str], ...] = (
    (PENDING_DOWNLOAD_KEY, "待下载"),
    (MAGNET_SAVED_KEY, "磁链已保存"),
    (VIDEO_DOWNLOADED_KEY, "已下载"),
    (VIDEO_CRACKED_KEY, "已破解"),
    (LOOSE_PENDING_KEY, "散片"),
)

TASK_HINTS: dict[str, str] = {
    PENDING_DOWNLOAD_KEY: "子文件夹为女优名。优先对照收藏女优；未找到时在 JavDB 搜索女优名后标记，成功后重命名为「1 原名」。",
    MAGNET_SAVED_KEY: "子文件夹为女优名，内含磁链 TXT。女优主页无番号时按番号搜索 JavDB 后标记；完成后重命名为 完成 … 或 !N …。",
    VIDEO_DOWNLOADED_KEY: "子文件夹为女优名。读取 目录.txt 仅处理 JavDB同步=否；女优主页无番号时按番号搜索后标记。",
    VIDEO_CRACKED_KEY: "识别 -U/-UC/restored 破解标记。目录.txt 分任务列；女优主页无番号时按番号搜索 JavDB 后标记/抓元数据。",
    LOOSE_PENDING_KEY: "目录下直接放散片。按番号搜索 JavDB 后标记、重命名并分类 U+字幕 影片。",
}


def build_settings_panel(app: JavManagerApp, parent: ctk.CTkFrame) -> None:
    parent.grid_columnconfigure(0, weight=3)
    parent.grid_columnconfigure(1, weight=2)
    parent.grid_rowconfigure(0, weight=1)

    left = ctk.CTkScrollableFrame(
        parent,
        label_text="同步任务与库路径",
        fg_color=SURFACE_ALT,
        label_fg_color=ACCENT_SOFT,
        label_text_color=TEXT,
    )
    left.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=0)

    path_tools = ctk.CTkFrame(left, fg_color="transparent")
    path_tools.pack(fill="x", padx=4, pady=(0, 8))
    ctk.CTkLabel(
        path_tools,
        text="库路径保存在本机配置中，不会打进发布包。",
        text_color=TEXT_MUTED,
        font=body_font(11),
        anchor="w",
    ).pack(side="left", fill="x", expand=True)
    ghost_button(path_tools, text="清空路径设置", width=96, height=26, command=app._reset_path_settings).pack(
        side="right"
    )

    locations = load_library_locations()
    for key, label in SETTINGS_SYNC_KEYS:
        _build_task_block(app, left, key, label, locations)

    txt_left = ctk.CTkFrame(left, fg_color="transparent")
    txt_left.pack(fill="x", padx=4, pady=(4, 4))
    txt_left.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(txt_left, text="生成 TXT 目录", width=88, anchor="w").grid(row=0, column=0, sticky="w")
    if not hasattr(app, "magnet_txt_dir_var"):
        app.magnet_txt_dir_var = tk.StringVar(value=str(get_magnet_txt_output_dir()))
    ctk.CTkEntry(txt_left, textvariable=app.magnet_txt_dir_var).grid(row=0, column=1, sticky="ew", padx=(0, 6))
    ctk.CTkButton(txt_left, text="浏览", width=56, command=app._browse_magnet_txt_dir).grid(row=0, column=2, padx=(0, 4))
    ctk.CTkButton(txt_left, text="保存", width=48, command=app._save_magnet_txt_dir).grid(row=0, column=3)

    save_row = ctk.CTkFrame(left, fg_color="transparent")
    save_row.pack(fill="x", padx=4, pady=(8, 4))
    accent_button(save_row, text="保存全部库地址", width=130, command=app._save_library_locations).pack(
        side="right"
    )

    right = card_frame(parent)
    right.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=0)
    right.grid_columnconfigure(0, weight=1)
    right.grid_rowconfigure(2, weight=1)
    _build_browser_panel(app, right)


def _build_task_block(
    app: JavManagerApp,
    parent: ctk.CTkScrollableFrame,
    key: str,
    label: str,
    locations: dict,
) -> None:
    block = card_frame(parent, fg_color=SURFACE_ALT)
    block.pack(fill="x", padx=4, pady=(0, 10))

    header = ctk.CTkFrame(block, fg_color="transparent")
    header.pack(fill="x", padx=8, pady=(8, 4))
    ctk.CTkLabel(header, text=label, font=ctk.CTkFont(size=13, weight="bold")).pack(side="left")
    ctk.CTkButton(
        header, text="+ 添加目录", width=80, height=26, command=lambda k=key: app._add_library_path_row(k, "")
    ).pack(side="right", padx=(4, 0))

    if key == PENDING_DOWNLOAD_KEY:
        app._pending_download_start_btn = accent_button(
            header, text="开始任务", width=76, height=26, command=app._start_pending_download_task
        )
        app._pending_download_start_btn.pack(side="right", padx=(4, 0))
    elif key == MAGNET_SAVED_KEY:
        app._magnet_saved_start_btn = accent_button(
            header, text="开始同步", width=76, height=26, command=app._start_magnet_saved_task
        )
        app._magnet_saved_start_btn.pack(side="right", padx=(4, 0))
    elif key == VIDEO_DOWNLOADED_KEY:
        app._video_downloaded_start_btn = accent_button(
            header, text="开始同步", width=76, height=26, command=app._start_video_downloaded_task
        )
        app._video_downloaded_start_btn.pack(side="right", padx=(4, 0))
    elif key == VIDEO_CRACKED_KEY:
        app._video_cracked_start_btn = accent_button(
            header, text="开始同步", width=76, height=26, command=app._start_video_cracked_task
        )
        app._video_cracked_start_btn.pack(side="right", padx=(4, 0))
        app._video_cracked_metadata_btn = ghost_button(
            header, text="同步元数据", width=76, height=26, command=app._start_video_cracked_metadata_task
        )
        app._video_cracked_metadata_btn.pack(side="right", padx=(4, 0))
    elif key == LOOSE_PENDING_KEY:
        app._loose_video_start_btn = accent_button(
            header, text="开始处理", width=76, height=26, command=app._start_loose_video_task
        )
        app._loose_video_start_btn.pack(side="right", padx=(4, 0))

    hint = TASK_HINTS.get(key, "")
    if hint:
        ctk.CTkLabel(
            block,
            text=hint,
            anchor="w",
            justify="left",
            wraplength=520,
            text_color=("gray40", "gray60"),
            font=ctk.CTkFont(size=11),
        ).pack(fill="x", padx=10, pady=(0, 4))

    paths_container = ctk.CTkFrame(block, fg_color="transparent")
    paths_container.pack(fill="x", padx=8, pady=(0, 4))
    app._library_path_containers[key] = paths_container
    for path in locations.get(key, []):
        app._add_library_path_row(key, path)

    sync_row = ctk.CTkFrame(block, fg_color="transparent")
    sync_row.pack(fill="x", padx=10, pady=(0, 8))
    progress = ctk.CTkProgressBar(sync_row)
    style_progress(progress)
    progress.pack(fill="x", pady=(0, 4))
    progress.set(0)
    status = ctk.CTkLabel(
        sync_row,
        text="任务进度将在此显示",
        anchor="w",
        text_color=("gray40", "gray60"),
        font=ctk.CTkFont(size=11),
    )
    status.pack(fill="x")

    if key == PENDING_DOWNLOAD_KEY:
        app._pending_download_progress = progress
        app._pending_download_sync_label = status
    elif key == MAGNET_SAVED_KEY:
        app._magnet_saved_progress = progress
        app._magnet_saved_sync_label = status
    elif key == VIDEO_DOWNLOADED_KEY:
        app._video_downloaded_progress = progress
        app._video_downloaded_sync_label = status
    elif key == VIDEO_CRACKED_KEY:
        app._video_cracked_progress = progress
        app._video_cracked_sync_label = status
    elif key == LOOSE_PENDING_KEY:
        app._loose_video_progress = progress
        app._loose_video_sync_label = status


def _build_path_only_block(
    app: JavManagerApp,
    parent: ctk.CTkScrollableFrame,
    key: str,
    label: str,
    locations: dict,
) -> None:
    block = ctk.CTkFrame(parent, fg_color="transparent")
    block.pack(fill="x", padx=4, pady=(0, 6))
    row = ctk.CTkFrame(block, fg_color="transparent")
    row.pack(fill="x")
    ctk.CTkLabel(row, text=label, width=90, anchor="w").pack(side="left")
    ctk.CTkButton(
        row, text="+", width=28, height=24, command=lambda k=key: app._add_library_path_row(k, "")
    ).pack(side="right")
    paths_container = ctk.CTkFrame(block, fg_color="transparent")
    paths_container.pack(fill="x", padx=(90, 0), pady=(2, 0))
    app._library_path_containers[key] = paths_container
    for path in locations.get(key, []):
        app._add_library_path_row(key, path)


def _build_browser_panel(app: JavManagerApp, parent: ctk.CTkFrame) -> None:
    ctk.CTkLabel(parent, text="扩展与浏览器", font=ctk.CTkFont(size=14, weight="bold")).grid(
        row=0, column=0, sticky="w", padx=12, pady=(12, 8)
    )

    btn_row = ctk.CTkFrame(parent, fg_color="transparent")
    btn_row.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 8))
    ctk.CTkButton(btn_row, text="打开扩展目录", width=96, command=app._open_extension_folder).pack(side="left", padx=(0, 6))
    ctk.CTkButton(btn_row, text="磁链筛选规则", width=96, command=app._open_magnet_filter_rules).pack(side="left")

    if hasattr(app, "edge_status_label") and app.edge_status_label.winfo_exists():
        ctk.CTkLabel(
            parent,
            text="浏览器连接状态与当前页面请查看窗口顶部栏。",
            anchor="w",
            justify="left",
            wraplength=420,
            text_color=("gray40", "gray60"),
            font=ctk.CTkFont(size=11),
        ).grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 8))
        row_offset = 3
    else:
        status_row = ctk.CTkFrame(parent, fg_color="transparent")
        status_row.grid(row=2, column=0, sticky="new", padx=12, pady=(0, 4))
        app.edge_status_label = ctk.CTkLabel(status_row, text="Edge: ○ 未连接")
        app.edge_status_label.pack(side="left", padx=(0, 12))
        app.browser115_status_label = ctk.CTkLabel(status_row, text="115: ○ 未连接")
        app.browser115_status_label.pack(side="left", padx=(0, 12))
        ctk.CTkCheckBox(
            status_row,
            text="浏览页识别番号后自动筛选",
            variable=app._auto_filter_from_browser,
        ).pack(side="left")

        app.current_page_label = ctk.CTkLabel(
            parent,
            text="当前页面：等待浏览器扩展连接...",
            anchor="w",
            justify="left",
            wraplength=420,
        )
        app.current_page_label.grid(row=3, column=0, sticky="ew", padx=12, pady=(4, 2))

        app.detected_code_label = ctk.CTkLabel(parent, text="当前识别到的番号：（无）", anchor="w")
        app.detected_code_label.grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 4))
        row_offset = 5

    txt_row = ctk.CTkFrame(parent, fg_color="transparent")
    txt_row.grid(row=row_offset, column=0, sticky="ew", padx=12, pady=(0, 4))
    txt_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(txt_row, text="TXT 目录", width=70, anchor="w").grid(row=0, column=0, sticky="w")
    if not hasattr(app, "magnet_txt_dir_var"):
        app.magnet_txt_dir_var = tk.StringVar(value=str(get_magnet_txt_output_dir()))
    ctk.CTkEntry(txt_row, textvariable=app.magnet_txt_dir_var).grid(row=0, column=1, sticky="ew", padx=(0, 6))
    ctk.CTkButton(txt_row, text="浏览", width=56, command=app._browse_magnet_txt_dir).grid(row=0, column=2, padx=(0, 4))
    ctk.CTkButton(txt_row, text="保存", width=48, command=app._save_magnet_txt_dir).grid(row=0, column=3)

    db_row = ctk.CTkFrame(parent, fg_color="transparent")
    db_row.grid(row=row_offset + 1, column=0, sticky="ew", padx=12, pady=(0, 4))
    db_row.grid_columnconfigure(1, weight=1)
    ctk.CTkLabel(db_row, text="操作数据库", width=70, anchor="w").grid(row=0, column=0, sticky="w")
    if not hasattr(app, "state_db_path_var"):
        app.state_db_path_var = tk.StringVar(value=str(get_state_db_path()))
    ctk.CTkEntry(db_row, textvariable=app.state_db_path_var).grid(row=0, column=1, sticky="ew", padx=(0, 6))
    ctk.CTkButton(db_row, text="浏览", width=56, command=app._browse_state_db_path).grid(row=0, column=2, padx=(0, 4))
    ctk.CTkButton(db_row, text="保存", width=48, command=app._save_state_db_path).grid(row=0, column=3, padx=(0, 4))
    ctk.CTkButton(
        db_row,
        text="清空数据库",
        width=88,
        fg_color="#b45309",
        hover_color="#92400e",
        command=app._clear_state_db,
    ).grid(row=0, column=4)
    ctk.CTkLabel(
        parent,
        text=(
            "清空会删除 .db 内全部记录并压缩文件体积，同时通知浏览器扩展重置本地缓存（不会删除影片文件）。"
            "发给他人时只发 release 里的 ZIP，不要附带本机配置目录或源码里的 txt。"
        ),
        anchor="w",
        justify="left",
        wraplength=420,
        text_color=("gray40", "gray60"),
        font=ctk.CTkFont(size=11),
    ).grid(row=row_offset + 2, column=0, sticky="ew", padx=12, pady=(0, 4))

    app.bridge_info_label = ctk.CTkLabel(
        parent,
        text="",
        anchor="w",
        text_color=("gray35", "gray65"),
        font=ctk.CTkFont(size=12),
    )
    app.bridge_info_label.grid(row=row_offset + 3, column=0, sticky="ew", padx=12, pady=(4, 8))

    log_box = ctk.CTkFrame(parent, corner_radius=6, fg_color=("gray90", "gray16"))
    log_box.grid(row=row_offset + 4, column=0, sticky="nsew", padx=12, pady=(0, 12))
    parent.grid_rowconfigure(row_offset + 4, weight=1)
    ctk.CTkLabel(
        log_box,
        text="磁链筛选优先级设置等功能\n请使用上方「磁链筛选规则」按钮",
        justify="center",
        text_color=("gray40", "gray60"),
    ).pack(expand=True, padx=16, pady=24)
