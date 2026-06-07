"""Load and persist bridge settings for browser extension pairing."""

from __future__ import annotations

import json
import secrets

from src.config import APP_DIR, BRIDGE_DEFAULT_PORT, CONFIG_PATH


def _read_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _write_config(data: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def get_bridge_settings() -> dict[str, str | int]:
    data = _read_config()
    bridge = data.get("bridge", {})
    token = bridge.get("token")
    if not token:
        token = secrets.token_hex(16)
        bridge["token"] = token
        data["bridge"] = bridge
        _write_config(data)

    port = bridge.get("port", BRIDGE_DEFAULT_PORT)
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = BRIDGE_DEFAULT_PORT

    return {"port": port, "token": str(token)}


def get_bridge_token() -> str:
    return str(get_bridge_settings()["token"])


def get_bridge_port() -> int:
    return int(get_bridge_settings()["port"])
