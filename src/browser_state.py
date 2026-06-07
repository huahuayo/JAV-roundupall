"""In-memory browser tab state from extension connections."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class BrowserTabInfo:
    browser: str
    url: str
    title: str
    tab_id: int | None = None
    window_id: int | None = None
    updated_at: float = field(default_factory=time.time)


@dataclass
class BrowserConnectionInfo:
    browser: str
    connected: bool = False
    extension_version: str = ""
    last_seen_at: float = 0.0
    current_tab: BrowserTabInfo | None = None


class BrowserMonitorState:
    """Tracks one connection and latest tab per browser type."""

    SUPPORTED_BROWSERS = ("edge", "115")

    def __init__(self) -> None:
        self._connections: dict[str, BrowserConnectionInfo] = {
            name: BrowserConnectionInfo(browser=name) for name in self.SUPPORTED_BROWSERS
        }
        self._active_browser: str | None = None
        self._listeners: list = []

    def add_listener(self, callback) -> None:
        self._listeners.append(callback)

    def _notify(self) -> None:
        for callback in self._listeners:
            callback()

    def set_connected(self, browser: str, *, connected: bool, extension_version: str = "") -> None:
        browser = self._normalize_browser(browser)
        info = self._connections[browser]
        info.connected = connected
        info.extension_version = extension_version
        info.last_seen_at = time.time()
        if not connected and self._active_browser == browser:
            self._active_browser = self._pick_active_browser()
        self._notify()

    def update_tab(
        self,
        browser: str,
        *,
        url: str,
        title: str,
        tab_id: int | None = None,
        window_id: int | None = None,
    ) -> None:
        browser = self._normalize_browser(browser)
        info = self._connections[browser]
        info.connected = True
        info.last_seen_at = time.time()
        info.current_tab = BrowserTabInfo(
            browser=browser,
            url=url,
            title=title,
            tab_id=tab_id,
            window_id=window_id,
        )
        self._active_browser = browser
        self._notify()

    def get_connection(self, browser: str) -> BrowserConnectionInfo:
        return self._connections[self._normalize_browser(browser)]

    def get_active_tab(self) -> BrowserTabInfo | None:
        if self._active_browser:
            tab = self._connections[self._active_browser].current_tab
            if tab:
                return tab
        return self._pick_latest_tab()

    def _pick_active_browser(self) -> str | None:
        best_name: str | None = None
        best_time = -1.0
        for name, info in self._connections.items():
            if info.current_tab and info.last_seen_at > best_time:
                best_time = info.last_seen_at
                best_name = name
        return best_name

    def _pick_latest_tab(self) -> BrowserTabInfo | None:
        best: BrowserTabInfo | None = None
        for info in self._connections.values():
            tab = info.current_tab
            if tab and (best is None or tab.updated_at > best.updated_at):
                best = tab
        return best

    @staticmethod
    def _normalize_browser(browser: str) -> str:
        value = (browser or "").strip().lower()
        if value in {"115", "115browser"}:
            return "115"
        if value in {"edge", "msedge", "microsoft-edge"}:
            return "edge"
        return value or "edge"


browser_monitor_state = BrowserMonitorState()
