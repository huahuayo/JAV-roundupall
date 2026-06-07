"""Write per-title magnet link txt files next to the desktop executable."""

from __future__ import annotations

import logging
import re
from pathlib import Path

from src.magnet_txt_settings import get_magnet_txt_output_dir

logger = logging.getLogger(__name__)

_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_magnet_txt_filename(filename: str) -> str:
    name = str(filename or "").strip()
    if not name:
        raise ValueError("empty_filename")
    if not name.lower().endswith(".txt"):
        name = f"{name}.txt"
    cleaned = _INVALID_FILENAME_CHARS.sub("", name)
    cleaned = cleaned.strip().strip(".")
    if not cleaned:
        raise ValueError("invalid_filename")
    return cleaned


def write_magnet_txt_file(filename: str, content: str, *, allow_empty: bool = False) -> Path:
    safe_name = sanitize_magnet_txt_filename(filename)
    magnet = str(content or "").strip()
    if not magnet.startswith("magnet:?"):
        if allow_empty and not magnet:
            txt_dir = get_magnet_txt_output_dir()
            txt_dir.mkdir(parents=True, exist_ok=True)
            path = txt_dir / safe_name
            path.write_text("", encoding="utf-8")
            logger.info("Wrote empty magnet txt marker: %s", path)
            return path
        raise ValueError("invalid_magnet")

    txt_dir = get_magnet_txt_output_dir()
    txt_dir.mkdir(parents=True, exist_ok=True)
    path = txt_dir / safe_name
    path.write_text(f"{magnet}\n", encoding="utf-8")
    logger.info("Wrote magnet txt: %s", path)
    return path
