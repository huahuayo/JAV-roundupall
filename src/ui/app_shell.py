"""Main window chrome: header, navigation, page stack, task footer."""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from src.config import APP_NAME, APP_VERSION
from src.ui.theme import (
    DANGER,
    LIBRARY_ACCENT,
    LIBRARY_BG,
    LIBRARY_BORDER,
    LIBRARY_CONTENT,
    LIBRARY_HEADING,
    LIBRARY_MUTED,
    LIBRARY_PANEL,
    LIBRARY_TEXT,
    LIBRARY_TEXT_ON_DARK,
    body_font,
    library_accent_button,
    title_font,
)

if TYPE_CHECKING:
    from src.app import JavManagerApp

PAGE_TITLES: dict[str, str] = {
    "library": "影片库",
    "actress": "女优",
    "category": "类别",
    "drain": "榨干!",
    "tools": "其他工具",
    "trash": "回收站",
    "settings": "设置",
}

NAV_ITEMS: tuple[tuple[str, str], ...] = (
    ("library", "影片库"),
    ("actress", "女优"),
    ("category", "类别"),
    ("drain", "榨干!"),
    ("tools", "其他工具"),
    ("trash", "回收站"),
)


def build_app_shell(app: JavManagerApp) -> ctk.CTkFrame:
    """Build header + nav + content host + footer; return the content host frame."""
    app.configure(fg_color=LIBRARY_BG)
    app.grid_columnconfigure(0, weight=1)
    app.grid_rowconfigure(2, weight=1)

    _build_header(app)
    _build_page_title_row(app)
    content_host = _build_content_host(app)
    _build_task_footer(app)
    return content_host


def _build_header(app: JavManagerApp) -> None:
    header = ctk.CTkFrame(app, fg_color=LIBRARY_BG, corner_radius=0)
    header.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
    header.grid_columnconfigure(1, weight=1)
    header.grid_columnconfigure(2, weight=0)

    brand = ctk.CTkFrame(header, fg_color="transparent")
    brand.grid(row=0, column=0, sticky="nw", padx=(16, 8), pady=(10, 4))
    ctk.CTkLabel(
        brand,
        text=f"{APP_NAME}  v{APP_VERSION}",
        font=title_font(18),
        text_color=LIBRARY_ACCENT,
    ).pack(anchor="w")

    nav = ctk.CTkFrame(header, fg_color="transparent")
    nav.grid(row=0, column=1, sticky="n", pady=(14, 4))
    app._nav_buttons: dict[str, ctk.CTkButton] = {}
    for index, (page_key, label) in enumerate(NAV_ITEMS):
        btn = ctk.CTkButton(
            nav,
            text=label,
            width=76 if page_key == "library" else 72,
            height=28,
            fg_color="transparent",
            hover_color=LIBRARY_PANEL,
            text_color=LIBRARY_HEADING,
            font=body_font(13),
            command=lambda k=page_key: app.show_page(k),
        )
        btn.grid(row=0, column=index, padx=6)
        app._nav_buttons[page_key] = btn

    settings_btn = ctk.CTkButton(
        nav,
        text="设置",
        width=56,
        height=28,
        fg_color="transparent",
        hover_color=LIBRARY_PANEL,
        text_color=LIBRARY_HEADING,
        font=body_font(13),
        command=lambda: app.show_page("settings"),
    )
    settings_btn.grid(row=0, column=len(NAV_ITEMS), padx=(12, 6))
    app._nav_buttons["settings"] = settings_btn

    browser_box = ctk.CTkFrame(
        header,
        fg_color=LIBRARY_PANEL,
        corner_radius=8,
        border_width=1,
        border_color=LIBRARY_BORDER,
    )
    browser_box.grid(row=0, column=2, sticky="ne", padx=(8, 16), pady=(8, 6))
    _build_header_browser_panel(app, browser_box)


def _build_header_browser_panel(app: JavManagerApp, parent: ctk.CTkFrame) -> None:
    row = ctk.CTkFrame(parent, fg_color="transparent")
    row.pack(fill="x", padx=8, pady=6)

    ctk.CTkLabel(
        row,
        text="扩展配对",
        font=body_font(11),
        text_color=LIBRARY_HEADING,
    ).pack(side="left", padx=(2, 8))

    app.edge_status_label = ctk.CTkLabel(
        row,
        text="Edge: ○ 未连接",
        font=body_font(11),
        text_color=LIBRARY_MUTED,
    )
    app.edge_status_label.pack(side="left", padx=(0, 8))

    app.browser115_status_label = ctk.CTkLabel(
        row,
        text="115: ○ 未连接",
        font=body_font(11),
        text_color=LIBRARY_MUTED,
    )
    app.browser115_status_label.pack(side="left", padx=(0, 8))

    ctk.CTkCheckBox(
        row,
        text="识别后跳转影片库",
        variable=app._auto_filter_from_browser,
        font=body_font(11),
        text_color=LIBRARY_TEXT_ON_DARK,
        fg_color=LIBRARY_ACCENT,
        hover_color=LIBRARY_ACCENT,
        border_color=LIBRARY_BORDER,
        checkmark_color=LIBRARY_TEXT,
        width=120,
    ).pack(side="left", padx=(0, 8))

    ctk.CTkLabel(row, text="番号", font=body_font(11), text_color=LIBRARY_TEXT_ON_DARK).pack(side="left")
    app.header_code_entry = ctk.CTkEntry(
        row,
        width=88,
        height=24,
        fg_color=LIBRARY_CONTENT,
        text_color=LIBRARY_TEXT,
        border_color=LIBRARY_BORDER,
        placeholder_text="（无）",
        state="disabled",
    )
    app.header_code_entry.pack(side="left", padx=(4, 8))

    library_accent_button(
        row,
        text="刷新",
        width=52,
        height=24,
        command=app._refresh_browser_panel,
    ).pack(side="left", padx=(0, 4))
    library_accent_button(
        row,
        text="打开目录",
        width=72,
        height=24,
        command=app._open_library_folder,
    ).pack(side="left")


def _build_page_title_row(app: JavManagerApp) -> None:
    row = ctk.CTkFrame(app, fg_color=LIBRARY_BG, corner_radius=0)
    row.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 4))
    app.page_title_label = ctk.CTkLabel(
        row,
        text="影片库",
        font=title_font(22),
        text_color=LIBRARY_TEXT_ON_DARK,
        anchor="w",
    )
    app.page_title_label.pack(side="left", anchor="w")


def _build_content_host(app: JavManagerApp) -> ctk.CTkFrame:
    host = ctk.CTkFrame(app, fg_color=LIBRARY_BG, corner_radius=0)
    host.grid(row=2, column=0, sticky="nsew", padx=12, pady=(0, 4))
    host.grid_columnconfigure(0, weight=1)
    host.grid_rowconfigure(0, weight=1)
    app.page_stack = host
    app.page_frames: dict[str, ctk.CTkFrame] = {}
    return host


def _build_task_footer(app: JavManagerApp) -> None:
    footer = ctk.CTkFrame(app, fg_color=LIBRARY_PANEL, corner_radius=0, height=52)
    footer.grid(row=3, column=0, sticky="ew")
    footer.grid_columnconfigure(1, weight=1)

    ctk.CTkLabel(
        footer,
        text="各项任务执行的进度条，百分比",
        font=body_font(11),
        text_color=LIBRARY_MUTED,
    ).grid(row=0, column=0, sticky="w", padx=(16, 8), pady=(8, 0))

    app.global_task_progress_label = ctk.CTkLabel(
        footer,
        text="任务进度将在此显示",
        font=body_font(11),
        text_color=LIBRARY_MUTED,
    )
    app.global_task_progress_label.grid(row=0, column=1, sticky="ew", padx=8, pady=(8, 0))

    app.global_task_progress = ctk.CTkProgressBar(footer, height=8, corner_radius=4)
    app.global_task_progress.configure(progress_color=DANGER[0], fg_color=LIBRARY_BORDER)
    app.global_task_progress.grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(4, 10))
    app.global_task_progress.set(0)

    app.status_label = ctk.CTkLabel(
        footer,
        text="就绪",
        anchor="e",
        text_color=LIBRARY_MUTED,
        font=body_font(11),
    )
    app.status_label.grid(row=0, column=2, sticky="e", padx=(8, 16), pady=(8, 0))
