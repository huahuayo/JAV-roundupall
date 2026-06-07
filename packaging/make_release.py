"""Build frozen executable and assemble the portable release folder + zip."""

from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import APP_NAME, APP_VERSION  # noqa: E402


def build_icons() -> None:
    subprocess.run([sys.executable, str(ROOT / "packaging" / "build_app_icon.py")], cwd=ROOT, check=True)


def build_exe() -> Path:
    subprocess.run([sys.executable, str(ROOT / "packaging" / "build_exe.py")], cwd=ROOT, check=True)
    exe = ROOT / "dist" / f"{APP_NAME}.exe"
    if not exe.is_file():
        raise SystemExit(f"Missing built executable: {exe}")
    return exe


def release_dir() -> Path:
    return ROOT / "release" / f"{APP_NAME}-{APP_VERSION}-win64"


def assemble_release(exe: Path) -> Path:
    stage = release_dir()
    if stage.parent.exists():
        shutil.rmtree(stage.parent)
    stage.mkdir(parents=True, exist_ok=True)

    shutil.copy2(exe, stage / exe.name)
    shutil.copytree(ROOT / "extension", stage / "extension")
    shutil.copy2(ROOT / "packaging" / "USER_GUIDE.txt", stage / "USER_GUIDE.txt")
    shutil.copy2(ROOT / "packaging" / "Start.bat", stage / "Start.bat")
    return stage


def verify_release(stage: Path) -> None:
    subprocess.run(
        [sys.executable, str(ROOT / "packaging" / "verify_release.py"), str(stage)],
        cwd=ROOT,
        check=True,
    )


def create_zip(stage: Path) -> Path:
    zip_path = stage.parent / f"{stage.name}.zip"
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in stage.rglob("*"):
            zf.write(path, path.relative_to(stage.parent))
    return zip_path


def main() -> None:
    print(f"Building {APP_NAME} v{APP_VERSION}")
    build_icons()
    exe = build_exe()
    stage = assemble_release(exe)
    verify_release(stage)
    zip_path = create_zip(stage)
    print(f"Release folder: {stage}")
    print(f"Release zip:    {zip_path} ({zip_path.stat().st_size // (1024 * 1024)} MB)")


if __name__ == "__main__":
    main()
