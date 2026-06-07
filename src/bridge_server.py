"""Local WebSocket bridge for browser extensions."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import threading
from datetime import datetime
from typing import Callable

import websockets
from websockets.server import WebSocketServerProtocol

from src.bridge_settings import get_bridge_port, get_bridge_token
from src.browser_state import browser_monitor_state
from src.sticker_store import (
    ACTION_BLOCKED,
    ACTION_DOWNLOADED,
    ACTION_MARKED,
    ACTION_VERIFIED,
    get_sync_payload,
    import_bulk_from_extension,
    record_blocked_series,
    record_blocked_title_keyword,
    record_sticker_action,
    remove_blocked_series,
    remove_blocked_title_keyword,
    remove_sticker_action,
)
from src.actress_store import (
    get_actress_sync_info,
    should_auto_sync_actresses_today,
    sync_collected_actresses,
)
from src.actress_profile_store import (
    init_actress_profile_db,
    record_blocked_actress,
    record_mediocre_actress,
    remove_blocked_actress,
    rewrite_all_profile_txt_files,
)
from src.magnet_txt_store import write_magnet_txt_file
from src.actress_folder_store import lookup_actress_folder_record
from src.magnet_txt_batch_store import find_actress_folder, read_magnet_summary_file, resolve_actress_folder, sanitize_actress_name, write_magnet_batch_files, read_manual_subtitle_file
from src.magnet_filter_store import get_magnet_filter_payload
from src.magnet_txt_settings import get_magnet_txt_settings_payload
from src.pending_download_scanner import (
    apply_synced_folder_renames,
    scan_pending_download_folders,
    scan_pending_download_names,
)
from src.pending_download_store import (
    init_pending_download_db,
    record_pending_download_actress,
    write_pending_download_sync_logs,
)
from src.magnet_saved_scanner import (
    MAGNET_SAVED_KEY,
    apply_magnet_saved_folder_renames,
    scan_magnet_saved_folders,
)
from src.magnet_saved_actress_store import record_magnet_saved_actress
from src.magnet_saved_video_store import record_magnet_saved_video
from src.magnet_saved_store import write_magnet_saved_folder_log, write_magnet_saved_root_logs
from src.sync_folder_rename import apply_sync_folder_renames
from src.loose_video_scanner import LOOSE_PENDING_KEY, scan_loose_video_roots
from src.loose_video_store import finalize_loose_root
from src.video_downloaded_actress_store import record_video_downloaded_actress
from src.video_downloaded_video_store import record_video_downloaded_video
from src.video_downloaded_store import write_video_downloaded_folder_log, write_video_downloaded_root_logs
from src.catalog_reader import (
    TASK_JAVDB,
    apply_metadata_work_filter_to_folders,
    apply_task_filter_to_folders,
)
from src.video_downloaded_scanner import VIDEO_DOWNLOADED_KEY, scan_video_downloaded_folders
from src.video_cracked_scanner import VIDEO_CRACKED_KEY, scan_video_cracked_folders
from src.video_cracked_actress_store import record_video_cracked_actress
from src.video_cracked_video_store import record_video_cracked_video
from src.video_cracked_store import write_video_cracked_folder_log, write_video_cracked_root_logs
from src.video_metadata_store import write_metadata_asset, download_folder_metadata_assets
from src.no_subtitle_txt import write_root_no_subtitle_txt
from src.incremental_sync_export import (
    finalize_magnet_saved_folder,
    finalize_metadata_folder,
    finalize_pending_download_folder,
    finalize_video_cracked_folder,
    finalize_video_downloaded_folder,
)

logger = logging.getLogger(__name__)

MessageHandler = Callable[[dict], None]


def _is_javdb_url(url: str) -> bool:
    return "javdb" in url.lower()


class BridgeServer:
    """Accept WebSocket connections from Chromium extensions on localhost."""

    def __init__(self, on_event: MessageHandler | None = None) -> None:
        self._on_event = on_event
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._server = None
        self._clients: set[WebSocketServerProtocol] = set()
        self._pending_auth: dict[str, dict] = {}
        self._running = False
        self._actress_auto_sync_sent_date: str | None = None
        self._pending_download_running = False
        self._pending_download_session_id = ""
        self._pending_download_started_at = ""
        self._pending_download_scan_roots: list[str] = []
        self._pending_download_folder_names: list[str] = []
        self._pending_download_log_roots: list[str] = []
        self._magnet_saved_running = False
        self._magnet_saved_session_id = ""
        self._magnet_saved_started_at = ""
        self._magnet_saved_scan_roots: list[str] = []
        self._magnet_saved_log_roots: list[str] = []
        self._video_downloaded_running = False
        self._video_downloaded_session_id = ""
        self._video_downloaded_started_at = ""
        self._video_downloaded_scan_roots: list[str] = []
        self._video_downloaded_log_roots: list[str] = []
        self._video_cracked_running = False
        self._video_cracked_session_id = ""
        self._video_cracked_started_at = ""
        self._video_cracked_scan_roots: list[str] = []
        self._video_cracked_log_roots: list[str] = []
        self._video_metadata_running = False
        self._video_metadata_session_id = ""
        self._video_metadata_library_kind = ""
        self._video_metadata_exported_paths: set[str] = set()
        self._pending_download_exported_paths: set[str] = set()
        self._magnet_saved_exported_paths: set[str] = set()
        self._video_downloaded_exported_paths: set[str] = set()
        self._video_cracked_exported_paths: set[str] = set()
        self._loose_video_running = False
        self._loose_video_session_id = ""
        self._loose_video_started_at = ""
        self._loose_video_scan_roots: list[str] = []
        self._loose_video_exported_paths: set[str] = set()

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self.reset_stuck_sync_flags()
        self._running = True
        self._thread = threading.Thread(target=self._run, name="jav-bridge", daemon=True)
        self._thread.start()

    def resolve_extension_auth(self, request_id: str, approved: bool) -> None:
        if not self._loop:
            return

        def _resolve() -> None:
            item = self._pending_auth.get(request_id)
            if not item:
                return
            future = item.get("future")
            if future and not future.done():
                future.set_result(approved)

        self._loop.call_soon_threadsafe(_resolve)

    async def _authenticate_client(
        self,
        websocket: WebSocketServerProtocol,
        message: dict,
        *,
        include_token: bool = False,
    ) -> str:
        browser_name = str(message.get("browser", "edge"))
        self._clients.add(websocket)
        browser_monitor_state.set_connected(
            browser_name,
            connected=True,
            extension_version=str(message.get("version", "")),
        )
        payload: dict = {
            "type": "hello_ack",
            "app": "jav-yiwangdajin",
            "message": "connected",
            "magnet_filter_rules": get_magnet_filter_payload(),
            "magnet_txt_settings": get_magnet_txt_settings_payload(),
        }
        if include_token:
            payload["token"] = get_bridge_token()
        await websocket.send(json.dumps(payload, ensure_ascii=False))
        if self._on_event:
            self._on_event({"type": "connected", "browser": browser_name})
        return browser_name

    async def _await_extension_auth(self, websocket: WebSocketServerProtocol, message: dict) -> bool:
        request_id = secrets.token_hex(8)
        future = self._loop.create_future() if self._loop else asyncio.get_running_loop().create_future()
        self._pending_auth[request_id] = {
            "future": future,
            "websocket": websocket,
            "message": message,
        }
        browser_name = str(message.get("browser", "edge"))
        await websocket.send(
            json.dumps(
                {
                    "type": "auth_pending",
                    "request_id": request_id,
                    "message": "waiting_for_user",
                }
            )
        )
        if self._on_event:
            self._on_event(
                {
                    "type": "extension_auth_request",
                    "request_id": request_id,
                    "browser": browser_name,
                    "version": str(message.get("version", "")),
                }
            )
        try:
            approved = await asyncio.wait_for(future, timeout=300.0)
        except asyncio.TimeoutError:
            approved = False
        finally:
            self._pending_auth.pop(request_id, None)
        return bool(approved)

    def reset_stuck_sync_flags(self) -> None:
        """Clear task-running guards (e.g. after app restart or interrupted sync)."""
        self._pending_download_running = False
        self._magnet_saved_running = False
        self._video_downloaded_running = False
        self._video_cracked_running = False
        self._video_metadata_running = False
        self._loose_video_running = False

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(lambda: asyncio.create_task(self._shutdown()))
        if self._thread:
            self._thread.join(timeout=3)

    def _run(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve())
        finally:
            self._loop.close()

    async def _serve(self) -> None:
        port = get_bridge_port()
        async with websockets.serve(
            self._handle_client,
            "127.0.0.1",
            port,
            ping_interval=20,
            ping_timeout=20,
        ) as server:
            self._server = server
            logger.info("Bridge server listening on ws://127.0.0.1:%s", port)
            while self._running:
                await asyncio.sleep(0.2)

    async def _shutdown(self) -> None:
        for client in list(self._clients):
            await client.close()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    def broadcast_magnet_filter_rules(self) -> None:
        if not self._loop or not self._running:
            return
        payload = get_magnet_filter_payload()
        asyncio.run_coroutine_threadsafe(
            self._broadcast_message(
                {"type": "magnet_filter_rules", "rules": payload},
            ),
            self._loop,
        )

    async def _broadcast_message(self, message: dict) -> None:
        text = json.dumps(message, ensure_ascii=False)
        for client in list(self._clients):
            try:
                await client.send(text)
            except Exception:
                logger.debug("broadcast failed", exc_info=True)

    async def _maybe_request_actress_sync(self, websocket: WebSocketServerProtocol, url: str) -> None:
        if not _is_javdb_url(url):
            return
        if not should_auto_sync_actresses_today():
            return
        today = datetime.now().strftime("%Y-%m-%d")
        if self._actress_auto_sync_sent_date == today:
            return
        self._actress_auto_sync_sent_date = today
        await websocket.send(
            json.dumps(
                {
                    "type": "actress_sync_request",
                    "reason": "daily_auto",
                    "force": False,
                }
            )
        )

    def _folder_export_key(self, folder_result: dict) -> str:
        return str(
            folder_result.get("folder_path")
            or folder_result.get("new_folder_path")
            or ""
        ).strip().casefold()

    async def _emit_sync_folder_done(
        self,
        *,
        event_type: str,
        library_kind: str = "",
        folder_result: dict,
        session_id: str = "",
        current: int = 0,
        total: int = 0,
    ) -> None:
        if not self._on_event:
            return
        payload = {
            "session_id": session_id,
            "folder_result": folder_result,
        }
        if library_kind:
            payload["library_kind"] = library_kind
        if current > 0:
            payload["current"] = current
        if total > 0:
            payload["total"] = total
        self._on_event({"type": event_type, "payload": payload})

    async def _download_metadata_folder_assets(self, folder_result: dict, library_kind: str) -> None:
        folder_path = str(folder_result.get("folder_path") or "").strip()
        if not folder_path:
            return

        actress = folder_result.get("actress") or {}
        actress_name = str(
            actress.get("name") or folder_result.get("actress_match_name") or folder_result.get("folder_name") or ""
        )
        code_results = folder_result.get("code_results") or []
        if not isinstance(code_results, list):
            code_results = []

        def run() -> dict:
            return download_folder_metadata_assets(
                folder_path,
                actress_name=actress_name,
                library_kind=library_kind,
                code_results=code_results,
            )

        try:
            result = await asyncio.to_thread(run)
        except OSError as exc:
            logger.warning("Background metadata download failed for %s: %s", folder_path, exc)
            return

        if not self._on_event or not result.get("ok"):
            return
        self._on_event(
            {
                "type": "video_metadata_assets_done",
                "payload": {
                    "library_kind": library_kind,
                    "folder_path": folder_path,
                    "folder_name": str(folder_result.get("folder_name") or ""),
                    "download_result": result,
                },
            }
        )

    async def _reply_sync_folder_ack(self, websocket, *, ack_type: str, folder_result: dict) -> None:
        await websocket.send(
            json.dumps(
                {
                    "type": ack_type,
                    "ok": True,
                    "folder_result": folder_result,
                },
                ensure_ascii=False,
            )
        )

    def _catch_up_folder_exports(
        self,
        folder_results: list[dict],
        *,
        exported_paths: set[str],
        finalize_fn,
        session_id: str,
    ) -> list[dict]:
        updated: list[dict] = []
        for item in folder_results:
            key = self._folder_export_key(item)
            if key and key in exported_paths:
                updated.append(item)
                continue
            updated.append(finalize_fn(item, session_id=session_id))
        return updated

    async def _launch_pending_download_sync(self, folders: list[dict], scan_roots: list[str]) -> None:
        self._pending_download_running = True
        self._pending_download_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._pending_download_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._pending_download_scan_roots = scan_roots
        self._pending_download_folder_names = [str(item.get("folder_name") or "") for item in folders]
        self._pending_download_log_roots = scan_roots
        self._pending_download_exported_paths = set()

        progress = {
            "phase": "starting",
            "message": f"已扫描 {len(folders)} 个待下载文件夹，正在后台对照 JavDB…",
            "current": 0,
            "total": len(folders),
        }
        if self._on_event:
            self._on_event({"type": "pending_download_sync_progress", "payload": progress})

        await self.broadcast(
            {
                "type": "pending_download_sync_request",
                "folders": folders,
                "folder_names": self._pending_download_folder_names,
                "log_roots": scan_roots,
                "session_id": self._pending_download_session_id,
            }
        )

    def request_pending_download_sync(
        self,
        *,
        folders: list[dict] | None = None,
        folder_names: list[str] | None = None,
        scan_roots: list[str] | None = None,
    ) -> dict[str, str | bool]:
        if self._pending_download_running:
            return {"ok": False, "message": "待下载对照任务正在进行中"}

        if folders is None:
            folders, scan_roots = scan_pending_download_folders(scan_roots)
        elif scan_roots is None:
            _, scan_roots = scan_pending_download_folders()

        if not scan_roots:
            return {"ok": False, "message": "请先配置待下载目录（保存后或填写有效路径）"}
        if not folders:
            return {"ok": False, "message": "待下载目录下没有待处理的女优文件夹（已跳过「1 …」前缀文件夹）"}
        if not self._clients:
            return {"ok": False, "message": "浏览器扩展未连接，请先打开 JavDB 并完成配对"}
        if not self._loop or not self._loop.is_running():
            return {"ok": False, "message": "桥接服务未就绪"}

        asyncio.run_coroutine_threadsafe(
            self._launch_pending_download_sync(folders, scan_roots),
            self._loop,
        )
        return {
            "ok": True,
            "message": f"已在后台开始对照 {len(folders)} 个女优文件夹",
        }

    async def _launch_magnet_saved_sync(self, folders: list[dict], scan_roots: list[str]) -> None:
        self._magnet_saved_running = True
        self._magnet_saved_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._magnet_saved_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._magnet_saved_scan_roots = scan_roots
        self._magnet_saved_log_roots = scan_roots
        self._magnet_saved_exported_paths = set()

        progress = {
            "phase": "starting",
            "message": f"已扫描 {len(folders)} 个磁链已保存文件夹，正在后台对照 JavDB…",
            "current": 0,
            "total": len(folders),
        }
        if self._on_event:
            self._on_event({"type": "magnet_saved_sync_progress", "payload": progress})

        await self.broadcast(
            {
                "type": "magnet_saved_sync_request",
                "folders": folders,
                "log_roots": scan_roots,
                "session_id": self._magnet_saved_session_id,
            }
        )

    def request_magnet_saved_sync(
        self,
        *,
        folders: list[dict] | None = None,
        scan_roots: list[str] | None = None,
    ) -> dict[str, str | bool]:
        if self._magnet_saved_running:
            return {"ok": False, "message": "磁链已保存同步任务正在进行中"}

        if folders is None:
            folders, scan_roots = scan_magnet_saved_folders(scan_roots)
        elif scan_roots is None:
            _, scan_roots = scan_magnet_saved_folders()

        if not scan_roots:
            return {"ok": False, "message": "请先配置磁链已保存目录（保存后或填写有效路径）"}
        if not folders:
            return {
                "ok": False,
                "message": "磁链已保存目录下没有含 TXT 的女优文件夹",
            }
        if not self._clients:
            return {"ok": False, "message": "浏览器扩展未连接，请先打开 JavDB 并完成配对"}
        if not self._loop or not self._loop.is_running():
            return {"ok": False, "message": "桥接服务未就绪"}

        asyncio.run_coroutine_threadsafe(
            self._launch_magnet_saved_sync(folders, scan_roots),
            self._loop,
        )
        return {
            "ok": True,
            "message": f"已在后台开始同步 {len(folders)} 个女优文件夹",
        }

    def _emit_magnet_saved_done(
        self,
        *,
        folder_results: list[dict],
        error: str = "",
        log_paths: list[str] | None = None,
    ) -> None:
        self._magnet_saved_running = False
        if not self._on_event:
            return
        success_folders = sum(1 for item in folder_results if item.get("ok"))
        self._on_event(
            {
                "type": "magnet_saved_sync_done",
                "payload": {
                    "session_id": self._magnet_saved_session_id,
                    "success_count": success_folders,
                    "total": len(folder_results),
                    "error": error,
                    "log_paths": log_paths or [],
                },
            }
        )

    def request_video_downloaded_sync(
        self,
        *,
        folders: list[dict] | None = None,
        scan_roots: list[str] | None = None,
    ) -> dict[str, str | bool]:
        if self._video_downloaded_running:
            return {"ok": False, "message": "影片已下载同步任务正在进行中"}

        if folders is None:
            folders, scan_roots = scan_video_downloaded_folders(scan_roots)
        elif scan_roots is None:
            _, scan_roots = scan_video_downloaded_folders()

        folders, catalog_skipped = apply_task_filter_to_folders(folders, TASK_JAVDB)

        if not scan_roots:
            return {"ok": False, "message": "请先配置影片已下载目录（保存后或填写有效路径）"}
        if not folders:
            skip_hint = f"（目录.txt 中 {catalog_skipped} 个番号 JavDB同步=是，已跳过）" if catalog_skipped else ""
            return {
                "ok": False,
                "message": f"影片已下载目录下没有待 JavDB 同步的番号{skip_hint}",
            }
        if not self._clients:
            return {"ok": False, "message": "浏览器扩展未连接，请先打开 JavDB 并完成配对"}
        if not self._loop or not self._loop.is_running():
            return {"ok": False, "message": "桥接服务未就绪"}

        asyncio.run_coroutine_threadsafe(
            self._launch_video_downloaded_sync(folders, scan_roots),
            self._loop,
        )
        return {
            "ok": True,
            "message": f"已在后台开始同步 {len(folders)} 个女优文件夹"
            + (f"（跳过目录.txt 中 JavDB已同步 {catalog_skipped} 个番号）" if catalog_skipped else ""),
        }

    async def _launch_video_downloaded_sync(self, folders: list[dict], scan_roots: list[str]) -> None:
        self._video_downloaded_running = True
        self._video_downloaded_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._video_downloaded_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._video_downloaded_scan_roots = scan_roots
        self._video_downloaded_log_roots = scan_roots
        self._video_downloaded_exported_paths = set()

        progress = {
            "phase": "starting",
            "message": f"已扫描 {len(folders)} 个影片已下载文件夹，正在后台对照 JavDB…",
            "current": 0,
            "total": len(folders),
        }
        if self._on_event:
            self._on_event({"type": "video_downloaded_sync_progress", "payload": progress})

        await self.broadcast(
            {
                "type": "video_downloaded_sync_request",
                "folders": folders,
                "log_roots": scan_roots,
                "session_id": self._video_downloaded_session_id,
            }
        )

    def _emit_video_downloaded_done(
        self,
        *,
        folder_results: list[dict],
        error: str = "",
        log_paths: list[str] | None = None,
    ) -> None:
        self._video_downloaded_running = False
        if not self._on_event:
            return
        success_folders = sum(1 for item in folder_results if item.get("ok"))
        self._on_event(
            {
                "type": "video_downloaded_sync_done",
                "payload": {
                    "session_id": self._video_downloaded_session_id,
                    "success_count": success_folders,
                    "total": len(folder_results),
                    "error": error,
                    "log_paths": log_paths or [],
                },
            }
        )

    def request_video_cracked_sync(
        self,
        *,
        folders: list[dict] | None = None,
        scan_roots: list[str] | None = None,
    ) -> dict[str, str | bool]:
        if self._video_cracked_running:
            return {"ok": False, "message": "影片已破解同步任务正在进行中"}

        if folders is None:
            folders, scan_roots = scan_video_cracked_folders(scan_roots)
        elif scan_roots is None:
            _, scan_roots = scan_video_cracked_folders()

        folders, catalog_skipped = apply_task_filter_to_folders(folders, TASK_JAVDB)

        if not scan_roots:
            return {"ok": False, "message": "请先配置影片已破解目录（保存后或填写有效路径）"}
        if not folders:
            skip_hint = f"（目录.txt 中 {catalog_skipped} 个番号 JavDB同步=是，已跳过）" if catalog_skipped else ""
            return {
                "ok": False,
                "message": f"影片已破解目录下没有待 JavDB 同步的番号{skip_hint}",
            }
        if not self._clients:
            return {"ok": False, "message": "浏览器扩展未连接，请先打开 JavDB 并完成配对"}
        if not self._loop or not self._loop.is_running():
            return {"ok": False, "message": "桥接服务未就绪"}

        asyncio.run_coroutine_threadsafe(
            self._launch_video_cracked_sync(folders, scan_roots),
            self._loop,
        )
        return {
            "ok": True,
            "message": f"已在后台开始同步 {len(folders)} 个女优文件夹"
            + (f"（跳过目录.txt 中 JavDB已同步 {catalog_skipped} 个番号）" if catalog_skipped else ""),
        }

    async def _launch_video_cracked_sync(self, folders: list[dict], scan_roots: list[str]) -> None:
        self._video_cracked_running = True
        self._video_cracked_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._video_cracked_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._video_cracked_scan_roots = scan_roots
        self._video_cracked_log_roots = scan_roots
        self._video_cracked_exported_paths = set()

        progress = {
            "phase": "starting",
            "message": f"已扫描 {len(folders)} 个影片已破解文件夹，正在后台对照 JavDB…",
            "current": 0,
            "total": len(folders),
        }
        if self._on_event:
            self._on_event({"type": "video_cracked_sync_progress", "payload": progress})

        await self.broadcast(
            {
                "type": "video_cracked_sync_request",
                "folders": folders,
                "log_roots": scan_roots,
                "session_id": self._video_cracked_session_id,
            }
        )

    def _emit_video_cracked_done(
        self,
        *,
        folder_results: list[dict],
        error: str = "",
        log_paths: list[str] | None = None,
    ) -> None:
        self._video_cracked_running = False
        if not self._on_event:
            return
        success_folders = sum(1 for item in folder_results if item.get("ok"))
        self._on_event(
            {
                "type": "video_cracked_sync_done",
                "payload": {
                    "session_id": self._video_cracked_session_id,
                    "success_count": success_folders,
                    "total": len(folder_results),
                    "error": error,
                    "log_paths": log_paths or [],
                },
            }
        )

    def request_loose_video_sync(
        self,
        *,
        roots: list[dict] | None = None,
        scan_roots: list[str] | None = None,
    ) -> dict[str, str | bool]:
        if self._loose_video_running:
            return {"ok": False, "message": "散片处理任务正在进行中"}

        if roots is None:
            roots, scan_roots = scan_loose_video_roots(scan_roots)
        elif scan_roots is None:
            _, scan_roots = scan_loose_video_roots()

        catalog_skipped = sum(int(item.get("catalog_skip_count") or 0) for item in roots)

        if not scan_roots:
            return {"ok": False, "message": "请先配置散片待处理目录（保存后或填写有效路径）"}
        if not roots:
            skip_hint = f"（已跳过 {catalog_skipped} 个目录.txt 中已有番号）" if catalog_skipped else ""
            return {
                "ok": False,
                "message": f"散片目录下没有待处理的影片{skip_hint}",
            }
        if not self._clients:
            return {"ok": False, "message": "浏览器扩展未连接，请先打开 JavDB 并完成配对"}
        if not self._loop or not self._loop.is_running():
            return {"ok": False, "message": "桥接服务未就绪"}

        asyncio.run_coroutine_threadsafe(
            self._launch_loose_video_sync(roots, scan_roots),
            self._loop,
        )
        total_items = sum(len(item.get("items") or []) for item in roots)
        return {
            "ok": True,
            "message": f"已在后台开始处理 {len(roots)} 个散片目录、共 {total_items} 部影片"
            + (f"（跳过目录.txt 中 {catalog_skipped} 个番号）" if catalog_skipped else ""),
        }

    async def _launch_loose_video_sync(self, roots: list[dict], scan_roots: list[str]) -> None:
        self._loose_video_running = True
        self._loose_video_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._loose_video_started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._loose_video_scan_roots = scan_roots
        self._loose_video_exported_paths = set()

        total_items = sum(len(item.get("items") or []) for item in roots)
        progress = {
            "phase": "starting",
            "message": f"已扫描 {total_items} 部散片，正在后台对照 JavDB…",
            "current": 0,
            "total": max(len(roots), 1),
        }
        if self._on_event:
            self._on_event({"type": "loose_video_sync_progress", "payload": progress})

        await self.broadcast(
            {
                "type": "loose_video_sync_request",
                "roots": roots,
                "session_id": self._loose_video_session_id,
            }
        )

    def _emit_loose_video_done(
        self,
        *,
        root_results: list[dict],
        error: str = "",
    ) -> None:
        self._loose_video_running = False
        if not self._on_event:
            return
        success_roots = sum(1 for item in root_results if item.get("ok"))
        self._on_event(
            {
                "type": "loose_video_sync_done",
                "payload": {
                    "session_id": self._loose_video_session_id,
                    "success_count": success_roots,
                    "total": len(root_results),
                    "error": error,
                    "root_results": root_results,
                },
            }
        )

    def request_video_metadata_sync(
        self,
        *,
        library_kind: str,
        folders: list[dict] | None = None,
        scan_roots: list[str] | None = None,
    ) -> dict[str, str | bool]:
        if self._video_metadata_running:
            return {"ok": False, "message": "元数据同步任务正在进行中"}

        if library_kind == VIDEO_CRACKED_KEY:
            scan_fn = scan_video_cracked_folders
            label = "影片已破解"
        elif library_kind == VIDEO_DOWNLOADED_KEY:
            return {"ok": False, "message": "影片已下载仅支持 JavDB 同步，请使用「开始同步」"}
        else:
            return {"ok": False, "message": f"不支持的库类型: {library_kind}"}

        if folders is None:
            folders, scan_roots = scan_fn(scan_roots)
        elif scan_roots is None:
            _, scan_roots = scan_fn()

        folders, catalog_skipped = apply_metadata_work_filter_to_folders(folders)

        if not scan_roots:
            return {"ok": False, "message": f"请先配置{label}目录（保存后或填写有效路径）"}
        if not folders:
            skip_hint = f"（目录.txt 中 {catalog_skipped} 个番号元数据/封面已完成，已跳过）" if catalog_skipped else ""
            return {
                "ok": False,
                "message": f"{label}目录下没有待抓取元数据的番号{skip_hint}",
            }
        if not self._clients:
            return {"ok": False, "message": "浏览器扩展未连接，请先打开 JavDB 并完成配对"}
        if not self._loop or not self._loop.is_running():
            return {"ok": False, "message": "桥接服务未就绪"}

        asyncio.run_coroutine_threadsafe(
            self._launch_video_metadata_sync(library_kind, folders),
            self._loop,
        )
        return {
            "ok": True,
            "message": f"已在后台开始{label}元数据同步（{len(folders)} 个女优文件夹）"
            + (f"（跳过目录.txt 中已完成 {catalog_skipped} 个番号）" if catalog_skipped else ""),
        }

    async def _launch_video_metadata_sync(self, library_kind: str, folders: list[dict]) -> None:
        self._video_metadata_running = True
        self._video_metadata_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._video_metadata_library_kind = library_kind
        self._video_metadata_exported_paths = set()

        label = "影片已破解" if library_kind == VIDEO_CRACKED_KEY else "影片已下载"
        progress = {
            "phase": "starting",
            "message": f"已扫描 {len(folders)} 个{label}文件夹，正在抓取 JavDB 元数据…",
            "current": 0,
            "total": len(folders),
            "library_kind": library_kind,
        }
        if self._on_event:
            self._on_event({"type": "video_metadata_sync_progress", "payload": progress})

        await self.broadcast(
            {
                "type": "video_metadata_sync_request",
                "folders": folders,
                "session_id": self._video_metadata_session_id,
                "library_kind": library_kind,
            }
        )

    def _emit_video_metadata_done(
        self,
        *,
        folder_results: list[dict],
        library_kind: str = "",
        error: str = "",
    ) -> None:
        self._video_metadata_running = False
        if not self._on_event:
            return
        success_folders = sum(1 for item in folder_results if item.get("ok"))
        self._on_event(
            {
                "type": "video_metadata_sync_done",
                "payload": {
                    "session_id": self._video_metadata_session_id,
                    "library_kind": library_kind or self._video_metadata_library_kind,
                    "success_count": success_folders,
                    "total": len(folder_results),
                    "error": error,
                    "folder_results": folder_results,
                },
            }
        )

    def _emit_pending_download_done(
        self,
        *,
        results: list[dict],
        error: str = "",
        log_paths: list[str] | None = None,
    ) -> None:
        self._pending_download_running = False
        if not self._on_event:
            return
        success_count = sum(1 for item in results if item.get("ok") and item.get("marked"))
        self._on_event(
            {
                "type": "pending_download_sync_done",
                "payload": {
                    "session_id": self._pending_download_session_id,
                    "success_count": success_count,
                    "total": len(results),
                    "error": error,
                    "log_paths": log_paths or [],
                },
            }
        )

    async def _handle_client(self, websocket: WebSocketServerProtocol) -> None:
        browser_name = "unknown"
        authenticated = False

        try:
            async for raw in websocket:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({"type": "error", "message": "invalid_json"}))
                    continue

                msg_type = message.get("type")

                if not authenticated:
                    if msg_type != "hello":
                        await websocket.send(json.dumps({"type": "error", "message": "auth_required"}))
                        continue

                    token = str(message.get("token") or "")
                    if token == get_bridge_token():
                        browser_name = await self._authenticate_client(websocket, message)
                        authenticated = True
                        continue

                    approved = await self._await_extension_auth(websocket, message)
                    if not approved:
                        await websocket.send(json.dumps({"type": "auth_rejected", "message": "denied"}))
                        await websocket.close(code=1008, reason="auth_rejected")
                        return

                    browser_name = await self._authenticate_client(websocket, message, include_token=True)
                    authenticated = True
                    continue

                if msg_type == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))
                    continue

                if msg_type == "tab_update":
                    browser_name = str(message.get("browser", browser_name))
                    url = str(message.get("url", ""))
                    browser_monitor_state.update_tab(
                        browser_name,
                        url=url,
                        title=str(message.get("title", "")),
                        tab_id=message.get("tabId"),
                        window_id=message.get("windowId"),
                    )
                    if self._on_event:
                        self._on_event({"type": "tab_update", "browser": browser_name, "payload": message})
                    await self._maybe_request_actress_sync(websocket, url)
                    continue

                if msg_type == "sticker_action":
                    action = str(message.get("action", ""))
                    code = str(message.get("code", "")).strip().upper()
                    try:
                        if action == "unmarked":
                            remove_sticker_action(ACTION_MARKED, code)
                            await websocket.send(
                                json.dumps({"type": "sticker_action_ack", "action": action, "code": code, "ok": True})
                            )
                        elif action == "unverified":
                            remove_sticker_action(ACTION_VERIFIED, code)
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "code": code,
                                        "ok": True,
                                        "serial": message.get("_serial"),
                                    }
                                )
                            )
                        elif action == "unblocked":
                            remove_sticker_action(ACTION_BLOCKED, code)
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "code": code,
                                        "ok": True,
                                        "serial": message.get("_serial"),
                                    }
                                )
                            )
                        elif action == "undownloaded":
                            remove_sticker_action(ACTION_DOWNLOADED, code)
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "code": code,
                                        "ok": True,
                                        "serial": message.get("_serial"),
                                    }
                                )
                            )
                        elif action == "block_series":
                            row = record_blocked_series(message)
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "series": row["series"],
                                        "ok": True,
                                    }
                                )
                            )
                        elif action == "unblock_series":
                            remove_blocked_series(str(message.get("series", "")))
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "series": str(message.get("series", "")),
                                        "ok": True,
                                    }
                                )
                            )
                        elif action == "block_title_keyword":
                            row = record_blocked_title_keyword(message)
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "keyword": row["keyword"],
                                        "ok": True,
                                    }
                                )
                            )
                        elif action == "unblock_title_keyword":
                            remove_blocked_title_keyword(str(message.get("keyword", "")))
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "keyword": str(message.get("keyword", "")),
                                        "ok": True,
                                    }
                                )
                            )
                        elif action == "block_actress":
                            record_blocked_actress(message)
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "javdb_id": str(message.get("javdb_id", "")),
                                        "ok": True,
                                    }
                                )
                            )
                        elif action == "unblock_actress":
                            remove_blocked_actress(str(message.get("javdb_id") or ""))
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "javdb_id": str(message.get("javdb_id", "")),
                                        "ok": True,
                                    }
                                )
                            )
                        elif action == "mediocre_actress":
                            record_mediocre_actress(message)
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "javdb_id": str(message.get("javdb_id", "")),
                                        "ok": True,
                                    }
                                )
                            )
                        elif action == "pending_download_actress":
                            record_pending_download_actress(message)
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "javdb_id": str(message.get("javdb_id", "")),
                                        "ok": True,
                                        "serial": message.get("_serial"),
                                    }
                                )
                            )
                        elif action == "magnet_saved_actress":
                            record_magnet_saved_actress(message)
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "javdb_id": str(message.get("javdb_id", "")),
                                        "ok": True,
                                        "serial": message.get("_serial"),
                                    }
                                )
                            )
                        elif action == "magnet_saved_video":
                            record_magnet_saved_video(message)
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "code": str(message.get("code", "")).strip().upper(),
                                        "ok": True,
                                        "serial": message.get("_serial"),
                                    }
                                )
                            )
                        elif action == "video_downloaded_actress":
                            record_video_downloaded_actress(message)
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "javdb_id": str(message.get("javdb_id", "")),
                                        "ok": True,
                                        "serial": message.get("_serial"),
                                    }
                                )
                            )
                        elif action == "video_downloaded_video":
                            record_video_downloaded_video(message)
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "code": str(message.get("code", "")).strip().upper(),
                                        "ok": True,
                                        "serial": message.get("_serial"),
                                    }
                                )
                            )
                        elif action == "video_cracked_actress":
                            record_video_cracked_actress(message)
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "javdb_id": str(message.get("javdb_id", "")),
                                        "ok": True,
                                        "serial": message.get("_serial"),
                                    }
                                )
                            )
                        elif action == "video_cracked_video":
                            record_video_cracked_video(message)
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "code": str(message.get("code", "")).strip().upper(),
                                        "ok": True,
                                        "serial": message.get("_serial"),
                                    }
                                )
                            )
                        elif action in (ACTION_BLOCKED, ACTION_VERIFIED, ACTION_DOWNLOADED, ACTION_MARKED):
                            record_sticker_action(action, message)
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "code": code,
                                        "ok": True,
                                        "serial": message.get("_serial"),
                                    }
                                )
                            )
                        else:
                            await websocket.send(
                                json.dumps(
                                    {
                                        "type": "sticker_action_ack",
                                        "action": action,
                                        "code": code,
                                        "ok": False,
                                        "message": "unknown_action",
                                    }
                                )
                            )
                    except ValueError as exc:
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "sticker_action_ack",
                                    "action": action,
                                    "code": code,
                                    "ok": False,
                                    "message": str(exc),
                                    "serial": message.get("_serial"),
                                }
                            )
                        )
                    continue

                if msg_type == "magnet_filter_rules_request":
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "magnet_filter_rules",
                                "rules": get_magnet_filter_payload(),
                            },
                            ensure_ascii=False,
                        )
                    )
                    continue

                if msg_type == "magnet_txt_write":
                    filename = str(message.get("filename", ""))
                    content = str(message.get("content", ""))
                    allow_empty = bool(message.get("allow_empty"))
                    try:
                        path = write_magnet_txt_file(filename, content, allow_empty=allow_empty)
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "magnet_txt_ack",
                                    "ok": True,
                                    "filename": path.name,
                                    "path": str(path),
                                }
                            )
                        )
                    except Exception as exc:
                        logger.exception("magnet_txt_write failed")
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "magnet_txt_ack",
                                    "ok": False,
                                    "message": str(exc),
                                }
                            )
                        )
                    continue

                if msg_type == "magnet_txt_batch_write":
                    actress_name = sanitize_actress_name(str(message.get("actress_name") or ""))
                    files = message.get("files") if isinstance(message.get("files"), dict) else {}
                    processed_codes = message.get("processed_codes") or []
                    if not isinstance(processed_codes, list):
                        processed_codes = []
                    try:
                        folder = resolve_actress_folder(actress_name, create=True)
                        written = write_magnet_batch_files(
                            folder,
                            files,
                            merge=True,
                            processed_codes=processed_codes,
                        )
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "magnet_txt_batch_ack",
                                    "ok": True,
                                    "folder_path": str(folder.resolve()),
                                    "files": written,
                                },
                                ensure_ascii=False,
                            )
                        )
                    except Exception as exc:
                        logger.exception("magnet_txt_batch_write failed")
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "magnet_txt_batch_ack",
                                    "ok": False,
                                    "message": str(exc),
                                },
                                ensure_ascii=False,
                            )
                        )
                    continue

                if msg_type == "actress_folder_lookup":
                    actress_name = sanitize_actress_name(str(message.get("actress_name") or ""))
                    javdb_id = str(message.get("javdb_id") or message.get("javdbId") or "").strip()
                    lookup_serial = message.get("serial")
                    try:
                        record = lookup_actress_folder_record(actress_name, javdb_id=javdb_id)
                        if record:
                            payload = {
                                "type": "actress_folder_lookup_ack",
                                "ok": True,
                                "actress_name": actress_name,
                                "found": True,
                                "folder_path": str(record.get("folder_path") or ""),
                                "folder_name": str(record.get("folder_name") or ""),
                                "library_kind": str(record.get("library_kind") or ""),
                                "source": "database",
                                "serial": lookup_serial,
                            }
                        else:
                            folder = (
                                find_actress_folder(actress_name, javdb_id=javdb_id)
                                if actress_name or javdb_id
                                else None
                            )
                            payload = {
                                "type": "actress_folder_lookup_ack",
                                "ok": True,
                                "actress_name": actress_name,
                                "found": bool(folder),
                                "folder_path": str(folder.resolve()) if folder else "",
                                "folder_name": folder.name if folder else "",
                                "library_kind": "",
                                "source": "scan" if folder else "",
                                "serial": lookup_serial,
                            }
                        await websocket.send(json.dumps(payload, ensure_ascii=False))
                    except Exception as exc:
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "actress_folder_lookup_ack",
                                    "ok": False,
                                    "message": str(exc),
                                    "serial": lookup_serial,
                                },
                                ensure_ascii=False,
                            )
                        )
                    continue

                if msg_type == "magnet_summary_read":
                    actress_name = sanitize_actress_name(str(message.get("actress_name") or ""))
                    pending_download = bool(message.get("pending_download"))
                    try:
                        payload = read_manual_subtitle_file(
                            actress_name,
                            pending_download=pending_download,
                        )
                        payload["ok"] = True
                        payload["serial"] = message.get("serial")
                        await websocket.send(
                            json.dumps(
                                {"type": "magnet_summary_ack", **payload},
                                ensure_ascii=False,
                            )
                        )
                    except Exception as exc:
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "magnet_summary_ack",
                                    "ok": False,
                                    "message": str(exc),
                                    "serial": message.get("serial"),
                                },
                                ensure_ascii=False,
                            )
                        )
                    continue

                if msg_type == "metadata_asset_write":
                    folder_path = str(message.get("folder_path") or "")
                    relative_path = str(message.get("relative_path") or "")
                    content_base64 = str(message.get("content_base64") or "")
                    result = write_metadata_asset(folder_path, relative_path, content_base64)
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "metadata_asset_ack",
                                "ok": bool(result.get("ok")),
                                "path": result.get("path") or "",
                                "message": result.get("message") or "",
                                "serial": message.get("serial"),
                            },
                            ensure_ascii=False,
                        )
                    )
                    continue

                if msg_type == "sticker_sync_request":
                    payload = get_sync_payload()
                    await websocket.send(json.dumps({"type": "sticker_sync", **payload}))
                    continue

                if msg_type == "backup_db_local":
                    from src.backup_115 import run_daily_backup_if_due

                    try:
                        result = run_daily_backup_if_due()
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "backup_db_local_ack",
                                    "ok": True,
                                    "path": result.get("local_path", ""),
                                    "status": result.get("status", ""),
                                    "serial": message.get("_serial"),
                                }
                            )
                        )
                    except Exception as exc:
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "backup_db_local_ack",
                                    "ok": False,
                                    "message": str(exc),
                                    "serial": message.get("_serial"),
                                }
                            )
                        )
                    continue

                if msg_type == "sticker_bulk_upload":
                    data = message.get("data") or {}
                    imported = import_bulk_from_extension(data) if isinstance(data, dict) else 0
                    payload = get_sync_payload()
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "sticker_bulk_ack",
                                "imported": imported,
                                **payload,
                            }
                        )
                    )
                    continue

                if msg_type == "actress_sync":
                    actresses = message.get("actresses") or []
                    if not isinstance(actresses, list):
                        actresses = []
                    synced_at = str(message.get("synced_at") or "")
                    try:
                        count = sync_collected_actresses(actresses, synced_at or None)
                        info = get_actress_sync_info()
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "actress_sync_ack",
                                    "ok": True,
                                    "count": count,
                                    "last_sync_date": info["last_sync_date"],
                                    "last_sync_at": info["last_sync_at"],
                                    "last_count": info["last_count"],
                                }
                            )
                        )
                    except Exception as exc:
                        logger.exception("actress_sync failed")
                        await websocket.send(
                            json.dumps(
                                {
                                    "type": "actress_sync_ack",
                                    "ok": False,
                                    "message": str(exc),
                                }
                            )
                        )
                    continue

                if msg_type == "actress_sync_info_request":
                    info = get_actress_sync_info()
                    await websocket.send(json.dumps({"type": "actress_sync_info", **info, "ok": True}))
                    continue

                if msg_type == "pending_download_sync_progress":
                    if self._on_event:
                        self._on_event({"type": "pending_download_sync_progress", "payload": message})
                    continue

                if msg_type == "pending_download_sync_folder_done":
                    folder_result = message.get("folder_result") or {}
                    if not isinstance(folder_result, dict):
                        folder_result = {}
                    session_id = str(message.get("session_id") or self._pending_download_session_id)
                    folder_result = finalize_pending_download_folder(folder_result, session_id=session_id)
                    key = self._folder_export_key(folder_result)
                    if key:
                        self._pending_download_exported_paths.add(key)
                    await self._reply_sync_folder_ack(
                        websocket,
                        ack_type="pending_download_sync_folder_ack",
                        folder_result=folder_result,
                    )
                    await self._emit_sync_folder_done(
                        event_type="pending_download_sync_folder_done",
                        folder_result=folder_result,
                        session_id=session_id,
                    )
                    continue

                if msg_type == "pending_download_sync_done":
                    results = message.get("results") or []
                    if not isinstance(results, list):
                        results = []
                    session_id = str(message.get("session_id") or self._pending_download_session_id)
                    results = self._catch_up_folder_exports(
                        results,
                        exported_paths=self._pending_download_exported_paths,
                        finalize_fn=finalize_pending_download_folder,
                        session_id=session_id,
                    )
                    finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    error = str(message.get("error") or "")
                    log_paths = write_pending_download_sync_logs(
                        self._pending_download_log_roots or message.get("log_roots") or [],
                        session_id=session_id,
                        started_at=self._pending_download_started_at or finished_at,
                        finished_at=finished_at,
                        scan_roots=self._pending_download_scan_roots or message.get("log_roots") or [],
                        folder_names=self._pending_download_folder_names
                        or message.get("folder_names")
                        or [],
                        results=results,
                        error=error,
                    )
                    self._pending_download_exported_paths.clear()
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "pending_download_sync_ack",
                                "ok": not error,
                                "log_paths": log_paths,
                            },
                            ensure_ascii=False,
                        )
                    )
                    self._emit_pending_download_done(results=results, error=error, log_paths=log_paths)
                    continue

                if msg_type == "magnet_saved_sync_progress":
                    if self._on_event:
                        self._on_event({"type": "magnet_saved_sync_progress", "payload": message})
                    continue

                if msg_type == "magnet_saved_sync_folder_done":
                    folder_result = message.get("folder_result") or {}
                    if not isinstance(folder_result, dict):
                        folder_result = {}
                    session_id = str(message.get("session_id") or self._magnet_saved_session_id)
                    folder_result = finalize_magnet_saved_folder(folder_result, session_id=session_id)
                    key = self._folder_export_key(folder_result)
                    if key:
                        self._magnet_saved_exported_paths.add(key)
                    await self._reply_sync_folder_ack(
                        websocket,
                        ack_type="magnet_saved_sync_folder_ack",
                        folder_result=folder_result,
                    )
                    await self._emit_sync_folder_done(
                        event_type="magnet_saved_sync_folder_done",
                        folder_result=folder_result,
                        session_id=session_id,
                    )
                    continue

                if msg_type == "magnet_saved_sync_done":
                    folder_results = message.get("folder_results") or []
                    if not isinstance(folder_results, list):
                        folder_results = []
                    finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    error = str(message.get("error") or "")
                    session_id = str(message.get("session_id") or self._magnet_saved_session_id)
                    log_roots = self._magnet_saved_log_roots or message.get("log_roots") or []
                    folder_results = self._catch_up_folder_exports(
                        folder_results,
                        exported_paths=self._magnet_saved_exported_paths,
                        finalize_fn=finalize_magnet_saved_folder,
                        session_id=session_id,
                    )
                    root_logs = write_magnet_saved_root_logs(
                        log_roots,
                        session_id=session_id,
                        started_at=self._magnet_saved_started_at or finished_at,
                        finished_at=finished_at,
                        folder_results=folder_results,
                        error=error,
                    )
                    for root in log_roots:
                        write_root_no_subtitle_txt(root, folder_results)
                    self._magnet_saved_exported_paths.clear()
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "magnet_saved_sync_ack",
                                "ok": not error,
                                "log_paths": root_logs,
                            },
                            ensure_ascii=False,
                        )
                    )
                    self._emit_magnet_saved_done(
                        folder_results=folder_results,
                        error=error,
                        log_paths=root_logs,
                    )
                    continue

                if msg_type == "video_downloaded_sync_progress":
                    if self._on_event:
                        self._on_event({"type": "video_downloaded_sync_progress", "payload": message})
                    continue

                if msg_type == "video_downloaded_sync_folder_done":
                    folder_result = message.get("folder_result") or {}
                    if not isinstance(folder_result, dict):
                        folder_result = {}
                    session_id = str(message.get("session_id") or self._video_downloaded_session_id)
                    folder_result = finalize_video_downloaded_folder(folder_result, session_id=session_id)
                    key = self._folder_export_key(folder_result)
                    if key:
                        self._video_downloaded_exported_paths.add(key)
                    await self._reply_sync_folder_ack(
                        websocket,
                        ack_type="video_downloaded_sync_folder_ack",
                        folder_result=folder_result,
                    )
                    await self._emit_sync_folder_done(
                        event_type="video_downloaded_sync_folder_done",
                        folder_result=folder_result,
                        session_id=session_id,
                    )
                    continue

                if msg_type == "video_downloaded_sync_done":
                    folder_results = message.get("folder_results") or []
                    if not isinstance(folder_results, list):
                        folder_results = []
                    finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    error = str(message.get("error") or "")
                    session_id = str(message.get("session_id") or self._video_downloaded_session_id)
                    log_roots = self._video_downloaded_log_roots or message.get("log_roots") or []
                    folder_results = self._catch_up_folder_exports(
                        folder_results,
                        exported_paths=self._video_downloaded_exported_paths,
                        finalize_fn=finalize_video_downloaded_folder,
                        session_id=session_id,
                    )
                    root_logs = write_video_downloaded_root_logs(
                        log_roots,
                        session_id=session_id,
                        started_at=self._video_downloaded_started_at or finished_at,
                        finished_at=finished_at,
                        folder_results=folder_results,
                        error=error,
                    )
                    for root in log_roots:
                        write_root_no_subtitle_txt(root, folder_results)
                    self._video_downloaded_exported_paths.clear()
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "video_downloaded_sync_ack",
                                "ok": not error,
                                "log_paths": root_logs,
                            },
                            ensure_ascii=False,
                        )
                    )
                    self._emit_video_downloaded_done(
                        folder_results=folder_results,
                        error=error,
                        log_paths=root_logs,
                    )
                    continue

                if msg_type == "video_cracked_sync_progress":
                    if self._on_event:
                        self._on_event({"type": "video_cracked_sync_progress", "payload": message})
                    continue

                if msg_type == "video_cracked_sync_folder_done":
                    folder_result = message.get("folder_result") or {}
                    if not isinstance(folder_result, dict):
                        folder_result = {}
                    session_id = str(message.get("session_id") or self._video_cracked_session_id)
                    folder_result = finalize_video_cracked_folder(folder_result, session_id=session_id)
                    key = self._folder_export_key(folder_result)
                    if key:
                        self._video_cracked_exported_paths.add(key)
                    await self._reply_sync_folder_ack(
                        websocket,
                        ack_type="video_cracked_sync_folder_ack",
                        folder_result=folder_result,
                    )
                    await self._emit_sync_folder_done(
                        event_type="video_cracked_sync_folder_done",
                        folder_result=folder_result,
                        session_id=session_id,
                    )
                    continue

                if msg_type == "video_cracked_sync_done":
                    folder_results = message.get("folder_results") or []
                    if not isinstance(folder_results, list):
                        folder_results = []
                    finished_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    error = str(message.get("error") or "")
                    session_id = str(message.get("session_id") or self._video_cracked_session_id)
                    log_roots = self._video_cracked_log_roots or message.get("log_roots") or []
                    folder_results = self._catch_up_folder_exports(
                        folder_results,
                        exported_paths=self._video_cracked_exported_paths,
                        finalize_fn=finalize_video_cracked_folder,
                        session_id=session_id,
                    )
                    root_logs = write_video_cracked_root_logs(
                        log_roots,
                        session_id=session_id,
                        started_at=self._video_cracked_started_at or finished_at,
                        finished_at=finished_at,
                        folder_results=folder_results,
                        error=error,
                    )
                    for root in log_roots:
                        write_root_no_subtitle_txt(root, folder_results)
                    self._video_cracked_exported_paths.clear()
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "video_cracked_sync_ack",
                                "ok": not error,
                                "log_paths": root_logs,
                            },
                            ensure_ascii=False,
                        )
                    )
                    self._emit_video_cracked_done(
                        folder_results=folder_results,
                        error=error,
                        log_paths=root_logs,
                    )
                    continue

                if msg_type == "video_metadata_sync_progress":
                    if self._on_event:
                        self._on_event({"type": "video_metadata_sync_progress", "payload": message})
                    continue

                if msg_type == "video_metadata_folder_done":
                    folder_result = message.get("folder_result") or {}
                    if not isinstance(folder_result, dict):
                        folder_result = {}
                    library_kind = str(
                        message.get("library_kind") or self._video_metadata_library_kind or VIDEO_DOWNLOADED_KEY
                    )
                    folder_path = str(folder_result.get("folder_path") or "").strip()
                    current = int(message.get("current") or 0)
                    total = int(message.get("total") or 0)
                    folder_result = finalize_metadata_folder(
                        folder_result,
                        library_kind=library_kind,
                        download_media=False,
                    )
                    key = self._folder_export_key(folder_result)
                    if key:
                        self._video_metadata_exported_paths.add(key)
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "video_metadata_folder_ack",
                                "ok": True,
                                "folder_path": folder_path,
                                "folder_result": folder_result,
                                "metadata_export": folder_result.get("metadata_export") or {},
                            },
                            ensure_ascii=False,
                        )
                    )
                    await self._emit_sync_folder_done(
                        event_type="video_metadata_folder_done",
                        library_kind=library_kind,
                        folder_result=folder_result,
                        session_id=str(message.get("session_id") or self._video_metadata_session_id),
                        current=current,
                        total=total,
                    )
                    asyncio.create_task(self._download_metadata_folder_assets(dict(folder_result), library_kind))
                    continue

                if msg_type == "video_metadata_sync_done":
                    folder_results = message.get("folder_results") or []
                    if not isinstance(folder_results, list):
                        folder_results = []
                    library_kind = str(
                        message.get("library_kind") or self._video_metadata_library_kind or VIDEO_DOWNLOADED_KEY
                    )
                    error = str(message.get("error") or "")

                    def _finalize_metadata_item(item: dict) -> dict:
                        return finalize_metadata_folder(item, library_kind=library_kind)

                    folder_results = self._catch_up_folder_exports(
                        folder_results,
                        exported_paths=self._video_metadata_exported_paths,
                        finalize_fn=_finalize_metadata_item,
                        session_id=str(message.get("session_id") or self._video_metadata_session_id),
                    )
                    self._video_metadata_exported_paths.clear()
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "video_metadata_sync_ack",
                                "ok": not error,
                                "library_kind": library_kind,
                            },
                            ensure_ascii=False,
                        )
                    )
                    self._emit_video_metadata_done(
                        folder_results=folder_results,
                        library_kind=library_kind,
                        error=error,
                    )
                    continue

                if msg_type == "loose_video_sync_progress":
                    if self._on_event:
                        self._on_event({"type": "loose_video_sync_progress", "payload": message})
                    continue

                if msg_type == "loose_video_sync_folder_done":
                    root_result = message.get("root_result") or {}
                    if not isinstance(root_result, dict):
                        root_result = {}
                    session_id = str(message.get("session_id") or self._loose_video_session_id)
                    if not root_result.get("folder_path"):
                        root_result["folder_path"] = str(root_result.get("root_path") or "")
                    root_result = finalize_loose_root(root_result, session_id=session_id)
                    key = self._folder_export_key(root_result)
                    if key:
                        self._loose_video_exported_paths.add(key)
                    await self._reply_sync_folder_ack(
                        websocket,
                        ack_type="loose_video_sync_folder_ack",
                        folder_result=root_result,
                    )
                    await self._emit_sync_folder_done(
                        event_type="loose_video_sync_folder_done",
                        folder_result=root_result,
                        session_id=session_id,
                        current=int(message.get("current") or 0),
                        total=int(message.get("total") or 0),
                    )
                    continue

                if msg_type == "loose_video_sync_done":
                    root_results = message.get("root_results") or []
                    if not isinstance(root_results, list):
                        root_results = []
                    error = str(message.get("error") or "")

                    def _finalize_loose_item(item: dict, *, session_id: str) -> dict:
                        if not item.get("folder_path"):
                            item["folder_path"] = str(item.get("root_path") or "")
                        return finalize_loose_root(item, session_id=session_id)

                    root_results = self._catch_up_folder_exports(
                        root_results,
                        exported_paths=self._loose_video_exported_paths,
                        finalize_fn=_finalize_loose_item,
                        session_id=str(message.get("session_id") or self._loose_video_session_id),
                    )
                    self._loose_video_exported_paths.clear()
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "loose_video_sync_ack",
                                "ok": not error,
                            },
                            ensure_ascii=False,
                        )
                    )
                    self._emit_loose_video_done(root_results=root_results, error=error)
                    continue

                await websocket.send(json.dumps({"type": "error", "message": f"unknown_type:{msg_type}"}))

        except websockets.ConnectionClosed:
            pass
        finally:
            self._clients.discard(websocket)
            if authenticated:
                browser_monitor_state.set_connected(browser_name, connected=False)
                if self._on_event:
                    self._on_event({"type": "disconnected", "browser": browser_name})

    async def broadcast(self, message: dict) -> None:
        if not self._clients:
            return
        payload = json.dumps(message)
        await asyncio.gather(
            *[client.send(payload) for client in list(self._clients)],
            return_exceptions=True,
        )

    def broadcast_threadsafe(self, message: dict) -> None:
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self.broadcast(message), self._loop)


bridge_server = BridgeServer()
