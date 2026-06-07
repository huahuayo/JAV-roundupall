"""Build the frozen desktop executable with a Unicode product name."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import APP_NAME


def main() -> None:
    icon = ROOT / "packaging" / "app-icon.ico"
    if not icon.is_file():
        raise SystemExit("Missing packaging/app-icon.ico — run packaging/build_app_icon.py first")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--name",
        APP_NAME,
        "--windowed",
        "--onefile",
        "--icon",
        str(icon),
        "--add-data",
        f"{icon}{';.'}",
        "--collect-all",
        "customtkinter",
        "--hidden-import",
        "websockets",
        "--hidden-import",
        "websockets.legacy",
        "--hidden-import",
        "websockets.legacy.server",
        str(ROOT / "main.py"),
    ]
    subprocess.run(cmd, cwd=ROOT, check=True)
    exe = ROOT / "dist" / f"{APP_NAME}.exe"
    if not exe.is_file():
        raise SystemExit(f"Build failed: {exe} not found")
    print(f"Built {exe}")


if __name__ == "__main__":
    main()
