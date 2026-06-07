"""Recycle bin tab."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import customtkinter as ctk
from tkinter import messagebox

from src.recycle_store import (
    clear_recycle_bin,
    get_auto_cleanup_days,
    list_recycle_items,
    restore_recycle_item,
    run_auto_cleanup,
    set_auto_cleanup_days,
)
from src.ui.theme import (
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
    library_card_frame,
    section_font,
)

if TYPE_CHECKING:
    from src.app import JavManagerApp


class TrashTabFrame(ctk.CTkFrame):
    def __init__(self, master, *, app: JavManagerApp, **kwargs):
        super().__init__(master, fg_color=LIBRARY_BG, **kwargs)
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self.list_box = library_card_frame(self)
        self.list_box.grid(row=1, column=0, sticky="nsew")
        self.list_box.grid_rowconfigure(0, weight=1)
        self.scroll = ctk.CTkScrollableFrame(self.list_box, fg_color=LIBRARY_CONTENT, border_color=LIBRARY_BORDER, border_width=1)
        self.scroll.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

    def _build_header(self) -> None:
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkLabel(head, text="回收站", font=section_font(14), text_color=LIBRARY_HEADING).pack(side="left")

        self.cleanup_days_var = ctk.StringVar(value=str(get_auto_cleanup_days()))
        ctk.CTkLabel(head, text="自动清理(天)", text_color=LIBRARY_MUTED, font=body_font(11)).pack(side="right", padx=(8, 4))
        ctk.CTkEntry(head, textvariable=self.cleanup_days_var, width=48).pack(side="right")
        library_accent_button(head, text="保存", width=52, height=28, command=self._save_cleanup_days).pack(side="right", padx=(8, 4))
        library_accent_button(head, text="执行清理", width=80, height=28, command=self._run_cleanup).pack(side="right", padx=(0, 4))
        library_accent_button(head, text="清空回收站", width=96, height=28, command=self._clear_all).pack(side="right", padx=(0, 4))
        library_accent_button(head, text="刷新", width=64, height=28, command=self.refresh).pack(side="right", padx=(0, 4))

    def refresh(self) -> None:
        for child in self.scroll.winfo_children():
            child.destroy()
        items = list_recycle_items()
        if not items:
            ctk.CTkLabel(self.scroll, text="回收站为空", text_color=LIBRARY_MUTED).pack(padx=8, pady=12)
            return
        for item in items:
            row = library_card_frame(self.scroll, fg_color=LIBRARY_PANEL)
            row.pack(fill="x", padx=4, pady=4)
            text = (
                f"{item.get('code')}  {item.get('title') or ''}\n"
                f"删除时间: {item.get('deleted_at')}  ·  理由: {item.get('reason') or '-'}\n"
                f"路径: {item.get('recycle_path')}"
            )
            ctk.CTkLabel(row, text=text, anchor="w", justify="left", text_color=LIBRARY_TEXT_ON_DARK, font=body_font(11), wraplength=760).pack(
                anchor="w", padx=10, pady=(8, 4)
            )
            btn_row = ctk.CTkFrame(row, fg_color="transparent")
            btn_row.pack(anchor="w", padx=10, pady=(0, 8))
            library_accent_button(btn_row, text="恢复", width=64, height=26, command=lambda i=int(item["id"]): self._restore(i)).pack(side="left", padx=(0, 6))
            library_accent_button(btn_row, text="打开文件夹", width=96, height=26, command=lambda p=str(item.get("recycle_path") or ""): self._open_folder(p)).pack(side="left")

    def _restore(self, item_id: int) -> None:
        result = restore_recycle_item(item_id)
        if result.get("ok"):
            self.refresh()
            self.app.refresh_library_tree()
            self.app.set_status(f"已恢复 {result.get('restored_count', 0)} 个文件")
        else:
            messagebox.showerror("恢复失败", str(result.get("message") or "未知错误"))

    def _open_folder(self, path: str) -> None:
        if path and os.path.isdir(path):
            os.startfile(path)  # noqa: S606

    def _clear_all(self) -> None:
        if not messagebox.askyesno("清空回收站", "确定清空回收站中的所有项目？此操作不可撤销。"):
            return
        count = clear_recycle_bin(delete_files=True)
        self.refresh()
        self.app.set_status(f"已清空回收站，删除 {count} 项")

    def _save_cleanup_days(self) -> None:
        try:
            days = int(self.cleanup_days_var.get().strip())
        except ValueError:
            messagebox.showerror("无效天数", "请输入非负整数。")
            return
        set_auto_cleanup_days(days)
        self.app.set_status(f"自动清理天数已设为 {days} 天")

    def _run_cleanup(self) -> None:
        count = run_auto_cleanup()
        self.refresh()
        self.app.set_status(f"自动清理完成，移除 {count} 项")
