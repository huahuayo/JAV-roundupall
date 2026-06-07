"""Settings for magnet link TXT output directory."""

from __future__ import annotations

from pathlib import Path

from src.config import APP_DIR
from src.bridge_settings import _read_config, _write_config


def get_magnet_txt_output_dir() -> Path:
    raw = str(_read_config().get("magnet_txt", {}).get("output_dir", "")).strip()
    if raw:
        path = Path(raw)
        lowered = str(path).lower().replace("/", "\\")
        if "pytest" not in lowered and path.is_dir():
            return path
    fallback = APP_DIR / "magnet_txt"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def set_magnet_txt_output_dir(directory: str) -> Path:
    folder = Path(str(directory or "").strip())
    if not folder.is_dir():
        raise ValueError("directory_not_found")
    data = _read_config()
    block = data.setdefault("magnet_txt", {})
    block["output_dir"] = str(folder.resolve())
    _write_config(data)
    return folder.resolve()


def get_magnet_txt_settings_payload() -> dict[str, str]:
    path = get_magnet_txt_output_dir()
    return {"output_dir": str(path)}
