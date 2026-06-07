"""Regenerate app icon (.ico) and extension PNG icons from packaging/app-icon.png."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "app-icon.png"
ICO = ROOT / "app-icon.ico"
EXT_ICONS = ROOT.parent / "extension" / "icons"


def build_ico() -> None:
    if not SRC.is_file():
        raise SystemExit(f"Missing source icon: {SRC}")
    img = Image.open(SRC).convert("RGBA")
    sizes = [256, 128, 64, 48, 32, 16]
    icons = [img.resize((size, size), Image.Resampling.LANCZOS) for size in sizes]
    icons[0].save(
        ICO,
        format="ICO",
        sizes=[(size, size) for size in sizes],
        append_images=icons[1:],
    )
    print(f"Wrote {ICO} ({ICO.stat().st_size} bytes)")


def build_extension_icons() -> None:
    if not SRC.is_file():
        raise SystemExit(f"Missing source icon: {SRC}")
    img = Image.open(SRC).convert("RGBA")
    EXT_ICONS.mkdir(parents=True, exist_ok=True)
    for size in (16, 48, 128):
        out = EXT_ICONS / f"icon{size}.png"
        img.resize((size, size), Image.Resampling.LANCZOS).save(out, format="PNG")
        print(f"Wrote {out}")


def main() -> None:
    build_ico()
    build_extension_icons()


if __name__ == "__main__":
    main()
