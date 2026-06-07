"""Remove invalid or leaked test paths from local user config on startup."""

from __future__ import annotations

import logging
from pathlib import Path

from src.bridge_settings import _read_config, _write_config

logger = logging.getLogger(__name__)


def _looks_like_test_or_temp_path(raw: str) -> bool:
    text = str(raw or "").strip().lower().replace("/", "\\")
    if not text:
        return False
    markers = (
        "\\temp\\",
        "\\tmp\\",
        "pytest",
        "pytest-of-",
        "\\appdata\\local\\temp\\",
    )
    return any(marker in text for marker in markers)


def sanitize_user_config_on_startup() -> list[str]:
    """Drop unsafe paths from config.json. Returns human-readable notices."""
    data = _read_config()
    notices: list[str] = []
    changed = False

    raw_db = str(data.get("state_db_path") or "").strip()
    if raw_db and _looks_like_test_or_temp_path(raw_db):
        data.pop("state_db_path", None)
        changed = True
        notices.append("已清除无效的操作数据库路径（测试目录），已恢复默认位置。")

    magnet = data.get("magnet_txt")
    if isinstance(magnet, dict):
        output_dir = str(magnet.get("output_dir") or "").strip()
        if output_dir and _looks_like_test_or_temp_path(output_dir):
            magnet.pop("output_dir", None)
            changed = True
            notices.append("已清除无效的 TXT 输出目录设置。")

    library = data.get("library_locations")
    if isinstance(library, dict):
        for key, paths in list(library.items()):
            if not isinstance(paths, list):
                continue
            cleaned = [p for p in paths if not _looks_like_test_or_temp_path(str(p))]
            if cleaned != paths:
                if cleaned:
                    library[key] = cleaned
                else:
                    library.pop(key, None)
                changed = True
                notices.append(f"已清除库路径中的测试/临时目录项（{key}）。")

    if changed:
        _write_config(data)
        logger.info("Sanitized user config: %s", "; ".join(notices))
    return notices


def reset_user_path_settings() -> None:
    """Clear saved library/txt/db paths from config (local settings only)."""
    data = _read_config()
    changed = False
    if data.pop("state_db_path", None) is not None:
        changed = True
    magnet = data.get("magnet_txt")
    if isinstance(magnet, dict) and magnet.pop("output_dir", None) is not None:
        changed = True
    if data.pop("library_locations", None) is not None:
        changed = True
    if changed:
        _write_config(data)
        logger.info("Reset user path settings in config.json")
