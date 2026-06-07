"""Actress browse tab: card grid -> video list -> detail."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import customtkinter as ctk
from PIL import Image

from src.library_index import IndexedActress, IndexedVideo, build_actress_index, build_library_index
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
from src.ui.video_detail_panel import VideoDetailPanel
from src.ui.video_quick_actions import VideoActionsController

if TYPE_CHECKING:
    from src.app import JavManagerApp


class ActressTabFrame(ctk.CTkFrame):
    def __init__(self, master, *, app: JavManagerApp, **kwargs):
        super().__init__(master, fg_color=LIBRARY_BG, **kwargs)
        self.app = app
        self._actresses: list[IndexedActress] = []
        self._current_actress: IndexedActress | None = None
        self._pending_focus = ""
        self._mode = "grid"
        self._actions = VideoActionsController(app, on_after_delete=self._on_video_deleted, parent_for_dialogs=self)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_grid_view()
        self._build_detail_view()

    def _build_header(self) -> None:
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=4, pady=(0, 6))
        ctk.CTkLabel(head, text="按女优浏览", font=section_font(14), text_color=LIBRARY_HEADING).pack(side="left")
        library_accent_button(head, text="刷新", width=64, height=28, command=self.refresh).pack(side="right")
        library_accent_button(head, text="返回卡片", width=80, height=28, command=self.show_grid).pack(side="right", padx=(0, 6))

    def _build_grid_view(self) -> None:
        self.grid_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.grid_frame.grid(row=1, column=0, sticky="nsew")
        self.grid_frame.grid_columnconfigure(0, weight=1)
        self.grid_frame.grid_rowconfigure(0, weight=1)
        self.card_scroll = ctk.CTkScrollableFrame(self.grid_frame, fg_color=LIBRARY_PANEL, border_color=LIBRARY_BORDER, border_width=1)
        self.card_scroll.grid(row=0, column=0, sticky="nsew")

    def _build_detail_view(self) -> None:
        self.detail_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.detail_frame.grid(row=1, column=0, sticky="nsew")
        self.detail_frame.grid_columnconfigure(1, weight=1)
        self.detail_frame.grid_rowconfigure(0, weight=1)
        self.detail_frame.grid_remove()

        list_box = library_card_frame(self.detail_frame, width=260)
        list_box.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        list_box.grid_rowconfigure(1, weight=1)
        self.actress_title = ctk.CTkLabel(list_box, text="女优", font=section_font(), text_color=LIBRARY_HEADING)
        self.actress_title.grid(row=0, column=0, sticky="w", padx=10, pady=(10, 4))
        self.video_list = ctk.CTkScrollableFrame(list_box, fg_color=LIBRARY_CONTENT, border_color=LIBRARY_BORDER, border_width=1)
        self.video_list.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 10))

        detail_host = library_card_frame(self.detail_frame)
        detail_host.grid(row=0, column=1, sticky="nsew")
        detail_host.grid_columnconfigure(1, weight=1)
        detail_host.grid_rowconfigure(0, weight=1)

        cmd_box = self._actions.build_command_box(detail_host)
        cmd_box.grid(row=0, column=0, sticky="nsw", padx=10, pady=10)

        self.detail_panel = VideoDetailPanel(
            detail_host,
            on_actress_click=lambda _n: None,
            on_category_click=lambda tag: self.app.navigate_to_category([tag]),
            on_categories_changed=self._refresh_current_actress,
        )
        self.detail_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)

    def _on_video_deleted(self) -> None:
        name = self._current_actress.name if self._current_actress else ""
        self._actions.clear_selection()
        self.refresh()
        if name:
            self.focus_actress(name)

    def _refresh_current_actress(self) -> None:
        if self._current_actress is None:
            return
        self.focus_actress(self._current_actress.name)

    def refresh(self) -> None:
        try:
            locations = self.app._collect_library_locations_from_ui()
        except Exception:
            locations = None
        videos = build_library_index(locations)
        self._actresses = build_actress_index(videos, locations)
        self._render_grid()
        if self._pending_focus:
            name = self._pending_focus
            self._pending_focus = ""
            self.focus_actress(name)

    def focus_actress(self, name: str) -> None:
        target = str(name or "").strip()
        if not target:
            return
        if not self._actresses:
            self._pending_focus = target
            self.refresh()
            return
        for actress in self._actresses:
            if actress.name.casefold() == target.casefold():
                self._open_actress(actress)
                return
        self.app.set_status(f"未找到女优: {target}")

    def show_grid(self) -> None:
        self._mode = "grid"
        self._current_actress = None
        self._actions.clear_selection()
        self.detail_frame.grid_remove()
        self.grid_frame.grid()

    def _select_video(self, video: IndexedVideo) -> None:
        self._actions.set_selection(video)
        self.detail_panel.show_video(video)

    def _open_actress(self, actress: IndexedActress) -> None:
        self._current_actress = actress
        self._mode = "detail"
        self.grid_frame.grid_remove()
        self.detail_frame.grid()
        self.actress_title.configure(text=f"{actress.name}（{actress.video_count} 部）")
        for child in self.video_list.winfo_children():
            child.destroy()
        for video in actress.videos:
            ctk.CTkButton(
                self.video_list,
                text=f"{video.code}  {video.title[:28]}",
                anchor="w",
                fg_color="transparent",
                hover_color=LIBRARY_PANEL,
                text_color=LIBRARY_TEXT,
                command=lambda v=video: self._select_video(v),
            ).pack(fill="x", padx=4, pady=2)
        if actress.videos:
            self._select_video(actress.videos[0])
        else:
            self._actions.clear_selection()

    def _render_grid(self) -> None:
        for child in self.card_scroll.winfo_children():
            child.destroy()
        row_frame: ctk.CTkFrame | None = None
        for index, actress in enumerate(self._actresses):
            if index % 4 == 0:
                row_frame = ctk.CTkFrame(self.card_scroll, fg_color="transparent")
                row_frame.pack(fill="x", pady=6)
            card = library_card_frame(row_frame, fg_color=LIBRARY_PANEL, width=170, height=220)
            card.pack(side="left", padx=8)
            card.pack_propagate(False)
            card.configure(cursor="hand2")
            card.bind("<Button-1>", lambda _e, a=actress: self._open_actress(a))
            avatar = ctk.CTkLabel(card, text="头像", width=130, height=130, fg_color=LIBRARY_CONTENT, text_color=LIBRARY_MUTED, cursor="hand2")
            if actress.avatar_path and os.path.isfile(actress.avatar_path):
                try:
                    img = Image.open(actress.avatar_path)
                    thumb = ctk.CTkImage(img, size=(130, 130))
                    avatar.configure(image=thumb, text="")
                except OSError:
                    pass
            avatar.pack(padx=10, pady=(10, 6))
            avatar.bind("<Button-1>", lambda _e, a=actress: self._open_actress(a))
            name_label = ctk.CTkLabel(card, text=actress.name, font=section_font(13), text_color=LIBRARY_TEXT_ON_DARK, cursor="hand2")
            name_label.pack()
            name_label.bind("<Button-1>", lambda _e, a=actress: self._open_actress(a))
            count_label = ctk.CTkLabel(card, text=f"{actress.video_count} 部影片", font=body_font(11), text_color=LIBRARY_MUTED, cursor="hand2")
            count_label.pack(pady=(0, 8))
            count_label.bind("<Button-1>", lambda _e, a=actress: self._open_actress(a))
            ctk.CTkButton(
                card,
                text="查看",
                width=100,
                height=28,
                fg_color=LIBRARY_HEADING,
                hover_color=LIBRARY_BORDER,
                text_color=LIBRARY_BG,
                command=lambda a=actress: self._open_actress(a),
            ).pack(pady=(0, 10))
