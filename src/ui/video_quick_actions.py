"""Shared quick-action buttons for selected videos (library / category / actress tabs)."""

from __future__ import annotations

import os
from tkinter import messagebox, simpledialog
from typing import TYPE_CHECKING, Any, Callable

import customtkinter as ctk

from src.library_index import IndexedVideo
from src.library_media_loader import load_video_detail, open_detail_url
from src.recycle_store import move_video_to_recycle
from src.refined_store import add_refined_video, is_refined_video, remove_refined_video
from src.ui.theme import LIBRARY_HEADING, LIBRARY_PANEL, library_card_frame, library_secondary_button, section_font

if TYPE_CHECKING:
    from src.app import JavManagerApp


def selection_from_payload(payload: dict[str, Any] | IndexedVideo | None) -> dict[str, Any] | None:
    if payload is None:
        return None
    if isinstance(payload, IndexedVideo):
        return {
            "code": payload.code,
            "folder_path": payload.folder_path,
            "video_path": payload.video_path,
            "actress_name": payload.actress_name,
            "label": payload.title,
            "category_key": payload.category_key,
        }
    return dict(payload)


class VideoActionsController:
    """Play / open folder / JavDB / copy / refine / delete for the current selection."""

    def __init__(
        self,
        app: JavManagerApp,
        *,
        on_after_delete: Callable[[], None] | None = None,
        parent_for_dialogs: ctk.Misc | None = None,
    ) -> None:
        self.app = app
        self.on_after_delete = on_after_delete
        self._parent_for_dialogs = parent_for_dialogs
        self._selection: dict[str, Any] | None = None

    def set_selection(self, payload: dict[str, Any] | IndexedVideo | None) -> None:
        self._selection = selection_from_payload(payload)

    def clear_selection(self) -> None:
        self._selection = None

    def build_command_box(self, parent: ctk.Misc, *, width: int = 118) -> ctk.CTkFrame:
        cmd_box = library_card_frame(parent, width=width, fg_color=LIBRARY_PANEL)
        ctk.CTkLabel(cmd_box, text="快捷操作", font=section_font(), text_color=LIBRARY_HEADING).pack(
            anchor="w", padx=10, pady=(10, 6)
        )
        for label, cmd in (
            ("播放影片", self.open_video),
            ("打开文件夹", self.open_folder),
            ("JavDB 详情", self.open_detail),
            ("复制番号", self.copy_code),
            ("加精", self.mark_refined),
            ("删除", self.delete_video),
        ):
            library_secondary_button(cmd_box, text=label, width=96, height=30, command=cmd).pack(padx=8, pady=3)
        return cmd_box

    def open_video(self) -> None:
        if not self._selection:
            self.app.set_status("请先在列表中选择一部影片")
            return
        path = str(self._selection.get("video_path") or "")
        if path and os.path.isfile(path):
            os.startfile(path)  # noqa: S606
        else:
            self.app.set_status("找不到影片文件，请检查路径或重新扫描")

    def open_folder(self) -> None:
        if not self._selection:
            self.app.set_status("请先在列表中选择一部影片")
            return
        path = str(self._selection.get("folder_path") or "")
        if path and os.path.isdir(path):
            os.startfile(path)  # noqa: S606
        else:
            self.app.set_status("找不到文件夹，请检查库路径")

    def open_detail(self) -> None:
        if not self._selection:
            self.app.set_status("请先在列表中选择一部影片")
            return
        detail = load_video_detail(
            folder_path=str(self._selection.get("folder_path") or ""),
            code=str(self._selection.get("code") or ""),
            video_path=str(self._selection.get("video_path") or ""),
            actress_name=str(self._selection.get("actress_name") or ""),
        )
        if open_detail_url(detail.detail_url):
            self.app.set_status(f"已在浏览器打开: {detail.code}")
        else:
            self.app.set_status("无详情页链接，请先同步元数据")

    def copy_code(self) -> None:
        if not self._selection:
            self.app.set_status("请先在列表中选择一部影片")
            return
        code = str(self._selection.get("code") or "")
        if not code:
            return
        self.app.clipboard_clear()
        self.app.clipboard_append(code)
        self.app.set_status(f"已复制番号: {code}")

    def mark_refined(self) -> None:
        if not self._selection:
            self.app.set_status("请先在列表中选择一部影片")
            return
        code = str(self._selection.get("code") or "")
        folder_path = str(self._selection.get("folder_path") or "")
        if is_refined_video(code=code, folder_path=folder_path):
            remove_refined_video(code=code, folder_path=folder_path)
            self.app.set_status(f"已取消加精: {code}")
            if hasattr(self.app, "drain_tab"):
                self.app.drain_tab.refresh()
            return
        title = str(self._selection.get("label") or self._selection.get("title") or code)
        add_refined_video(
            code=code,
            folder_path=folder_path,
            video_path=str(self._selection.get("video_path") or ""),
            title=title,
        )
        self.app.set_status(f"已加精: {code}，可在「榨干!」查看")
        self.app.navigate_to_drain()

    def delete_video(self) -> None:
        if not self._selection:
            self.app.set_status("请先在列表中选择一部影片")
            return
        parent = self._parent_for_dialogs or self.app
        reason = simpledialog.askstring("删除理由", "请输入删除理由：", parent=parent)
        if reason is None or not str(reason).strip():
            return
        code = str(self._selection.get("code") or "")
        folder_path = str(self._selection.get("folder_path") or "")
        video_path = str(self._selection.get("video_path") or "")
        detail = load_video_detail(
            folder_path=folder_path,
            code=code,
            video_path=video_path,
            actress_name=str(self._selection.get("actress_name") or ""),
        )
        title = str(detail.metadata.get("标题") or self._selection.get("label") or code)
        try:
            move_video_to_recycle(
                code=code,
                title=title,
                folder_path=folder_path,
                video_path=video_path,
                reason=str(reason).strip(),
            )
        except (FileNotFoundError, OSError) as exc:
            messagebox.showerror("删除失败", str(exc), parent=parent)
            return
        self._selection = None
        if hasattr(self.app, "trash_tab"):
            self.app.trash_tab.refresh()
        if hasattr(self.app, "library_tab"):
            self.app.library_tab.refresh_tree()
        if self.on_after_delete:
            self.on_after_delete()
        self.app.set_status(f"已移入回收站: {code}")
