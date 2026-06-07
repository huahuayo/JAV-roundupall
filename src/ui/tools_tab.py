"""Custom external tools tab."""

from __future__ import annotations

import os
from tkinter import filedialog
from typing import TYPE_CHECKING

import customtkinter as ctk

from src.custom_tools_store import delete_custom_tool, list_custom_tools, save_custom_tool
from src.ui.theme import (
    LIBRARY_BG,
    LIBRARY_BORDER,
    LIBRARY_CONTENT,
    LIBRARY_HEADING,
    LIBRARY_MUTED,
    LIBRARY_PANEL,
    LIBRARY_TEXT,
    body_font,
    library_accent_button,
    library_card_frame,
    section_font,
)

if TYPE_CHECKING:
    from src.app import JavManagerApp


class ToolsTabFrame(ctk.CTkFrame):
    def __init__(self, master, *, app: JavManagerApp, **kwargs):
        super().__init__(master, fg_color=LIBRARY_BG, **kwargs)
        self.app = app
        self._rows: list[dict] = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkLabel(head, text="其他工具", font=section_font(14), text_color=LIBRARY_HEADING).pack(side="left")
        library_accent_button(head, text="添加工具", width=88, height=28, command=self._add_row).pack(side="right")
        library_accent_button(head, text="保存全部", width=88, height=28, command=self.save_all).pack(side="right", padx=(0, 6))

        self.scroll = ctk.CTkScrollableFrame(self, fg_color=LIBRARY_PANEL, border_color=LIBRARY_BORDER, border_width=1)
        self.scroll.grid(row=1, column=0, sticky="nsew")

    def refresh(self) -> None:
        for child in self.scroll.winfo_children():
            child.destroy()
        self._rows.clear()
        tools = list_custom_tools()
        if not tools:
            self._add_row()
            return
        for tool in tools:
            self._add_row(tool)

    def _add_row(self, tool: dict | None = None) -> None:
        row = ctk.CTkFrame(self.scroll, fg_color=LIBRARY_CONTENT, corner_radius=8, border_color=LIBRARY_BORDER, border_width=1)
        row.pack(fill="x", padx=8, pady=6)
        row.grid_columnconfigure(1, weight=1)

        name_var = ctk.StringVar(value=str((tool or {}).get("name") or ""))
        path_var = ctk.StringVar(value=str((tool or {}).get("executable_path") or ""))
        tool_id = int((tool or {}).get("id") or 0)

        ctk.CTkLabel(row, text="名称", width=40, text_color=LIBRARY_TEXT, font=body_font(11)).grid(row=0, column=0, padx=(8, 4), pady=8, sticky="w")
        ctk.CTkEntry(row, textvariable=name_var, width=140).grid(row=0, column=1, padx=4, pady=8, sticky="w")
        ctk.CTkLabel(row, text="程序路径", width=56, text_color=LIBRARY_TEXT, font=body_font(11)).grid(row=0, column=2, padx=(8, 4), pady=8, sticky="w")
        ctk.CTkEntry(row, textvariable=path_var).grid(row=0, column=3, padx=4, pady=8, sticky="ew")
        ctk.CTkButton(row, text="浏览", width=56, command=lambda v=path_var: self._browse(v)).grid(row=0, column=4, padx=4, pady=8)
        library_accent_button(row, text="运行", width=56, height=28, command=lambda v=path_var: self._run(v.get())).grid(row=0, column=5, padx=4, pady=8)
        ctk.CTkButton(row, text="删除", width=56, fg_color=LIBRARY_PANEL, hover_color=LIBRARY_BORDER, text_color=LIBRARY_HEADING, command=lambda r=row, tid=tool_id: self._delete_row(r, tid)).grid(row=0, column=6, padx=(4, 8), pady=8)

        self._rows.append({"frame": row, "id": tool_id, "name_var": name_var, "path_var": path_var})

    def _browse(self, var: ctk.StringVar) -> None:
        path = filedialog.askopenfilename(title="选择要运行的程序")
        if path:
            var.set(path)

    def _run(self, path: str) -> None:
        exe = str(path or "").strip()
        if not exe or not os.path.isfile(exe):
            self.app.set_status("请先选择有效的程序路径")
            return
        try:
            os.startfile(exe)  # noqa: S606
            self.app.set_status(f"已启动: {exe}")
        except OSError as exc:
            self.app.set_status(f"启动失败: {exc}")

    def save_all(self) -> None:
        for index, row in enumerate(self._rows):
            name = row["name_var"].get().strip()
            path = row["path_var"].get().strip()
            if not name and not path:
                if row["id"]:
                    delete_custom_tool(row["id"])
                continue
            new_id = save_custom_tool(tool_id=row["id"] or None, name=name, executable_path=path, sort_order=index)
            row["id"] = new_id
        self.app.set_status("工具列表已保存")
        self.refresh()

    def _delete_row(self, frame: ctk.CTkFrame, tool_id: int) -> None:
        if tool_id:
            delete_custom_tool(tool_id)
        frame.destroy()
        self._rows = [row for row in self._rows if row["frame"].winfo_exists()]
