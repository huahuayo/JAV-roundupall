"""Index library tree videos with parsed metadata for browse/filter UI."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from src.library_media_loader import build_library_tree, load_video_detail
from src.library_location_settings import load_library_locations

_SPLIT_RE = re.compile(r"[,，、/|]+")


@dataclass
class IndexedVideo:
    code: str
    title: str
    folder_path: str
    video_path: str
    actress_name: str
    actress_names: list[str]
    categories: list[str]
    category_key: str
    metadata_path: str
    cover_path: str
    detail_url: str


@dataclass
class IndexedActress:
    name: str
    folder_path: str
    avatar_path: str
    video_count: int
    videos: list[IndexedVideo] = field(default_factory=list)


def split_tags(text: str) -> list[str]:
    parts = [p.strip() for p in _SPLIT_RE.split(str(text or "")) if p.strip()]
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        key = part.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(part)
    return out


def _pick_avatar(folder_path: str, videos: list[IndexedVideo]) -> str:
    for video in videos:
        if video.cover_path and Path(video.cover_path).is_file():
            return video.cover_path
    folder = Path(folder_path)
    if folder.is_dir():
        for pattern in ("avatar.*", "头像.*", "profile.*", "cover.jpg", "cover.png", "cover.webp"):
            for path in sorted(folder.glob(pattern)):
                if path.is_file():
                    return str(path)
    covers = folder / "封面"
    if covers.is_dir():
        for path in sorted(covers.rglob("cover.*")):
            if path.is_file():
                return str(path)
    return ""


def _to_indexed_video(
    *,
    code: str,
    folder_path: str,
    video_path: str,
    actress_name: str,
    category_key: str,
    label: str,
) -> IndexedVideo:
    detail = load_video_detail(
        folder_path=folder_path,
        code=code,
        video_path=video_path,
        actress_name=actress_name,
    )
    actress_raw = str(detail.metadata.get("女优") or detail.actress_name or actress_name or "")
    actress_names = split_tags(actress_raw) or ([actress_name] if actress_name else [])
    categories = split_tags(str(detail.metadata.get("类别") or ""))
    title = str(detail.metadata.get("标题") or label or code)
    return IndexedVideo(
        code=detail.code,
        title=title,
        folder_path=folder_path,
        video_path=detail.video_path,
        actress_name=actress_names[0] if actress_names else actress_name,
        actress_names=actress_names,
        categories=categories,
        category_key=category_key,
        metadata_path=detail.metadata_path,
        cover_path=detail.cover_path,
        detail_url=detail.detail_url,
    )


def count_videos_by_code(code: str, locations: dict[str, list[str]] | None = None) -> int:
    wanted = str(code or "").strip().upper()
    if not wanted:
        return 0
    locs = locations if locations is not None else load_library_locations()
    count = 0
    for category in build_library_tree(locs):
        for actress in category.actresses:
            for video in actress.videos:
                if video.code.upper() == wanted:
                    count += 1
        for video in category.loose_videos:
            if video.code.upper() == wanted:
                count += 1
    return count


def build_library_index(locations: dict[str, list[str]] | None = None) -> list[IndexedVideo]:
    locs = locations if locations is not None else load_library_locations()
    items: list[IndexedVideo] = []
    for category in build_library_tree(locs):
        for actress in category.actresses:
            for video in actress.videos:
                items.append(
                    _to_indexed_video(
                        code=video.code,
                        folder_path=video.folder_path or actress.folder_path,
                        video_path=video.video_path,
                        actress_name=actress.name,
                        category_key=category.key,
                        label=video.label,
                    )
                )
        for video in category.loose_videos:
            items.append(
                _to_indexed_video(
                    code=video.code,
                    folder_path=video.folder_path,
                    video_path=video.video_path,
                    actress_name="",
                    category_key=category.key,
                    label=video.label,
                )
            )
    return items


def build_actress_index(
    videos: list[IndexedVideo] | None = None,
    locations: dict[str, list[str]] | None = None,
) -> list[IndexedActress]:
    source = videos if videos is not None else build_library_index(locations)
    groups: dict[str, IndexedActress] = {}
    for video in source:
        names = video.actress_names or ([video.actress_name] if video.actress_name else [])
        if not names:
            names = ["未知女优"]
        for name in names:
            key = name.casefold()
            if key not in groups:
                groups[key] = IndexedActress(
                    name=name,
                    folder_path=video.folder_path,
                    avatar_path="",
                    video_count=0,
                    videos=[],
                )
            entry = groups[key]
            if not entry.folder_path and video.folder_path:
                entry.folder_path = video.folder_path
            entry.videos.append(video)
            entry.video_count = len(entry.videos)

    tree_locs = locations if locations is not None else load_library_locations()
    for category in build_library_tree(tree_locs):
        for actress in category.actresses:
            name = str(actress.name or "").strip()
            if not name:
                continue
            key = name.casefold()
            if key not in groups:
                groups[key] = IndexedActress(
                    name=name,
                    folder_path=actress.folder_path,
                    avatar_path="",
                    video_count=0,
                    videos=[],
                )
            else:
                entry = groups[key]
                if not entry.folder_path and actress.folder_path:
                    entry.folder_path = actress.folder_path

    result = sorted(groups.values(), key=lambda item: item.name.casefold())
    for entry in result:
        entry.avatar_path = _pick_avatar(entry.folder_path, entry.videos)
    return result


def build_category_index(videos: list[IndexedVideo] | None = None) -> list[str]:
    source = videos if videos is not None else build_library_index()
    tags: dict[str, str] = {}
    for video in source:
        for tag in video.categories:
            tags.setdefault(tag.casefold(), tag)
    return sorted(tags.values(), key=lambda item: item.casefold())


def filter_videos_by_categories(
    videos: list[IndexedVideo],
    selected: set[str],
) -> list[IndexedVideo]:
    if not selected:
        return list(videos)
    wanted = {tag.casefold() for tag in selected}
    return [
        video
        for video in videos
        if wanted.intersection({tag.casefold() for tag in video.categories})
    ]
