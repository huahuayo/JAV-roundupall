"""Category browse tab with multi-select tag filters."""

from __future__ import annotations

from typing import TYPE_CHECKING

import customtkinter as ctk

from src.library_index import IndexedVideo, build_category_index, build_library_index, filter_videos_by_categories
from src.ui.theme import (
    LIBRARY_BG,
    LIBRARY_BORDER,
    LIBRARY_CONTENT,
    LIBRARY_HEADING,
    LIBRARY_LINK,
    LIBRARY_MUTED,
    LIBRARY_PANEL,
    LIBRARY_TEXT,
    body_font,
    library_accent_button,
    library_card_frame,
    section_font,
)
from src.ui.video_detail_panel import VideoDetailPanel
from src.ui.video_quick_actions import VideoActionsController

if TYPE_CHECKING:
    from src.app import JavManagerApp


class CategoryTabFrame(ctk.CTkFrame):
    def __init__(self, master, *, app: JavManagerApp, **kwargs):
        super().__init__(master, fg_color=LIBRARY_BG, **kwargs)
        self.app = app
        self._videos: list[IndexedVideo] = []
        self._selected: set[str] = set()
        self._tag_buttons: dict[str, ctk.CTkButton] = {}
        self._actions = VideoActionsController(app, on_after_delete=self._on_video_deleted, parent_for_dialogs=self)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._build_header()
        self._build_body()

    def _build_header(self) -> None:
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 6))
        ctk.CTkLabel(head, text="按类别筛选（可多选）", font=section_font(14), text_color=LIBRARY_HEADING).pack(side="left")
        library_accent_button(head, text="刷新", width=64, height=28, command=self.refresh).pack(side="right")
        library_accent_button(head, text="清除筛选", width=80, height=28, command=self.clear_selection).pack(side="right", padx=(0, 6))

        self.tag_bar = ctk.CTkScrollableFrame(head, orientation="horizontal", height=42, fg_color=LIBRARY_PANEL, border_color=LIBRARY_BORDER, border_width=1)
        self.tag_bar.pack(side="left", fill="x", expand=True, padx=(12, 12))

    def _build_body(self) -> None:
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
            on_category_click=lambda tag: self.toggle_tag(tag, select=True),
            on_categories_changed=self.refresh,
        )
        self.detail_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)

    def _on_video_deleted(self) -> None:
        self._actions.clear_selection()
        self._apply_filter()

    def _select_video(self, video: IndexedVideo) -> None:
        self._actions.set_selection(video)
        self.detail_panel.show_video(video)

    def refresh(self) -> None:
        try:
            locations = self.app._collect_library_locations_from_ui()
        except Exception:
            locations = None
        self._videos = build_library_index(locations)
        tags = build_category_index(self._videos)
        for child in self.tag_bar.winfo_children():
            child.destroy()
        self._tag_buttons.clear()
        for tag in tags:
            btn = ctk.CTkButton(
                self.tag_bar,
                text=tag,
                height=28,
                fg_color=LIBRARY_PANEL,
                hover_color=LIBRARY_BORDER,
                text_color=LIBRARY_LINK,
                command=lambda t=tag: self.toggle_tag(t),
            )
            btn.pack(side="left", padx=4, pady=6)
            self._tag_buttons[tag.casefold()] = btn
        self._apply_filter()

    def set_selected_tags(self, tags: list[str]) -> None:
        self._selected = {str(tag).casefold() for tag in tags if str(tag).strip()}
        self._apply_filter()

    def toggle_tag(self, tag: str, *, select: bool = False) -> None:
        key = str(tag).casefold()
        if select:
            self._selected.add(key)
        elif key in self._selected:
            self._selected.remove(key)
        else:
            self._selected.add(key)
        self._apply_filter()

    def clear_selection(self) -> None:
        self._selected.clear()
        self._apply_filter()

    def _apply_filter(self) -> None:
        selected_display = {k: v for k, v in ((t.casefold(), t) for t in build_category_index(self._videos))}
        for key, btn in self._tag_buttons.items():
            if key in self._selected:
                btn.configure(fg_color=LIBRARY_HEADING, text_color=LIBRARY_BG)
            else:
                btn.configure(fg_color=LIBRARY_PANEL, text_color=LIBRARY_LINK)
        filtered = filter_videos_by_categories(
            self._videos,
            {selected_display[k] for k in self._selected if k in selected_display},
        )
        for child in self.result_list.winfo_children():
            child.destroy()
        if not filtered:
            ctk.CTkLabel(self.result_list, text="没有匹配的影片", text_color=LIBRARY_MUTED).pack(padx=8, pady=12)
            self._actions.clear_selection()
            return
        for video in filtered:
            ctk.CTkButton(
                self.result_list,
                text=f"{video.code}  {video.title[:30]}",
                anchor="w",
                fg_color="transparent",
                hover_color=LIBRARY_PANEL,
                text_color=LIBRARY_TEXT,
                command=lambda v=video: self._select_video(v),
            ).pack(fill="x", padx=4, pady=2)
