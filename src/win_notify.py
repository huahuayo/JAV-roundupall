"""Windows completion notifications for desktop tasks."""

from __future__ import annotations

import sys
import threading


def notify(title: str, message: str, *, success: bool = True) -> None:
    if sys.platform != "win32":
        return
    text = str(message or "").strip() or "任务已完成"
    heading = str(title or "").strip() or "JAV一网打尽"
    flags = 0x40 if success else 0x30

    def _show() -> None:
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(0, text[:2048], heading[:128], flags)
        except Exception:
            pass

    threading.Thread(target=_show, daemon=True).start()
