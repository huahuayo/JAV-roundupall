"""Refined (加精) videos tab."""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from src.library_index import IndexedVideo, build_library_index
from src.refined_store import list_refined_videos
from src.ui.theme import (
    LIBRARY_BG,
    LIBRARY_BORDER,
    LIBRARY_CONTENT,
    LIBRARY_HEADING,
    LIBRARY_MUTED,
    LIBRARY_PANEL,
    LIBRARY_TEXT,
    library_accent_button,
    library_card_frame,
    section_font,
)
from src.ui.video_detail_panel import VideoDetailPanel
from src.ui.video_quick_actions import VideoActionsController

if TYPE_CHECKING:
    from src.app import JavManagerApp


class DrainTabFrame(ctk.CTkFrame):
    def __init__(self, master, *, app: JavManagerApp, **kwargs):
        super().__init__(master, fg_color=LIBRARY_BG, **kwargs)
        self.app = app
        self._actions = VideoActionsController(app, on_after_delete=self.refresh, parent_for_dialogs=self)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ctk.CTkLabel(head, text="榨干! · 加精影片", font=section_font(14), text_color=LIBRARY_HEADING).pack(side="left")
        library_accent_button(head, text="刷新", width=64, height=28, command=self.refresh).pack(side="right")

        list_box = library_card_frame(self, width=280)
        list_box.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        list_box.grid_rowconfigure(0, weight=1)
        self.result_list = ctk.CTkScrollableFrame(list_box, fg_color=LIBRARY_CONTENT, border_color=LIBRARY_BORDER, border_width=1)
        self.result_list.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        detail_host = library_card_frame(self)
        detail_host.grid(row=1, column=1, sticky="nsew")
        detail_host.grid_columnconfigure(1, weight=1)
        detail_host.grid_rowconfigure(0, weight=1)

        cmd_box = self._actions.build_command_box(detail_host)
        cmd_box.grid(row=0, column=0, sticky="nsw", padx=10, pady=10)

        self.detail_panel = VideoDetailPanel(
            detail_host,
            on_actress_click=lambda name: self.app.navigate_to_actress(name),
            on_category_click=lambda tag: self.app.navigate_to_category([tag]),
        )
        self.detail_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)

    def refresh(self) -> None:
        try:
            locations = self.app._collect_library_locations_from_ui()
        except Exception:
            locations = None
        refined = {f"{row['code']}|{row['folder_path']}" for row in list_refined_videos()}
        videos = [
            video
            for video in build_library_index(locations)
            if f"{video.code}|{video.folder_path}" in refined
        ]
        for child in self.result_list.winfo_children():
            child.destroy()
        if not videos:
            ctk.CTkLabel(self.result_list, text="暂无加精影片", text_color=LIBRARY_MUTED).pack(padx=8, pady=12)
            self._actions.clear_selection()
            return
        for video in videos:
            ctk.CTkButton(
                self.result_list,
                text=f"{video.code}  {video.title[:26]}",
                anchor="w",
                fg_color="transparent",
                hover_color=LIBRARY_PANEL,
                text_color=LIBRARY_TEXT,
                command=lambda v=video: self._select_video(v),
            ).pack(fill="x", padx=4, pady=2)

    def _select_video(self, video: IndexedVideo) -> None:
        self._actions.set_selection(video)
        self.detail_panel.show_video(video)
