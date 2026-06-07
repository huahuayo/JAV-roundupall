"""Read/write selected fields in per-video metadata txt files."""

from __future__ import annotations

from pathlib import Path

from src.library_index import split_tags


def update_metadata_categories(metadata_path: str, categories: list[str]) -> bool:
    path = Path(str(metadata_path or ""))
    if not path.is_file():
        return False
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False

    value = "、".join(split_tags("、".join(categories)))
    replaced = False
    out: list[str] = []
    for line in lines:
        text = line.strip()
        if text.startswith("类别:"):
            out.append(f"类别: {value or '-'}")
            replaced = True
        else:
            out.append(line)
    if not replaced:
        out.append(f"类别: {value or '-'}")
    try:
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    except OSError:
        return False
    return True
