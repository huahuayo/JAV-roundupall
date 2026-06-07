"""影片库 tab: folder tree + media detail panel."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING, Any

import customtkinter as ctk

from src.library_media_loader import build_library_tree
from src.ui.theme import (
    LIBRARY_ACCENT,
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
    library_wide_secondary_button,
    section_font,
)
from src.ui.video_detail_panel import VideoDetailPanel
from src.ui.video_quick_actions import VideoActionsController

if TYPE_CHECKING:
    from src.app import JavManagerApp


class LibraryTabFrame(ctk.CTkFrame):
    """Left tree navigation + right cover/metadata/previews."""

    def __init__(self, master, *, app: JavManagerApp, **kwargs):
        super().__init__(master, fg_color=LIBRARY_BG, **kwargs)
        self.app = app
        self._selection: dict[str, Any] | None = None
        self._node_payload: dict[str, dict[str, Any]] = {}
        self._actions = VideoActionsController(
            app,
            on_after_delete=lambda: setattr(self, "_selection", None),
            parent_for_dialogs=self,
        )

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_detail_panel()

    def _build_sidebar(self) -> None:
        sidebar = library_card_frame(self, width=250)
        sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=0)
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(sidebar, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        ctk.CTkLabel(head, text="目录", font=section_font(14), text_color=LIBRARY_HEADING).pack(side="left")
        library_accent_button(head, text="刷新", width=64, height=28, command=self.refresh_tree).pack(side="right")

        tree_wrap = ctk.CTkFrame(
            sidebar,
            fg_color=LIBRARY_CONTENT,
            corner_radius=6,
            border_width=1,
            border_color=LIBRARY_BORDER,
        )
        tree_wrap.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        tree_wrap.grid_rowconfigure(0, weight=1)
        tree_wrap.grid_columnconfigure(0, weight=1)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "Library.Treeview",
            background=LIBRARY_CONTENT,
            fieldbackground=LIBRARY_CONTENT,
            foreground=LIBRARY_TEXT,
            borderwidth=0,
            rowheight=26,
            font=("Segoe UI", 10),
        )
        style.map(
            "Library.Treeview",
            background=[("selected", LIBRARY_ACCENT)],
            foreground=[("selected", LIBRARY_TEXT)],
        )

        self.tree = ttk.Treeview(tree_wrap, style="Library.Treeview", show="tree", selectmode="browse")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        scroll = ctk.CTkScrollbar(tree_wrap, command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns", pady=4)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)

        ctk.CTkLabel(
            sidebar,
            text="左侧选择影片后，右侧可查看封面、元数据与快捷操作",
            font=body_font(11),
            text_color=LIBRARY_MUTED,
            wraplength=220,
        ).grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 6))
        library_wide_secondary_button(
            sidebar,
            text="打开设置",
            command=lambda: self.app.show_page("settings"),
        ).grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))

    def _build_detail_panel(self) -> None:
        panel = library_card_frame(self)
        panel.grid(row=0, column=1, sticky="nsew")
        panel.grid_columnconfigure(1, weight=1)
        panel.grid_rowconfigure(0, weight=1)

        cmd_box = self._actions.build_command_box(panel)
        cmd_box.grid(row=0, column=0, sticky="nsw", padx=10, pady=10)

        self.detail_panel = VideoDetailPanel(
            panel,
            on_actress_click=lambda name: self.app.navigate_to_actress(name),
            on_category_click=lambda tag: self.app.navigate_to_category([tag]),
            on_categories_changed=self.refresh_tree,
        )
        self.detail_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)

    def _locations_from_app(self) -> dict[str, list[str]] | None:
        if not hasattr(self.app, "_collect_library_locations_from_ui"):
            return None
        try:
            return self.app._collect_library_locations_from_ui()
        except tk.TclError:
            return None

    def refresh_tree(self) -> None:
        expanded: set[str] = set()
        for iid in self.tree.get_children(""):
            if self.tree.item(iid, "open"):
                expanded.add(str(self.tree.item(iid, "text")))

        self.tree.delete(*self.tree.get_children())
        self._node_payload.clear()

        for category in build_library_tree(self._locations_from_app()):
            cat_iid = self.tree.insert("", "end", text=category.label, open=category.label in expanded)
            self._node_payload[cat_iid] = {"kind": "category", "key": category.key}

            if category.key == "loose_pending":
                for video in category.loose_videos:
                    vid_iid = self.tree.insert(cat_iid, "end", text=video.label)
                    self._node_payload[vid_iid] = {
                        "kind": "video",
                        "category_key": category.key,
                        "folder_path": video.folder_path,
                        "actress_name": "",
                        "code": video.code,
                        "video_path": video.video_path,
                        "label": video.label,
                    }
                continue

            for actress in category.actresses:
                act_iid = self.tree.insert(cat_iid, "end", text=actress.name, open=False)
                self._node_payload[act_iid] = {
                    "kind": "actress",
                    "folder_path": actress.folder_path,
                    "actress_name": actress.name,
                }
                for video in actress.videos:
                    vid_iid = self.tree.insert(act_iid, "end", text=video.label)
                    self._node_payload[vid_iid] = {
                        "kind": "video",
                        "category_key": category.key,
                        "folder_path": actress.folder_path,
                        "actress_name": actress.name,
                        "code": video.code,
                        "video_path": video.video_path,
                        "label": video.label,
                    }

        self.app.set_status("影片库目录已更新")

    def focus_code(self, code: str) -> None:
        wanted = str(code or "").strip().upper()
        if not wanted:
            return
        for iid, payload in self._node_payload.items():
            if payload.get("kind") != "video":
                continue
            if str(payload.get("code") or "").upper() != wanted:
                continue
            parent = self.tree.parent(iid)
            while parent:
                self.tree.item(parent, open=True)
                parent = self.tree.parent(parent)
            self.tree.selection_set(iid)
            self.tree.see(iid)
            self._on_tree_select()
            self.app.set_status(f"已定位番号: {wanted}")
            return
        self.app.set_status(f"影片库中未找到番号: {wanted}")

    def _on_tree_select(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        payload = self._node_payload.get(selected[0])
        if not payload or payload.get("kind") != "video":
            self._selection = None
            return
        self._selection = payload
        self._actions.set_selection(payload)
        self.detail_panel.show_video(payload)
