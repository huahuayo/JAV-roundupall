"""Main application window."""

from __future__ import annotations

import os
import threading
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from tkinter import filedialog, messagebox
import customtkinter as ctk

from src.bridge_server import bridge_server
from src.bridge_settings import get_bridge_port
from src.browser_state import browser_monitor_state
from src.config import APP_NAME, APP_VERSION, DEFAULT_WINDOW_SIZE, get_app_icon_path, get_extension_dir, get_project_root
from src.magnet_txt_settings import get_magnet_txt_output_dir, set_magnet_txt_output_dir
from src.library_location_settings import (
    LIBRARY_LOCATION_KEYS,
    LibraryLocationError,
    get_library_location_label,
    load_library_locations,
    save_library_locations,
)
from src.pending_download_scanner import PENDING_DOWNLOAD_KEY, scan_pending_download_folders
from src.magnet_saved_scanner import MAGNET_SAVED_KEY, scan_magnet_saved_folders
from src.video_downloaded_scanner import VIDEO_DOWNLOADED_KEY, scan_video_downloaded_folders
from src.library_index import count_videos_by_code
from src.loose_video_scanner import LOOSE_PENDING_KEY, scan_loose_video_roots
from src.video_cracked_scanner import VIDEO_CRACKED_KEY, scan_video_cracked_folders
from src.state_db import clear_all_state_data, get_state_db_path, init_state_database, set_state_db_path
from src.config_sanitize import reset_user_path_settings, sanitize_user_config_on_startup
from src.parser import extract_code_from_text
from src.sticker_store import regenerate_all_txt_files
from src.actress_store import rewrite_collected_actresses_txt
from src.actress_profile_store import rewrite_all_profile_txt_files
from src.magnet_filter_store import load_magnet_filter_rules
from src.magnet_filter_ui import open_magnet_filter_rules_window
from src.ui.app_shell import PAGE_TITLES, build_app_shell
from src.ui.actress_tab import ActressTabFrame
from src.ui.category_tab import CategoryTabFrame
from src.ui.drain_tab import DrainTabFrame
from src.ui.library_tab import LibraryTabFrame
from src.ui.tools_tab import ToolsTabFrame
from src.ui.trash_tab import TrashTabFrame
from src.recycle_store import run_auto_cleanup
from src.ui.settings_panel import build_settings_panel
from src.ui.theme import (
    LIBRARY_BG,
    LIBRARY_HEADING,
    apply_app_theme,
)
from src.win_notify import notify as win_notify


class JavManagerApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_NAME} v{APP_VERSION}")
        self.geometry(DEFAULT_WINDOW_SIZE)
        self.minsize(900, 560)
        icon_path = get_app_icon_path()
        if icon_path is not None:
            try:
                self.iconbitmap(default=str(icon_path))
            except tk.TclError:
                pass

        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        apply_app_theme()

        for notice in sanitize_user_config_on_startup():
            self.after(600, lambda n=notice: self.set_status(n))

        init_state_database()
        regenerate_all_txt_files()
        rewrite_collected_actresses_txt()
        rewrite_all_profile_txt_files()
        load_magnet_filter_rules()
        self._library_path_rows: dict[str, list[dict]] = {}
        self._library_path_containers: dict[str, ctk.CTkFrame] = {}
        self._auto_filter_from_browser = tk.BooleanVar(value=True)

        self._build_layout()
        self._start_bridge()
        browser_monitor_state.add_listener(self._on_browser_state_changed)
        self._refresh_browser_panel()
        removed = run_auto_cleanup()
        if removed:
            self.set_status(f"自动清理回收站 {removed} 项")
        self.after(200, self._show_runtime_hint)

    def _show_runtime_hint(self) -> None:
        self.set_status(f"就绪 · {describe_runtime()}")

    def _start_bridge(self) -> None:
        bridge_server._on_event = self._handle_bridge_event
        bridge_server.start()

    def _handle_bridge_event(self, event: dict) -> None:
        self.after(0, lambda: self._on_bridge_event_ui(event))

    def _on_bridge_event_ui(self, event: dict) -> None:
        self._refresh_browser_panel()
        event_type = event.get("type")
        if event_type == "extension_auth_request":
            self._prompt_extension_auth(event)
        elif event_type == "pending_download_sync_progress":
            self._update_pending_download_progress(event.get("payload") or {})
        elif event_type == "pending_download_sync_folder_done":
            self._update_sync_folder_done(event.get("payload") or {}, "待下载")
        elif event_type == "pending_download_sync_done":
            self._update_pending_download_done(event.get("payload") or {})
            self._refresh_library_tree()
        elif event_type == "magnet_saved_sync_progress":
            self._update_magnet_saved_progress(event.get("payload") or {})
        elif event_type == "magnet_saved_sync_folder_done":
            self._update_sync_folder_done(event.get("payload") or {}, "磁链已保存")
        elif event_type == "magnet_saved_sync_done":
            self._update_magnet_saved_done(event.get("payload") or {})
            self._refresh_library_tree()
        elif event_type == "video_downloaded_sync_progress":
            self._update_video_downloaded_progress(event.get("payload") or {})
        elif event_type == "video_downloaded_sync_folder_done":
            self._update_sync_folder_done(event.get("payload") or {}, "影片已下载")
        elif event_type == "video_downloaded_sync_done":
            self._update_video_downloaded_done(event.get("payload") or {})
            self._refresh_library_tree()
        elif event_type == "video_cracked_sync_progress":
            self._update_video_cracked_progress(event.get("payload") or {})
        elif event_type == "video_cracked_sync_folder_done":
            self._update_sync_folder_done(event.get("payload") or {}, "影片已破解")
        elif event_type == "video_cracked_sync_done":
            self._update_video_cracked_done(event.get("payload") or {})
            self._refresh_library_tree()
        elif event_type == "video_metadata_sync_progress":
            self._update_video_metadata_progress(event.get("payload") or {})
        elif event_type == "video_metadata_folder_done":
            self._update_video_metadata_folder_done(event.get("payload") or {})
        elif event_type == "video_metadata_assets_done":
            self._update_video_metadata_assets_done(event.get("payload") or {})
        elif event_type == "video_metadata_sync_done":
            self._update_video_metadata_done(event.get("payload") or {})
            self._refresh_library_tree()
        elif event_type == "loose_video_sync_progress":
            self._update_loose_video_progress(event.get("payload") or {})
        elif event_type == "loose_video_sync_folder_done":
            self._update_loose_video_folder_done(event.get("payload") or {})
        elif event_type == "loose_video_sync_done":
            self._update_loose_video_done(event.get("payload") or {})
            self._refresh_library_tree()
        elif event_type == "disconnected":
            self._on_extension_disconnected(str(event.get("browser") or ""))
        elif event_type == "tab_update" and self._auto_filter_from_browser.get():
            payload = event.get("payload", {})
            url = str(payload.get("url", ""))
            title = str(payload.get("title", ""))
            code = extract_code_from_text(url) or extract_code_from_text(title)
            if code:
                self._focus_library_code(code)

    def _on_browser_state_changed(self) -> None:
        self.after(0, self._refresh_browser_panel)

    def _refresh_library_tree(self) -> None:
        tab = getattr(self, "library_tab", None)
        if tab is not None:
            tab.refresh_tree()

    _SYNC_START_BUTTONS: tuple[str, ...] = (
        "_pending_download_start_btn",
        "_magnet_saved_start_btn",
        "_video_downloaded_start_btn",
        "_video_cracked_start_btn",
        "_video_cracked_metadata_btn",
        "_loose_video_start_btn",
    )

    def _reset_sync_start_buttons(self) -> None:
        for attr in self._SYNC_START_BUTTONS:
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.configure(state="normal")

    def _on_extension_disconnected(self, browser: str = "") -> None:
        bridge_server.reset_stuck_sync_flags()
        self._reset_sync_start_buttons()
        label = browser or "扩展"
        self.set_status(f"{label} 已断开连接，同步按钮已恢复")

    def _focus_library_code(self, code: str) -> None:
        if not code:
            return
        self.show_page("library")
        if hasattr(self, "library_tab"):
            self.library_tab.focus_code(code)

    def _refresh_browser_panel(self) -> None:
        edge = browser_monitor_state.get_connection("edge")
        b115 = browser_monitor_state.get_connection("115")

        if hasattr(self, "edge_status_label"):
            self.edge_status_label.configure(
                text=self._format_browser_status("Edge", edge.connected),
                text_color=("#15803d", "#4ade80") if edge.connected else ("#b91c1c", "#f87171"),
            )
        if hasattr(self, "browser115_status_label"):
            self.browser115_status_label.configure(
                text=self._format_browser_status("115", b115.connected),
                text_color=("#15803d", "#4ade80") if b115.connected else ("#b91c1c", "#f87171"),
            )

        active = browser_monitor_state.get_active_tab()
        code_text = "当前识别到的番号：（无）"
        code_color = ("gray40", "gray60")

        if active and active.url:
            browser_label = "Edge" if active.browser == "edge" else "115"
            page_hint = f"[{browser_label}] {active.title or active.url}"
            if len(page_hint) > 72:
                page_hint = page_hint[:69] + "…"
            self.set_status(page_hint)
            code = extract_code_from_text(active.url) or extract_code_from_text(active.title or "")
            if code:
                try:
                    locations = self._collect_library_locations_from_ui()
                except tk.TclError:
                    locations = load_library_locations()
                match_count = count_videos_by_code(code, locations)
                if match_count:
                    code_text = f"识别番号: {code}  ·  本地已有 {match_count} 个文件"
                    code_color = ("#15803d", "#4ade80")
                else:
                    code_text = f"识别番号: {code}  ·  本地未找到"
                    code_color = ("#b45309", "#fbbf24")
            else:
                code_text = "识别番号: （当前页面未识别到番号）"
        else:
            if not hasattr(self, "_current_page") or self._current_page == "library":
                self.set_status("等待浏览器扩展连接…")

        if hasattr(self, "detected_code_label"):
            self.detected_code_label.configure(text=code_text, text_color=code_color)
        if hasattr(self, "header_code_entry"):
            entry = self.header_code_entry
            entry.configure(state="normal")
            entry.delete(0, "end")
            if active and active.url:
                code = extract_code_from_text(active.url) or extract_code_from_text(active.title or "")
                if code:
                    entry.insert(0, code)
            elif "识别番号:" in code_text:
                fragment = code_text.split("识别番号:", 1)[-1].strip()
                if fragment and not fragment.startswith("（"):
                    entry.insert(0, fragment.split("·")[0].strip())
            entry.configure(state="disabled")

        port = get_bridge_port()
        if hasattr(self, "bridge_info_label"):
            self.bridge_info_label.configure(
                text=f"桥接端口 ws://127.0.0.1:{port}  ·  扩展首次连接时请在弹窗中点「是」允许"
            )

    def _prompt_extension_auth(self, event: dict) -> None:
        browser = str(event.get("browser") or "浏览器")
        version = str(event.get("version") or "").strip()
        request_id = str(event.get("request_id") or "")
        if not request_id:
            return
        detail = f"（{browser}"
        if version:
            detail += f" · v{version}"
        detail += "）"
        approved = messagebox.askyesno(
            "允许扩展连接",
            f"浏览器扩展{detail} 请求连接本机「{APP_NAME}」。\n\n是否允许？",
            icon=messagebox.QUESTION,
        )
        bridge_server.resolve_extension_auth(request_id, approved)
        if approved:
            self.set_status(f"已允许 {browser} 扩展连接。")
        else:
            self.set_status(f"已拒绝 {browser} 扩展连接。")

    @staticmethod
    def _format_browser_status(name: str, connected: bool) -> str:
        return f"{name}: {'● 已连接' if connected else '○ 未连接'}"

    def _open_extension_folder(self) -> None:
        ext_dir = get_extension_dir()
        if not ext_dir.is_dir():
            messagebox.showerror("未找到扩展", f"扩展目录不存在:\n{ext_dir}")
            return
        os.startfile(str(ext_dir))  # noqa: S606

    def _open_magnet_filter_rules(self) -> None:
        open_magnet_filter_rules_window(self)

    def _browse_magnet_txt_dir(self) -> None:
        folder = filedialog.askdirectory(
            title="选择生成 TXT 的保存文件夹",
            initialdir=self.magnet_txt_dir_var.get() or str(get_project_root()),
        )
        if folder:
            self.magnet_txt_dir_var.set(folder)

    def _save_magnet_txt_dir(self) -> None:
        try:
            path = set_magnet_txt_output_dir(self.magnet_txt_dir_var.get().strip())
        except ValueError:
            messagebox.showerror("目录无效", "请选择有效的文件夹。")
            return
        self.magnet_txt_dir_var.set(str(path))
        self.set_status(f"生成 TXT 目录已保存: {path}")

    def _browse_state_db_path(self) -> None:
        initial = self.state_db_path_var.get() or str(get_state_db_path().parent)
        path = filedialog.asksaveasfilename(
            title="选择操作数据库文件",
            initialdir=initial,
            initialfile="jav_manager_state.db",
            defaultextension=".db",
            filetypes=[("SQLite 数据库", "*.db"), ("所有文件", "*.*")],
        )
        if path:
            self.state_db_path_var.set(path)

    def _save_state_db_path(self) -> None:
        raw = self.state_db_path_var.get().strip()
        try:
            path = set_state_db_path(raw)
        except OSError as exc:
            messagebox.showerror("保存失败", f"无法使用该数据库路径:\n{exc}")
            return
        init_state_database()
        regenerate_all_txt_files()
        rewrite_collected_actresses_txt()
        rewrite_all_profile_txt_files()
        self.state_db_path_var.set(str(path))
        self.set_status(f"操作数据库已保存: {path}（换电脑时复制此文件即可恢复全部操作记录）")

    def _clear_state_db(self) -> None:
        db_path = self.state_db_path_var.get().strip() or str(get_state_db_path())
        if not messagebox.askyesno(
            "清空数据库",
            f"确定清空当前操作数据库中的所有记录？\n\n{db_path}\n\n"
            "此操作不可撤销，不会删除影片文件与元数据，但会清空屏蔽/鉴定/已下载、"
            "收藏女优、同步进度等全部操作记录，并同步重置浏览器扩展中的贴纸缓存。"
            "同时会清空设置页中的库路径、TXT 目录与自定义数据库路径。",
        ):
            return
        try:
            sync_payload = clear_all_state_data()
        except OSError as exc:
            messagebox.showerror("清空失败", str(exc))
            return
        bridge_server.broadcast_threadsafe({"type": "state_db_cleared", **sync_payload})
        self.set_status(f"已清空操作数据库: {db_path}")
        if hasattr(self, "state_db_path_var"):
            self.state_db_path_var.set(str(get_state_db_path()))
        if hasattr(self, "magnet_txt_dir_var"):
            self.magnet_txt_dir_var.set(str(get_magnet_txt_output_dir()))
        if hasattr(self, "_apply_library_locations_to_ui"):
            self._apply_library_locations_to_ui({})
        if hasattr(self, "library_tab"):
            self.library_tab.refresh()
        if hasattr(self, "actress_tab"):
            self.actress_tab.refresh()
        if hasattr(self, "category_tab"):
            self.category_tab.refresh()
        if hasattr(self, "drain_tab"):
            self.drain_tab.refresh()

    def _reset_path_settings(self) -> None:
        if not messagebox.askyesno(
            "清空路径设置",
            "确定清空设置页中所有库路径、TXT 目录与自定义数据库路径？\n\n"
            "不会删除影片文件，也不会清空贴纸/收藏等数据库记录。",
        ):
            return
        reset_user_path_settings()
        if hasattr(self, "state_db_path_var"):
            self.state_db_path_var.set(str(get_state_db_path()))
        if hasattr(self, "magnet_txt_dir_var"):
            self.magnet_txt_dir_var.set(str(get_magnet_txt_output_dir()))
        if hasattr(self, "_apply_library_locations_to_ui"):
            self._apply_library_locations_to_ui({})
        self.set_status("已清空库路径与目录设置")

    def _browse_library_path_var(self, var: tk.StringVar) -> None:
        folder = filedialog.askdirectory(
            title="选择文件夹",
            initialdir=var.get() or str(get_project_root()),
        )
        if folder:
            var.set(folder)

    def _add_library_path_row(self, key: str, path: str = "") -> None:
        container = self._library_path_containers[key]
        row = ctk.CTkFrame(container, fg_color="transparent")
        row.pack(fill="x", pady=2)
        row.grid_columnconfigure(0, weight=1)

        var = tk.StringVar(value=path)
        entry = ctk.CTkEntry(row, textvariable=var, placeholder_text="本地路径或 SMB：\\\\NAS\\共享\\文件夹")
        entry.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        ctk.CTkButton(
            row,
            text="浏览…",
            width=64,
            command=lambda v=var: self._browse_library_path_var(v),
        ).grid(row=0, column=1, padx=(0, 4))
        ctk.CTkButton(
            row,
            text="×",
            width=32,
            command=lambda r=row, v=var: self._remove_library_path_row(key, r, v),
        ).grid(row=0, column=2)

        self._library_path_rows.setdefault(key, []).append({"frame": row, "var": var})

    def _remove_library_path_row(self, key: str, row: ctk.CTkFrame, var: tk.StringVar) -> None:
        rows = self._library_path_rows.get(key, [])
        self._library_path_rows[key] = [item for item in rows if item["var"] is not var]
        row.destroy()

    def _collect_library_locations_from_ui(self) -> dict[str, list[str]]:
        result: dict[str, list[str]] = {}
        for key, _label in LIBRARY_LOCATION_KEYS:
            rows = self._library_path_rows.get(key, [])
            result[key] = [item["var"].get().strip() for item in rows if item["var"].get().strip()]
        return result

    def _apply_library_locations_to_ui(self, locations: dict[str, list[str]]) -> None:
        for key, _label in LIBRARY_LOCATION_KEYS:
            for item in self._library_path_rows.get(key, []):
                item["frame"].destroy()
            self._library_path_rows[key] = []
            for path in locations.get(key, []):
                self._add_library_path_row(key, path)

    def _save_library_locations(self) -> None:
        locations = self._collect_library_locations_from_ui()
        try:
            saved = save_library_locations(locations)
        except LibraryLocationError as exc:
            label = get_library_location_label(exc.key)
            messagebox.showerror(
                "路径无效",
                f"「{label}」中的路径无效：\n{exc.path}\n\n"
                "请填写本地文件夹或局域网 SMB 路径（如 \\\\NAS\\共享\\文件夹）。",
            )
            return

        self._apply_library_locations_to_ui(saved)
        self.set_status("本地库地址已保存")
        self._refresh_library_tree()

    _SYNC_FOLDER_PROGRESS: dict[str, tuple[str, str]] = {
        "待下载": ("_pending_download_progress", "_pending_download_sync_label"),
        "磁链已保存": ("_magnet_saved_progress", "_magnet_saved_sync_label"),
        "影片已下载": ("_video_downloaded_progress", "_video_downloaded_sync_label"),
        "影片已破解": ("_video_cracked_progress", "_video_cracked_sync_label"),
    }

    def _abort_task_start(self, message: str) -> None:
        text = message or "无法开始任务"
        self.set_status(text)
        messagebox.showwarning("无法开始", text)
        if hasattr(self, "show_page"):
            self.show_page("settings")
        elif hasattr(self, "main_tabs"):
            self.main_tabs.set("设置")

    _LIBRARY_SCAN_TIMEOUT_SEC = 300

    def _run_library_scan_task(
        self,
        *,
        label: str,
        scan_fn,
        roots: list[str],
        disable_btn_attrs: tuple[str, ...],
        on_scanned,
    ) -> None:
        if getattr(self, "_library_scan_running", False):
            self.set_status(f"正在扫描「{label}」目录，请稍候…")
            return

        self._library_scan_running = True
        for attr in disable_btn_attrs:
            btn = getattr(self, attr, None)
            if btn is not None:
                btn.configure(state="disabled")
        self.set_status(f"正在扫描「{label}」目录…")
        self.update_idletasks()

        scan_args = (roots if roots else None,)

        def worker() -> None:
            error = ""
            result = None
            try:
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(scan_fn, *scan_args)
                    result = future.result(timeout=self._LIBRARY_SCAN_TIMEOUT_SEC)
            except FutureTimeoutError:
                error = (
                    f"扫描「{label}」目录超时（{self._LIBRARY_SCAN_TIMEOUT_SEC // 60} 分钟），"
                    "请检查网络路径是否可访问"
                )
            except Exception as exc:
                error = str(exc or exc)

            def finish() -> None:
                self._library_scan_running = False
                if error:
                    for attr in disable_btn_attrs:
                        btn = getattr(self, attr, None)
                        if btn is not None:
                            btn.configure(state="normal")
                    self._abort_task_start(error)
                    return
                try:
                    on_scanned(result)
                except Exception as exc:
                    for attr in disable_btn_attrs:
                        btn = getattr(self, attr, None)
                        if btn is not None:
                            btn.configure(state="normal")
                    self._abort_task_start(str(exc or exc))

            self.after(0, finish)

        threading.Thread(target=worker, daemon=True).start()

    def _start_pending_download_task(self) -> None:
        roots = [
            item["var"].get().strip()
            for item in self._library_path_rows.get(PENDING_DOWNLOAD_KEY, [])
            if item["var"].get().strip()
        ]
        folder_records, scan_roots = scan_pending_download_folders(roots if roots else None)
        result = bridge_server.request_pending_download_sync(
            folders=folder_records,
            scan_roots=scan_roots,
        )
        if not result.get("ok"):
            self._abort_task_start(str(result.get("message") or "无法开始任务"))
            return

        if hasattr(self, "_pending_download_progress"):
            self._pending_download_progress.set(0)
        self._update_pending_download_progress(
            {
                "phase": "starting",
                "message": str(result.get("message") or "任务已开始"),
                "current": 0,
                "total": max(len(folder_records), 1),
            }
        )
        if hasattr(self, "_pending_download_start_btn"):
            self._pending_download_start_btn.configure(state="disabled")
        self.set_status(str(result.get("message")))

    def _update_pending_download_progress(self, payload: dict) -> None:
        if not hasattr(self, "_pending_download_progress"):
            return
        total = max(int(payload.get("total") or 0), 1)
        current = min(max(int(payload.get("current") or 0), 0), total)
        self._pending_download_progress.set(current / total)
        message = str(payload.get("message") or "正在同步待下载女优…")
        phase = str(payload.get("phase") or "")
        if phase == "collection":
            detail = "抓取收藏女优列表"
        elif phase == "matching":
            detail = "对照文件夹名称"
        elif phase == "marking":
            detail = "打开女优页并标记"
        else:
            detail = ""
        text = f"{message}（{current}/{total}）" if total > 1 else message
        if detail and detail not in text:
            text = f"{detail}：{text}"
        self._pending_download_sync_label.configure(text=text)
        self._update_global_task_progress(text, current, total)

    def _update_pending_download_done(self, payload: dict) -> None:
        if not hasattr(self, "_pending_download_progress"):
            return
        success = int(payload.get("success_count") or 0)
        total = int(payload.get("total") or 0)
        error = str(payload.get("error") or "")
        log_paths = payload.get("log_paths") or []
        self._pending_download_progress.set(1.0 if total else 0)
        if error:
            self._pending_download_sync_label.configure(text=f"待下载同步失败：{error}")
            self._notify_task_result("待下载同步", f"待下载同步失败：{error}", success=False)
        else:
            log_hint = log_paths[0] if log_paths else ""
            self._pending_download_sync_label.configure(
                text=f"待下载同步完成：成功 {success}/{total}" + (f" · 日志：{log_hint}" if log_hint else "")
            )
            self._notify_task_result("待下载同步", f"待下载同步完成，成功 {success}/{total}")
        if hasattr(self, "_pending_download_start_btn"):
            self._pending_download_start_btn.configure(state="normal")

    def _start_magnet_saved_task(self) -> None:
        roots = [
            item["var"].get().strip()
            for item in self._library_path_rows.get(MAGNET_SAVED_KEY, [])
            if item["var"].get().strip()
        ]
        folder_records, scan_roots = scan_magnet_saved_folders(roots if roots else None)
        result = bridge_server.request_magnet_saved_sync(
            folders=folder_records,
            scan_roots=scan_roots,
        )
        if not result.get("ok"):
            self._abort_task_start(str(result.get("message") or "无法开始任务"))
            return

        if hasattr(self, "_magnet_saved_progress"):
            self._magnet_saved_progress.set(0)
        self._update_magnet_saved_progress(
            {
                "phase": "starting",
                "message": str(result.get("message") or "任务已开始"),
                "current": 0,
                "total": max(len(folder_records), 1),
            }
        )
        if hasattr(self, "_magnet_saved_start_btn"):
            self._magnet_saved_start_btn.configure(state="disabled")
        self.set_status(str(result.get("message")))

    def _update_magnet_saved_progress(self, payload: dict) -> None:
        if not hasattr(self, "_magnet_saved_progress"):
            return
        total = max(int(payload.get("total") or 0), 1)
        current = min(max(int(payload.get("current") or 0), 0), total)
        self._magnet_saved_progress.set(current / total)
        message = str(payload.get("message") or "正在同步磁链已保存…")
        phase = str(payload.get("phase") or "")
        if phase == "collection":
            detail = "抓取收藏女优列表"
        elif phase == "marking":
            detail = "标记磁链已保存"
        else:
            detail = ""
        text = f"{message}（{current}/{total}）" if total > 1 else message
        if detail and detail not in text:
            text = f"{detail}：{text}"
        self._magnet_saved_sync_label.configure(text=text)
        self._update_global_task_progress(text, current, total)

    def _update_magnet_saved_done(self, payload: dict) -> None:
        if not hasattr(self, "_magnet_saved_progress"):
            return
        success = int(payload.get("success_count") or 0)
        total = int(payload.get("total") or 0)
        error = str(payload.get("error") or "")
        log_paths = payload.get("log_paths") or []
        self._magnet_saved_progress.set(1.0 if total else 0)
        if error:
            self._magnet_saved_sync_label.configure(text=f"磁链已保存同步失败：{error}")
            self._notify_task_result("磁链已保存同步", f"磁链已保存同步失败：{error}", success=False)
        else:
            log_hint = log_paths[0] if log_paths else ""
            self._magnet_saved_sync_label.configure(
                text=f"磁链已保存同步完成：成功 {success}/{total} 个女优文件夹"
                + (f" · 日志：{log_hint}" if log_hint else "")
            )
            self._notify_task_result("磁链已保存同步", f"磁链已保存同步完成，成功 {success}/{total} 个女优文件夹")
        if hasattr(self, "_magnet_saved_start_btn"):
            self._magnet_saved_start_btn.configure(state="normal")

    def _start_video_downloaded_task(self) -> None:
        self.set_status("正在准备「已下载」同步任务…")
        roots = [
            item["var"].get().strip()
            for item in self._library_path_rows.get(VIDEO_DOWNLOADED_KEY, [])
            if item["var"].get().strip()
        ]
        folder_records, scan_roots = scan_video_downloaded_folders(roots if roots else None)
        result = bridge_server.request_video_downloaded_sync(
            folders=folder_records,
            scan_roots=scan_roots,
        )
        if not result.get("ok"):
            self._abort_task_start(str(result.get("message") or "无法开始任务"))
            return

        if hasattr(self, "_video_downloaded_progress"):
            self._video_downloaded_progress.set(0)
        self._update_video_downloaded_progress(
            {
                "phase": "starting",
                "message": str(result.get("message") or "任务已开始"),
                "current": 0,
                "total": max(len(folder_records), 1),
            }
        )
        if hasattr(self, "_video_downloaded_start_btn"):
            self._video_downloaded_start_btn.configure(state="disabled")
        self.set_status(str(result.get("message")))

    def _update_video_downloaded_progress(self, payload: dict) -> None:
        if not hasattr(self, "_video_downloaded_progress"):
            return
        total = max(int(payload.get("total") or 0), 1)
        current = min(max(int(payload.get("current") or 0), 0), total)
        self._video_downloaded_progress.set(current / total)
        message = str(payload.get("message") or "正在同步影片已下载…")
        phase = str(payload.get("phase") or "")
        if phase == "collection":
            detail = "抓取收藏女优列表"
        elif phase == "marking":
            detail = "标记已下载"
        else:
            detail = ""
        text = f"{message}（{current}/{total}）" if total > 1 else message
        if detail and detail not in text:
            text = f"{detail}：{text}"
        self._video_downloaded_sync_label.configure(text=text)
        self._update_global_task_progress(text, current, total)

    def _update_video_downloaded_done(self, payload: dict) -> None:
        if not hasattr(self, "_video_downloaded_progress"):
            return
        success = int(payload.get("success_count") or 0)
        total = int(payload.get("total") or 0)
        error = str(payload.get("error") or "")
        log_paths = payload.get("log_paths") or []
        self._video_downloaded_progress.set(1.0 if total else 0)
        if error:
            self._video_downloaded_sync_label.configure(text=f"影片已下载同步失败：{error}")
            self._notify_task_result("影片已下载同步", f"影片已下载同步失败：{error}", success=False)
        else:
            log_hint = log_paths[0] if log_paths else ""
            self._video_downloaded_sync_label.configure(
                text=f"影片已下载同步完成：成功 {success}/{total} 个女优文件夹"
                + (f" · 日志：{log_hint}" if log_hint else "")
            )
            self._notify_task_result("影片已下载同步", f"影片已下载同步完成，成功 {success}/{total} 个女优文件夹")
        if hasattr(self, "_video_downloaded_start_btn"):
            self._video_downloaded_start_btn.configure(state="normal")

    def _start_video_cracked_task(self) -> None:
        roots = [
            item["var"].get().strip()
            for item in self._library_path_rows.get(VIDEO_CRACKED_KEY, [])
            if item["var"].get().strip()
        ]

        def on_scanned(scan_result: tuple[list[dict], list[str]]) -> None:
            folder_records, scan_roots = scan_result
            result = bridge_server.request_video_cracked_sync(
                folders=folder_records,
                scan_roots=scan_roots,
            )
            if not result.get("ok"):
                if hasattr(self, "_video_cracked_start_btn"):
                    self._video_cracked_start_btn.configure(state="normal")
                if hasattr(self, "_video_cracked_metadata_btn"):
                    self._video_cracked_metadata_btn.configure(state="normal")
                self._abort_task_start(str(result.get("message") or "无法开始任务"))
                return

            if hasattr(self, "_video_cracked_progress"):
                self._video_cracked_progress.set(0)
            self._update_video_cracked_progress(
                {
                    "phase": "starting",
                    "message": str(result.get("message") or "任务已开始"),
                    "current": 0,
                    "total": max(len(folder_records), 1),
                }
            )
            self.set_status(str(result.get("message")))

        self._run_library_scan_task(
            label="已破解",
            scan_fn=scan_video_cracked_folders,
            roots=roots,
            disable_btn_attrs=("_video_cracked_start_btn", "_video_cracked_metadata_btn"),
            on_scanned=on_scanned,
        )

    def _update_video_cracked_progress(self, payload: dict) -> None:
        if not hasattr(self, "_video_cracked_progress"):
            return
        total = max(int(payload.get("total") or 0), 1)
        current = min(max(int(payload.get("current") or 0), 0), total)
        self._video_cracked_progress.set(current / total)
        message = str(payload.get("message") or "正在同步影片已破解…")
        phase = str(payload.get("phase") or "")
        if phase == "collection":
            detail = "抓取收藏女优列表"
        elif phase == "marking":
            detail = "标记已破解"
        else:
            detail = ""
        text = f"{message}（{current}/{total}）" if total > 1 else message
        if detail and detail not in text:
            text = f"{detail}：{text}"
        self._video_cracked_sync_label.configure(text=text)
        self._update_global_task_progress(text, current, total)

    def _update_video_cracked_done(self, payload: dict) -> None:
        if not hasattr(self, "_video_cracked_progress"):
            return
        success = int(payload.get("success_count") or 0)
        total = int(payload.get("total") or 0)
        error = str(payload.get("error") or "")
        log_paths = payload.get("log_paths") or []
        self._video_cracked_progress.set(1.0 if total else 0)
        if error:
            self._video_cracked_sync_label.configure(text=f"影片已破解同步失败：{error}")
            self._notify_task_result("影片已破解同步", f"影片已破解同步失败：{error}", success=False)
        else:
            log_hint = log_paths[0] if log_paths else ""
            self._video_cracked_sync_label.configure(
                text=f"影片已破解同步完成：成功 {success}/{total} 个女优文件夹"
                + (f" · 日志：{log_hint}" if log_hint else "")
            )
            self._notify_task_result("影片已破解同步", f"影片已破解同步完成，成功 {success}/{total} 个女优文件夹")
        if hasattr(self, "_video_cracked_start_btn"):
            self._video_cracked_start_btn.configure(state="normal")
        if hasattr(self, "_video_cracked_metadata_btn"):
            self._video_cracked_metadata_btn.configure(state="normal")

    def _start_loose_video_task(self) -> None:
        roots_cfg = [
            item["var"].get().strip()
            for item in self._library_path_rows.get(LOOSE_PENDING_KEY, [])
            if item["var"].get().strip()
        ]
        root_records, scan_roots = scan_loose_video_roots(roots_cfg if roots_cfg else None)
        result = bridge_server.request_loose_video_sync(
            roots=root_records,
            scan_roots=scan_roots,
        )
        if not result.get("ok"):
            self._abort_task_start(str(result.get("message") or "无法开始任务"))
            return

        if hasattr(self, "_loose_video_progress"):
            self._loose_video_progress.set(0)
        self._update_loose_video_progress(
            {
                "phase": "starting",
                "message": str(result.get("message") or "散片任务已开始"),
                "current": 0,
                "total": max(len(root_records), 1),
            }
        )
        if hasattr(self, "_loose_video_start_btn"):
            self._loose_video_start_btn.configure(state="disabled")
        self.set_status(str(result.get("message")))

    def _update_loose_video_progress(self, payload: dict) -> None:
        if not hasattr(self, "_loose_video_progress"):
            return
        total = max(int(payload.get("total") or 0), 1)
        current = min(max(int(payload.get("current") or 0), 0), total)
        self._loose_video_progress.set(current / total)
        message = str(payload.get("message") or "正在处理散片…")
        phase = str(payload.get("phase") or "")
        if phase == "marking":
            detail = "标记与抓取"
        elif phase == "export":
            detail = "重命名与分类"
        else:
            detail = ""
        text = f"[散片] {message}（{current}/{total}）" if total > 1 else f"[散片] {message}"
        if detail and detail not in text:
            text = f"[散片] {detail}：{message}（{current}/{total}）"
        self._loose_video_sync_label.configure(text=text)
        self._update_global_task_progress(text, current, total)

    def _update_loose_video_folder_done(self, payload: dict) -> None:
        if not hasattr(self, "_loose_video_sync_label"):
            return
        folder_result = payload.get("folder_result") or {}
        root_name = str(folder_result.get("root_name") or folder_result.get("root_path") or "")
        success_items = int(folder_result.get("success_items") or 0)
        total_items = int(folder_result.get("total_items") or 0)
        current = int(payload.get("current") or 0)
        total = int(payload.get("total") or 0)
        if current > 0 and total > 0 and hasattr(self, "_loose_video_progress"):
            self._loose_video_progress.set(current / total)
        self._loose_video_sync_label.configure(
            text=f"[散片] 已处理 {root_name} · 成功 {success_items}/{total_items}"
        )
        self.set_status(f"散片：{root_name} 已处理（成功 {success_items}/{total_items}）")

    def _update_loose_video_done(self, payload: dict) -> None:
        if not hasattr(self, "_loose_video_progress"):
            return
        success = int(payload.get("success_count") or 0)
        total = int(payload.get("total") or 0)
        error = str(payload.get("error") or "")
        self._loose_video_progress.set(1.0 if total else 0)
        if error:
            self._loose_video_sync_label.configure(text=f"散片处理失败：{error}")
            self._notify_task_result("散片处理", f"散片处理失败：{error}", success=False)
        else:
            self._loose_video_sync_label.configure(text=f"散片处理完成：成功 {success}/{total} 个目录")
            self._notify_task_result("散片处理", f"散片处理完成，成功 {success}/{total} 个目录")
        if hasattr(self, "_loose_video_start_btn"):
            self._loose_video_start_btn.configure(state="normal")

    def _start_video_metadata_task(self, library_kind: str) -> None:
        if library_kind != VIDEO_CRACKED_KEY:
            self._abort_task_start("影片已下载仅支持 JavDB 同步，请使用「开始同步」")
            return
        label = "已破解"
        roots = [
            item["var"].get().strip()
            for item in self._library_path_rows.get(VIDEO_CRACKED_KEY, [])
            if item["var"].get().strip()
        ]
        progress_attr = "_video_cracked_progress"
        sync_btn_attr = "_video_cracked_start_btn"
        meta_btn_attr = "_video_cracked_metadata_btn"

        def on_scanned(scan_result: tuple[list[dict], list[str]]) -> None:
            folder_records, scan_roots = scan_result
            result = bridge_server.request_video_metadata_sync(
                library_kind=library_kind,
                folders=folder_records,
                scan_roots=scan_roots,
            )
            if not result.get("ok"):
                if hasattr(self, sync_btn_attr):
                    getattr(self, sync_btn_attr).configure(state="normal")
                if hasattr(self, meta_btn_attr):
                    getattr(self, meta_btn_attr).configure(state="normal")
                self._abort_task_start(str(result.get("message") or "无法开始任务"))
                return

            if hasattr(self, progress_attr):
                getattr(self, progress_attr).set(0)
            self._metadata_sync_totals = {
                "catalog_added": 0,
                "covers_added": 0,
                "previews_added": 0,
                "metadata_files": 0,
            }
            self._update_video_metadata_progress(
                {
                    "library_kind": library_kind,
                    "phase": "starting",
                    "message": str(result.get("message") or "元数据任务已开始"),
                    "current": 0,
                    "total": max(len(folder_records), 1),
                }
            )
            self.set_status(str(result.get("message")))

        self._run_library_scan_task(
            label=label,
            scan_fn=scan_video_cracked_folders,
            roots=roots,
            disable_btn_attrs=(sync_btn_attr, meta_btn_attr),
            on_scanned=on_scanned,
        )

    def _start_video_cracked_metadata_task(self) -> None:
        self._start_video_metadata_task(VIDEO_CRACKED_KEY)

    def _update_video_metadata_progress(self, payload: dict) -> None:
        library_kind = str(payload.get("library_kind") or VIDEO_DOWNLOADED_KEY)
        if library_kind == VIDEO_CRACKED_KEY:
            if not hasattr(self, "_video_cracked_progress"):
                return
            progress = self._video_cracked_progress
            label = self._video_cracked_sync_label
        else:
            if not hasattr(self, "_video_downloaded_progress"):
                return
            progress = self._video_downloaded_progress
            label = self._video_downloaded_sync_label

        total = max(int(payload.get("total") or 0), 1)
        current = min(max(int(payload.get("current") or 0), 0), total)
        progress.set(current / total)
        message = str(payload.get("message") or "正在同步元数据…")
        phase = str(payload.get("phase") or "")
        if phase == "collection":
            detail = "抓取收藏女优列表"
        elif phase == "export":
            detail = "写入目录与封面"
        elif phase == "metadata":
            detail = "抓取元数据"
        else:
            detail = ""
        text = f"[元数据] {message}（{current}/{total}）" if total > 1 else f"[元数据] {message}"
        if detail and detail not in text:
            text = f"[元数据] {detail}：{message}（{current}/{total}）"
        label.configure(text=text)
        self._update_global_task_progress(text, current, total)

    def _update_sync_folder_done(self, payload: dict, label_name: str) -> None:
        folder_result = payload.get("folder_result") or {}
        folder_name = str(folder_result.get("folder_name") or "")
        log_path = str(folder_result.get("folder_log_path") or "")
        export_info = folder_result.get("metadata_export") or {}
        detail = log_path or str(export_info.get("catalog_path") or "")

        current = int(payload.get("current") or 0)
        total = int(payload.get("total") or 0)
        attrs = self._SYNC_FOLDER_PROGRESS.get(label_name)
        if attrs and current > 0 and total > 0:
            prog_attr, label_attr = attrs
            if hasattr(self, prog_attr):
                getattr(self, prog_attr).set(current / total)
            if hasattr(self, label_attr):
                getattr(self, label_attr).configure(text=f"{label_name}：{folder_name}（{current}/{total}）")

        if export_info:
            covers = int(export_info.get("covers_added") or 0)
            self.set_status(f"{label_name}：{folder_name} 已写入（封面 {covers} 张）")
        elif detail:
            self.set_status(f"{label_name}：{folder_name} 已写入同步记录")
        else:
            self.set_status(f"{label_name}：{folder_name} 已处理")

    def _update_video_metadata_folder_done(self, payload: dict) -> None:
        library_kind = str(payload.get("library_kind") or VIDEO_DOWNLOADED_KEY)
        folder_result = payload.get("folder_result") or {}
        export_info = folder_result.get("metadata_export") or {}
        totals = getattr(self, "_metadata_sync_totals", None) or {}
        totals["catalog_added"] = int(totals.get("catalog_added") or 0) + int(export_info.get("catalog_added") or 0)
        totals["covers_added"] = int(totals.get("covers_added") or 0) + int(export_info.get("covers_added") or 0)
        totals["previews_added"] = int(totals.get("previews_added") or 0) + int(export_info.get("previews_added") or 0)
        totals["metadata_files"] = int(totals.get("metadata_files") or 0) + int(
            export_info.get("metadata_added") or 0
        ) + int(export_info.get("metadata_updated") or 0)
        self._metadata_sync_totals = totals

        if library_kind == VIDEO_CRACKED_KEY:
            if not hasattr(self, "_video_cracked_sync_label"):
                return
            label = self._video_cracked_sync_label
            progress = self._video_cracked_progress
            label_name = "影片已破解"
        else:
            if not hasattr(self, "_video_downloaded_sync_label"):
                return
            label = self._video_downloaded_sync_label
            progress = self._video_downloaded_progress
            label_name = "影片已下载"

        current = int(payload.get("current") or 0)
        total = int(payload.get("total") or 0)
        if current > 0 and total > 0:
            progress.set(current / total)

        folder_name = str(folder_result.get("folder_name") or "")
        pending_hint = " · 封面下载中" if export_info.get("media_download_pending") else ""
        label.configure(
            text=(
                f"[元数据] 已写入 {folder_name}"
                f" · 累计封面 {totals['covers_added']} · 预览 {totals['previews_added']}"
                f" · 元数据 {totals['metadata_files']}{pending_hint}"
            )
        )
        self.set_status(f"{label_name}元数据：{folder_name} 已写入（封面 {export_info.get('covers_added', 0)} 张）")

    def _update_video_metadata_assets_done(self, payload: dict) -> None:
        library_kind = str(payload.get("library_kind") or VIDEO_DOWNLOADED_KEY)
        download_result = payload.get("download_result") or {}
        totals = getattr(self, "_metadata_sync_totals", None) or {}
        totals["covers_added"] = int(totals.get("covers_added") or 0) + int(download_result.get("covers_added") or 0)
        totals["previews_added"] = int(totals.get("previews_added") or 0) + int(
            download_result.get("previews_added") or 0
        )
        self._metadata_sync_totals = totals

        if library_kind == VIDEO_CRACKED_KEY:
            if not hasattr(self, "_video_cracked_sync_label"):
                return
            label = self._video_cracked_sync_label
        else:
            if not hasattr(self, "_video_downloaded_sync_label"):
                return
            label = self._video_downloaded_sync_label

        folder_name = str(payload.get("folder_name") or "")
        label.configure(
            text=(
                f"[元数据] {folder_name} 封面已下载"
                f" · 累计封面 {totals['covers_added']} · 预览 {totals['previews_added']}"
                f" · 元数据 {totals.get('metadata_files', 0)}"
            )
        )

    def _update_video_metadata_done(self, payload: dict) -> None:
        library_kind = str(payload.get("library_kind") or VIDEO_DOWNLOADED_KEY)
        if library_kind == VIDEO_CRACKED_KEY:
            if not hasattr(self, "_video_cracked_progress"):
                return
            progress = self._video_cracked_progress
            label = self._video_cracked_sync_label
            sync_btn = getattr(self, "_video_cracked_start_btn", None)
            meta_btn = getattr(self, "_video_cracked_metadata_btn", None)
            label_name = "影片已破解"
        else:
            return

        success = int(payload.get("success_count") or 0)
        total = int(payload.get("total") or 0)
        error = str(payload.get("error") or "")
        folder_results = payload.get("folder_results") or []

        catalog_added = sum(int((item.get("metadata_export") or {}).get("catalog_added") or 0) for item in folder_results)
        covers_added = sum(int((item.get("metadata_export") or {}).get("covers_added") or 0) for item in folder_results)
        previews_added = sum(int((item.get("metadata_export") or {}).get("previews_added") or 0) for item in folder_results)
        naming_added = sum(
            int((item.get("metadata_export") or {}).get("metadata_added") or 0)
            + int((item.get("metadata_export") or {}).get("metadata_updated") or 0)
            for item in folder_results
        )
        totals = getattr(self, "_metadata_sync_totals", None) or {}
        if int(totals.get("covers_added") or 0) > 0:
            covers_added = int(totals.get("covers_added") or 0)
        if int(totals.get("previews_added") or 0) > 0:
            previews_added = int(totals.get("previews_added") or 0)
        if int(totals.get("metadata_files") or 0) > 0:
            naming_added = int(totals.get("metadata_files") or 0)
        if int(totals.get("catalog_added") or 0) > 0:
            catalog_added = int(totals.get("catalog_added") or 0)

        progress.set(1.0 if total else 0)
        if error:
            label.configure(text=f"{label_name}元数据同步失败：{error}")
            self._notify_task_result(f"{label_name}元数据同步", f"{label_name}元数据同步失败：{error}", success=False)
        else:
            asset_hint = ""
            if success > 0 and covers_added == 0:
                asset_hint = "（封面未下载，请检查 JavDB/JavBus 登录与网络）"
            label.configure(
                text=(
                    f"{label_name}元数据同步完成：{success}/{total} 个女优文件夹"
                    f" · 目录新增 {catalog_added} · 封面 {covers_added} · 预览图 {previews_added} · 元数据 {naming_added}"
                    f"{asset_hint}"
                )
            )
            notify_msg = (
                f"{label_name}元数据同步完成，成功 {success}/{total} 个女优文件夹"
                + (f"，封面 {covers_added} 张" if covers_added else "，封面未下载")
            )
            self._notify_task_result(f"{label_name}元数据同步", notify_msg)
        if sync_btn:
            sync_btn.configure(state="normal")
        if meta_btn:
            meta_btn.configure(state="normal")

    def destroy(self) -> None:
        bridge_server.stop()
        super().destroy()

    def _update_global_task_progress(self, message: str, current: int, total: int) -> None:
        if not hasattr(self, "global_task_progress"):
            return
        total = max(int(total or 0), 1)
        current = min(max(int(current or 0), 0), total)
        ratio = current / total
        self.global_task_progress.set(ratio)
        percent = int(ratio * 100)
        detail = f"{message}（{current}/{total}） {percent}%"
        if hasattr(self, "global_task_progress_label"):
            self.global_task_progress_label.configure(text=detail)

    def _build_layout(self) -> None:
        content_host = build_app_shell(self)

        self.page_frames["library"] = ctk.CTkFrame(content_host, fg_color=LIBRARY_BG)
        self.library_tab = LibraryTabFrame(self.page_frames["library"], app=self)
        self.library_tab.pack(fill="both", expand=True)

        self.page_frames["actress"] = ctk.CTkFrame(content_host, fg_color=LIBRARY_BG)
        self.actress_tab = ActressTabFrame(self.page_frames["actress"], app=self)
        self.actress_tab.pack(fill="both", expand=True)

        self.page_frames["category"] = ctk.CTkFrame(content_host, fg_color=LIBRARY_BG)
        self.category_tab = CategoryTabFrame(self.page_frames["category"], app=self)
        self.category_tab.pack(fill="both", expand=True)

        self.page_frames["drain"] = ctk.CTkFrame(content_host, fg_color=LIBRARY_BG)
        self.drain_tab = DrainTabFrame(self.page_frames["drain"], app=self)
        self.drain_tab.pack(fill="both", expand=True)

        self.page_frames["tools"] = ctk.CTkFrame(content_host, fg_color=LIBRARY_BG)
        self.tools_tab = ToolsTabFrame(self.page_frames["tools"], app=self)
        self.tools_tab.pack(fill="both", expand=True)

        self.page_frames["trash"] = ctk.CTkFrame(content_host, fg_color=LIBRARY_BG)
        self.trash_tab = TrashTabFrame(self.page_frames["trash"], app=self)
        self.trash_tab.pack(fill="both", expand=True)

        self.page_frames["settings"] = ctk.CTkFrame(content_host, fg_color=LIBRARY_BG)
        settings_shell = ctk.CTkFrame(self.page_frames["settings"], fg_color=LIBRARY_BG)
        settings_shell.pack(fill="both", expand=True, padx=4, pady=4)
        build_settings_panel(self, settings_shell)

        self.library_tab.refresh_tree()
        self.actress_tab.refresh()
        self.category_tab.refresh()
        self.drain_tab.refresh()
        self.tools_tab.refresh()
        self.trash_tab.refresh()
        self.show_page("library")

    def refresh_library_tree(self) -> None:
        self._refresh_library_tree()

    def navigate_to_actress(self, name: str) -> None:
        self.show_page("actress")
        if hasattr(self, "actress_tab"):
            self.actress_tab.focus_actress(name)

    def navigate_to_category(self, tags: list[str]) -> None:
        self.show_page("category")
        if hasattr(self, "category_tab"):
            self.category_tab.set_selected_tags(tags)

    def navigate_to_drain(self) -> None:
        self.show_page("drain")
        if hasattr(self, "drain_tab"):
            self.drain_tab.refresh()

    def show_page(self, page_key: str) -> None:
        frame = self.page_frames.get(page_key)
        if frame is None:
            return
        for child in self.page_stack.winfo_children():
            child.grid_forget()
        frame.grid(row=0, column=0, sticky="nsew")
        title = PAGE_TITLES.get(page_key, page_key)
        if hasattr(self, "page_title_label"):
            self.page_title_label.configure(text=title)
        self._current_page = page_key
        for key, btn in getattr(self, "_nav_buttons", {}).items():
            if key == page_key:
                btn.configure(fg_color=LIBRARY_HEADING, text_color=LIBRARY_BG)
            else:
                btn.configure(fg_color="transparent", text_color=LIBRARY_HEADING)
        if page_key == "actress" and hasattr(self, "actress_tab"):
            self.actress_tab.refresh()
        elif page_key == "category" and hasattr(self, "category_tab"):
            self.category_tab.refresh()
        elif page_key == "drain" and hasattr(self, "drain_tab"):
            self.drain_tab.refresh()
        elif page_key == "tools" and hasattr(self, "tools_tab"):
            self.tools_tab.refresh()
        elif page_key == "trash" and hasattr(self, "trash_tab"):
            self.trash_tab.refresh()

    def _open_library_folder(self) -> None:
        try:
            locations = self._collect_library_locations_from_ui()
        except tk.TclError:
            locations = load_library_locations()

        priority_keys = (
            VIDEO_DOWNLOADED_KEY,
            MAGNET_SAVED_KEY,
            VIDEO_CRACKED_KEY,
            PENDING_DOWNLOAD_KEY,
            LOOSE_PENDING_KEY,
        )
        candidates: list[str] = []
        for key in priority_keys:
            for path in locations.get(key, []):
                if path not in candidates:
                    candidates.append(path)
        for paths in locations.values():
            for path in paths:
                if path not in candidates:
                    candidates.append(path)

        folder = next((path for path in candidates if os.path.isdir(path)), None)
        if not folder:
            messagebox.showinfo("提示", "请先在设置中配置至少一个有效的库文件夹。")
            return
        os.startfile(folder)  # noqa: S606

    def set_status(self, text: str) -> None:
        if hasattr(self, "status_label"):
            self.status_label.configure(text=text)

    def _notify_task_result(self, title: str, message: str, *, success: bool = True) -> None:
        self.set_status(message)
        win_notify(title, message, success=success)


def run_app() -> None:
    app = JavManagerApp()
    app.mainloop()
