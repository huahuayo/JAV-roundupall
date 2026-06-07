"""Reusable video detail panel: cover, metadata links, previews."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import messagebox, simpledialog
from typing import Any, Callable

import customtkinter as ctk
from PIL import Image

from src.library_index import IndexedVideo, split_tags
from src.library_media_loader import load_video_detail, open_detail_url
from src.metadata_editor import update_metadata_categories
from src.ui.theme import (
    LIBRARY_BORDER,
    LIBRARY_CONTENT,
    LIBRARY_HEADING,
    LIBRARY_LINK,
    LIBRARY_MUTED,
    LIBRARY_PANEL,
    LIBRARY_TEXT,
    LIBRARY_TEXT_ON_DARK,
    body_font,
    library_card_frame,
    section_font,
)


class VideoDetailPanel(ctk.CTkFrame):
    def __init__(
        self,
        master,
        *,
        on_actress_click: Callable[[str], None] | None = None,
        on_category_click: Callable[[str], None] | None = None,
        on_categories_changed: Callable[[], None] | None = None,
        **kwargs,
    ):
        super().__init__(master, fg_color="transparent", **kwargs)
        self.on_actress_click = on_actress_click
        self.on_category_click = on_category_click
        self.on_categories_changed = on_categories_changed
        self._selection: dict[str, Any] | None = None
        self._cover_image: ctk.CTkImage | None = None
        self._preview_images: list[ctk.CTkImage] = []
        self._view_cover_path = ""

        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=2)
        self.grid_rowconfigure(1, weight=1)
        self._build_widgets()

    def _build_widgets(self) -> None:
        self.cover_box = library_card_frame(self, fg_color=LIBRARY_PANEL)
        self.cover_box.grid(row=0, column=1, sticky="nsew", padx=(0, 5), pady=0)
        self.cover_box.grid_propagate(False)
        self.cover_box.configure(width=230, height=320)
        self.code_title = ctk.CTkLabel(
            self.cover_box,
            text="请选择影片",
            font=section_font(14),
            text_color=LIBRARY_TEXT_ON_DARK,
            wraplength=200,
        )
        self.code_title.pack(anchor="w", padx=10, pady=(10, 4))
        self.cover_label = ctk.CTkLabel(
            self.cover_box,
            text="",
            width=200,
            height=260,
            fg_color=LIBRARY_CONTENT,
            text_color=LIBRARY_TEXT,
            cursor="hand2",
        )
        self.cover_label.pack(padx=10, pady=(0, 10))
        self.cover_label.bind("<Button-1>", lambda _e: self._open_image(self._view_cover_path))

        self.meta_box = library_card_frame(self, fg_color=LIBRARY_PANEL)
        self.meta_box.grid(row=0, column=2, sticky="nsew", padx=(5, 0), pady=0)
        self.meta_box.grid_rowconfigure(1, weight=1)
        self.meta_box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.meta_box, text="元数据", font=section_font(), text_color=LIBRARY_HEADING).grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 4)
        )
        self.meta_scroll = ctk.CTkScrollableFrame(
            self.meta_box,
            fg_color=LIBRARY_CONTENT,
            border_color=LIBRARY_BORDER,
            border_width=1,
        )
        self.meta_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

        self.preview_box = library_card_frame(self, fg_color=LIBRARY_PANEL)
        self.preview_box.grid(row=1, column=1, columnspan=2, sticky="nsew", pady=(10, 0))
        self.preview_box.grid_rowconfigure(1, weight=1)
        self.preview_box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(self.preview_box, text="预览图", font=section_font(), text_color=LIBRARY_HEADING).grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 4)
        )
        self.preview_scroll = ctk.CTkScrollableFrame(
            self.preview_box,
            orientation="horizontal",
            height=180,
            fg_color=LIBRARY_CONTENT,
            border_color=LIBRARY_BORDER,
            border_width=1,
        )
        self.preview_scroll.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))

    def show_video(self, payload: dict[str, Any] | IndexedVideo) -> None:
        if isinstance(payload, IndexedVideo):
            data = {
                "code": payload.code,
                "folder_path": payload.folder_path,
                "video_path": payload.video_path,
                "actress_name": payload.actress_name,
                "label": payload.title,
            }
        else:
            data = dict(payload)
        self._selection = data
        detail = load_video_detail(
            folder_path=str(data.get("folder_path") or ""),
            code=str(data.get("code") or ""),
            video_path=str(data.get("video_path") or ""),
            actress_name=str(data.get("actress_name") or ""),
        )
        self._selection["metadata_path"] = detail.metadata_path
        self._selection["title"] = detail.metadata.get("标题") or detail.code

        title = detail.metadata.get("标题") or detail.code
        short = title[:40] + ("…" if len(title) > 40 else "")
        self.code_title.configure(text=f"{detail.code}\n{short}")
        self._render_metadata(detail)
        self._render_cover(detail)
        self._render_previews(detail)

    def _render_metadata(self, detail) -> None:
        for child in self.meta_scroll.winfo_children():
            child.destroy()

        row = 0
        for label, value in (
            ("番号", detail.code),
            ("文件", _path_display(detail.video_path)),
        ):
            self._meta_line(row, label, value)
            row += 1

        for key in ("标题", "日期", "时长", "导演", "片商", "系列", "评分", "详情页", "JavBus", "破解状态", "是否4K", "有字幕"):
            if detail.metadata.get(key):
                self._meta_line(row, key, str(detail.metadata[key]))
                row += 1

        actress_raw = str(detail.metadata.get("女优") or detail.actress_name or "")
        categories_raw = str(detail.metadata.get("类别") or "")
        row = self._meta_tags_row(row, "女优", split_tags(actress_raw) or ([detail.actress_name] if detail.actress_name else []), self._click_actress)
        row = self._meta_tags_row(row, "类别", split_tags(categories_raw), self._click_category, edit=lambda: self._edit_categories(detail.metadata_path, categories_raw))

        if detail.metadata_path:
            ctk.CTkLabel(
                self.meta_scroll,
                text=f"元数据: {_path_display(detail.metadata_path)}",
                anchor="w",
                text_color=LIBRARY_MUTED,
                font=body_font(11),
                wraplength=360,
            ).grid(row=row, column=0, sticky="w", pady=2)
        elif not detail.metadata:
            ctk.CTkLabel(
                self.meta_scroll,
                text="尚未同步元数据，请在「设置」页执行「同步元数据」。",
                text_color=LIBRARY_MUTED,
                font=body_font(11),
                wraplength=360,
            ).grid(row=row, column=0, sticky="w", pady=4)

    def _meta_line(self, row: int, label: str, value: str) -> None:
        line = ctk.CTkFrame(self.meta_scroll, fg_color="transparent")
        line.grid(row=row, column=0, sticky="ew", pady=1)
        ctk.CTkLabel(line, text=f"{label}: ", width=72, anchor="w", text_color=LIBRARY_TEXT, font=body_font(12)).pack(side="left")
        ctk.CTkLabel(line, text=value, anchor="w", text_color=LIBRARY_TEXT, font=body_font(12), wraplength=360).pack(side="left", fill="x", expand=True)

    def _meta_tags_row(self, row: int, label: str, tags: list[str], click_fn, edit=None) -> int:
        line = ctk.CTkFrame(self.meta_scroll, fg_color="transparent")
        line.grid(row=row, column=0, sticky="ew", pady=1)
        ctk.CTkLabel(line, text=f"{label}: ", width=72, anchor="w", text_color=LIBRARY_TEXT, font=body_font(12)).pack(side="left")
        wrap = ctk.CTkFrame(line, fg_color="transparent")
        wrap.pack(side="left", fill="x", expand=True)
        if not tags:
            ctk.CTkLabel(wrap, text="-", text_color=LIBRARY_TEXT, font=body_font(12)).pack(side="left")
        else:
            for tag in tags:
                ctk.CTkButton(
                    wrap,
                    text=tag,
                    width=max(56, len(tag) * 12),
                    height=24,
                    fg_color="transparent",
                    hover_color=LIBRARY_CONTENT,
                    text_color=LIBRARY_LINK,
                    font=body_font(12),
                    command=lambda t=tag: click_fn(t),
                ).pack(side="left", padx=(0, 4), pady=1)
        if edit:
            ctk.CTkButton(
                line,
                text="编辑",
                width=44,
                height=24,
                fg_color=LIBRARY_PANEL,
                hover_color=LIBRARY_BORDER,
                text_color=LIBRARY_HEADING,
                command=edit,
            ).pack(side="right", padx=(4, 0))
        return row + 1

    def _click_actress(self, name: str) -> None:
        if self.on_actress_click:
            self.on_actress_click(name)

    def _click_category(self, tag: str) -> None:
        if self.on_category_click:
            self.on_category_click(tag)

    def _edit_categories(self, metadata_path: str, current: str) -> None:
        value = simpledialog.askstring("编辑类别", "多个类别请用逗号或顿号分隔：", initialvalue=current, parent=self.winfo_toplevel())
        if value is None:
            return
        if not update_metadata_categories(metadata_path, split_tags(value)):
            messagebox.showerror("保存失败", "无法写入元数据 txt。", parent=self.winfo_toplevel())
            return
        if self._selection:
            self.show_video(self._selection)
        if self.on_categories_changed:
            self.on_categories_changed()

    def _render_cover(self, detail) -> None:
        self._cover_image = None
        self._view_cover_path = ""
        if detail.cover_path and os.path.isfile(detail.cover_path):
            try:
                img = Image.open(detail.cover_path)
                size = _fit_image_size(img, max_w=200, max_h=280)
                self._cover_image = ctk.CTkImage(img, size=size)
                self._view_cover_path = detail.cover_path
                self.cover_label.configure(image=self._cover_image, text="", cursor="hand2")
            except OSError:
                self.cover_label.configure(image=None, text="封面加载失败", cursor="")
        else:
            self.cover_label.configure(image=None, text="暂无封面", cursor="")

    def _render_previews(self, detail) -> None:
        for child in self.preview_scroll.winfo_children():
            child.destroy()
        self._preview_images.clear()
        if detail.preview_paths:
            for path in detail.preview_paths[:24]:
                try:
                    img = Image.open(path)
                    size = _fit_image_size(img, max_w=160, max_h=100)
                    thumb = ctk.CTkImage(img, size=size)
                    self._preview_images.append(thumb)
                    label = ctk.CTkLabel(self.preview_scroll, image=thumb, text="", fg_color=LIBRARY_CONTENT, cursor="hand2")
                    label.bind("<Button-1>", lambda _e, p=path: self._open_image(p))
                    label.pack(side="left", padx=4, pady=6)
                except OSError:
                    continue
        else:
            ctk.CTkLabel(self.preview_scroll, text="暂无预览图", text_color=LIBRARY_MUTED).pack(padx=8, pady=8)

    def _open_image(self, path: str) -> None:
        if path and os.path.isfile(path):
            os.startfile(path)  # noqa: S606


def _path_display(path: str) -> str:
    text = str(path or "")
    return ("…" + text[-77:]) if len(text) > 80 else text


def _fit_image_size(img: Image.Image, *, max_w: int, max_h: int) -> tuple[int, int]:
    width, height = img.size
    if width <= 0 or height <= 0:
        return max_w, max_h
    scale = min(max_w / width, max_h / height, 1.0)
    return max(1, int(width * scale)), max(1, int(height * scale))
