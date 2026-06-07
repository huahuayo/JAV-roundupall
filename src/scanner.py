"""Scan library folders for video files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.config import VIDEO_EXTENSIONS
from src.parser import parse_video_metadata


@dataclass
class ScannedVideo:
    path: str
    filename: str
    code: str | None
    title: str | None
    size_bytes: int
    folder: str


def scan_paths(roots: list[str], progress_cb=None) -> list[ScannedVideo]:
    """Walk roots and collect video files."""
    results: list[ScannedVideo] = []
    valid_roots = [Path(r) for r in roots if r and Path(r).is_dir()]

    for root in valid_roots:
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() not in VIDEO_EXTENSIONS:
                continue

            meta = parse_video_metadata(path)
            results.append(
                ScannedVideo(
                    path=str(path.resolve()),
                    filename=path.name,
                    code=meta["code"],
                    title=meta["title"],
                    size_bytes=path.stat().st_size,
                    folder=str(path.parent),
                )
            )

            if progress_cb:
                progress_cb(len(results))

    results.sort(key=lambda v: (v.code or "ZZZ", v.filename.lower()))
    return results
