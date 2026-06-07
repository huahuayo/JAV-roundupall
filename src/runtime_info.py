"""Describe how the desktop app is being launched."""

from __future__ import annotations

import sys
from pathlib import Path


def describe_runtime() -> str:
    if getattr(sys, "frozen", False):
        exe = Path(sys.executable)
        return f"打包版 · {exe.name} · {exe.parent}"
    root = Path(__file__).resolve().parents[1]
    return f"源码版 · python main.py · {root}"
