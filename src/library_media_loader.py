"""Load library folder tree and per-video media/metadata for the browser UI."""

from __future__ import annotations

import re
import webbrowser
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.library_location_settings import load_library_locations
from src.loose_video_scanner import LOOSE_PENDING_KEY, scan_loose_video_roots
from src.magnet_saved_scanner import MAGNET_SAVED_KEY, scan_magnet_saved_folders
from src.parser import normalize_code
from src.pending_download_scanner import PENDING_DOWNLOAD_KEY, scan_pending_download_folders
from src.sync_folder_rename import strip_sync_status_prefix
from src.video_cracked_scanner import VIDEO_CRACKED_KEY, scan_video_cracked_folders
from src.video_downloaded_scanner import VIDEO_DOWNLOADED_KEY, scan_video_downloaded_folders
from src.video_metadata_store import COVERS_DIRNAME, METADATA_DIRNAME, sanitize_filename

LIBRARY_CATEGORIES: tuple[tuple[str, str], ...] = (
    (PENDING_DOWNLOAD_KEY, "待下载"),
    (MAGNET_SAVED_KEY, "磁链已保存"),
    (VIDEO_DOWNLOADED_KEY, "已下载"),
    (VIDEO_CRACKED_KEY, "已破解"),
    (LOOSE_PENDING_KEY, "散片"),
)


@dataclass
class LibraryVideoNode:
    code: str
    label: str
    video_path: str = ""
    source_file: str = ""
    folder_path: str = ""


@dataclass
class LibraryActressNode:
    name: str
    folder_path: str
    folder_name: str
    videos: list[LibraryVideoNode] = field(default_factory=list)


@dataclass
class LibraryCategoryNode:
    key: str
    label: str
    actresses: list[LibraryActressNode] = field(default_factory=list)
    loose_videos: list[LibraryVideoNode] = field(default_factory=list)


@dataclass
class VideoDetailBundle:
    code: str
    folder_path: str
    video_path: str
    actress_name: str
    metadata: dict[str, str]
    metadata_path: str
    cover_path: str
    preview_paths: list[str]
    detail_url: str


def _display_actress_name(folder_name: str, actress_match_name: str = "") -> str:
    if actress_match_name:
        return str(actress_match_name).strip()
    base = strip_sync_status_prefix(str(folder_name or ""))
    base = re.sub(r"\s+\d+$", "", base).strip()
    return base or str(folder_name or "").strip() or "未知女优"


def _video_label(code: str, item: dict[str, Any]) -> str:
    source = str(item.get("source_file") or "").strip()
    if source:
        return source
    source_path = str(item.get("source_path") or "").strip()
    if source_path:
        return Path(source_path).name
    return code


def build_library_tree(locations: dict[str, list[str]] | None = None) -> list[LibraryCategoryNode]:
    locs = locations if locations is not None else load_library_locations()
    tree: list[LibraryCategoryNode] = []

    pending_roots = locs.get(PENDING_DOWNLOAD_KEY, [])
    pending_folders, _ = scan_pending_download_folders(pending_roots if pending_roots else None)
    pending_actresses = [
        LibraryActressNode(
            name=_display_actress_name(
                str(item.get("folder_name") or ""),
                str(item.get("actress_match_name") or ""),
            ),
            folder_path=str(item.get("folder_path") or ""),
            folder_name=str(item.get("folder_name") or ""),
            videos=[],
        )
        for item in pending_folders
    ]
    tree.append(LibraryCategoryNode(PENDING_DOWNLOAD_KEY, "待下载", actresses=pending_actresses))

    def scan_cat(key: str, scan_fn) -> list[LibraryActressNode]:
        roots = locs.get(key, [])
        if not roots:
            return []
        folders, _valid = scan_fn(roots)
        nodes: list[LibraryActressNode] = []
        for folder in folders:
            actress_name = _display_actress_name(
                str(folder.get("folder_name") or ""),
                str(folder.get("actress_match_name") or ""),
            )
            videos: list[LibraryVideoNode] = []
            for item in folder.get("codes") or []:
                if not isinstance(item, dict):
                    continue
                code = normalize_code(str(item.get("code") or ""))
                if not code:
                    continue
                videos.append(
                    LibraryVideoNode(
                        code=code,
                        label=_video_label(code, item),
                        video_path=str(item.get("source_path") or ""),
                        source_file=str(item.get("source_file") or ""),
                        folder_path=str(folder.get("folder_path") or ""),
                    )
                )
            nodes.append(
                LibraryActressNode(
                    name=actress_name,
                    folder_path=str(folder.get("folder_path") or ""),
                    folder_name=str(folder.get("folder_name") or ""),
                    videos=videos,
                )
            )
        return nodes

    tree.append(
        LibraryCategoryNode(
            MAGNET_SAVED_KEY,
            "磁链已保存",
            actresses=scan_cat(MAGNET_SAVED_KEY, scan_magnet_saved_folders),
        )
    )
    tree.append(
        LibraryCategoryNode(
            VIDEO_DOWNLOADED_KEY,
            "已下载",
            actresses=scan_cat(VIDEO_DOWNLOADED_KEY, scan_video_downloaded_folders),
        )
    )
    tree.append(
        LibraryCategoryNode(
            VIDEO_CRACKED_KEY,
            "已破解",
            actresses=scan_cat(VIDEO_CRACKED_KEY, scan_video_cracked_folders),
        )
    )

    loose_roots = locs.get(LOOSE_PENDING_KEY, [])
    loose_records, _ = scan_loose_video_roots(loose_roots if loose_roots else None)
    loose_videos: list[LibraryVideoNode] = []
    for record in loose_records:
        root_path = str(record.get("root_path") or "")
        for item in record.get("items") or []:
            if not isinstance(item, dict):
                continue
            code = normalize_code(str(item.get("code") or ""))
            if not code:
                continue
            loose_videos.append(
                LibraryVideoNode(
                    code=code,
                    label=_video_label(code, item),
                    video_path=str(item.get("source_path") or ""),
                    source_file=str(item.get("source_file") or ""),
                    folder_path=root_path,
                )
            )
    tree.append(LibraryCategoryNode(LOOSE_PENDING_KEY, "散片", loose_videos=loose_videos))

    return tree


def _find_metadata_file(folder: Path, code: str) -> Path | None:
    meta_root = folder / METADATA_DIRNAME
    if not meta_root.is_dir():
        return None
    target = normalize_code(code)
    for path in sorted(meta_root.glob("*.txt")):
        if normalize_code(path.stem.split(" ", 1)[0]) == target:
            return path
        if path.stem.upper().startswith(target):
            return path
    return None


def _parse_metadata_txt(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return data
    for line in lines:
        text = line.strip()
        if not text or text.startswith("#") or ":" not in text:
            continue
        key, value = text.split(":", 1)
        data[key.strip()] = value.strip()
    return data


def _cover_and_previews(folder: Path, code: str) -> tuple[str, list[str]]:
    code_dir = folder / COVERS_DIRNAME / sanitize_filename(normalize_code(code))
    cover_path = ""
    previews: list[str] = []
    if not code_dir.is_dir():
        return cover_path, previews
    for path in sorted(code_dir.iterdir()):
        if not path.is_file():
            continue
        lower = path.name.lower()
        if lower.startswith("cover."):
            cover_path = str(path)
        elif len(path.stem) >= 2 and path.stem[:2].isdigit():
            previews.append(str(path))
    return cover_path, previews


def load_video_detail(
    *,
    folder_path: str,
    code: str,
    video_path: str = "",
    actress_name: str = "",
) -> VideoDetailBundle:
    folder = Path(folder_path)
    normalized = normalize_code(code)
    metadata_path = _find_metadata_file(folder, normalized)
    metadata = _parse_metadata_txt(metadata_path) if metadata_path else {}
    cover_path, preview_paths = _cover_and_previews(folder, normalized)

    resolved_video = str(video_path or metadata.get("本地文件") or "").strip()
    if resolved_video and not Path(resolved_video).is_file():
        candidate = folder / resolved_video
        if candidate.is_file():
            resolved_video = str(candidate)

    detail_url = str(metadata.get("详情页") or metadata.get("JavBus") or "").strip()
    actress = actress_name or str(metadata.get("女优") or "").split("、")[0].strip()

    return VideoDetailBundle(
        code=normalized,
        folder_path=str(folder),
        video_path=resolved_video,
        actress_name=actress,
        metadata=metadata,
        metadata_path=str(metadata_path) if metadata_path else "",
        cover_path=cover_path,
        preview_paths=preview_paths,
        detail_url=detail_url,
    )


def open_detail_url(url: str) -> bool:
    text = str(url or "").strip()
    if text.startswith("http"):
        webbrowser.open(text)
        return True
    return False
