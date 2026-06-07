"""Daily backup of the unified state database to 115 WebDAV (scaffold).

Wire credentials in desktop settings, then schedule ``run_daily_backup_if_due()``
from the app main loop or a background timer once 115 WebDAV is configured.
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from src.config import get_project_root
from src.state_db import get_state_db_path

logger = logging.getLogger(__name__)

BACKUP_META_KEY = "last_115_db_backup_date"


def get_backup_settings() -> dict[str, str]:
    """Return WebDAV settings when implemented in the desktop UI."""
    return {
        "webdav_url": "",
        "webdav_user": "",
        "webdav_password": "",
        "remote_dir": "/JAV-Manager/backups",
    }


def is_backup_configured(settings: dict[str, str] | None = None) -> bool:
    cfg = settings or get_backup_settings()
    return bool(str(cfg.get("webdav_url") or "").strip() and str(cfg.get("webdav_user") or "").strip())


def local_backup_copy() -> Path:
    """Create a timestamped copy beside the project root for manual recovery."""
    src = get_state_db_path()
    if not src.is_file():
        raise FileNotFoundError(f"state db not found: {src}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = Path(get_project_root()) / f"jav_manager_state_backup_{stamp}.db"
    shutil.copy2(src, dest)
    logger.info("Created local DB backup: %s", dest)
    return dest


def upload_to_115_webdav(local_path: Path, settings: dict[str, str] | None = None) -> None:
    """Upload ``local_path`` to 115 WebDAV. Not implemented until credentials are wired."""
    cfg = settings or get_backup_settings()
    if not is_backup_configured(cfg):
        raise RuntimeError("115 WebDAV is not configured")

    raise NotImplementedError(
        "115 WebDAV upload will be implemented after desktop settings store credentials"
    )


def run_daily_backup_if_due(last_backup_date: str | None = None) -> dict[str, str]:
    """Run one backup per calendar day when WebDAV is configured."""
    today = datetime.now().strftime("%Y-%m-%d")
    if last_backup_date == today:
        return {"ok": True, "skipped": "already_backed_up_today", "date": today}

    settings = get_backup_settings()
    local_path = local_backup_copy()

    if is_backup_configured(settings):
        upload_to_115_webdav(local_path, settings)
        status = "uploaded"
    else:
        status = "local_only"
        logger.info("115 WebDAV not configured; kept local backup only: %s", local_path)

    return {
        "ok": True,
        "date": today,
        "status": status,
        "local_path": str(local_path),
    }
