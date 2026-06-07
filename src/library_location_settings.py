"""Semantic local library folder paths for JavDB matching."""

from __future__ import annotations

from pathlib import Path

from src.bridge_settings import _read_config, _write_config

LIBRARY_LOCATION_KEYS: tuple[tuple[str, str], ...] = (
    ("pending_download", "待下载"),
    ("magnet_saved", "磁链已保存"),
    ("video_downloaded", "影片已下载"),
    ("video_cracked", "影片已破解"),
    ("loose_pending", "散片待处理"),
)

_LABEL_BY_KEY = {key: label for key, label in LIBRARY_LOCATION_KEYS}


class LibraryLocationError(ValueError):
    def __init__(self, key: str, path: str, reason: str = "invalid") -> None:
        self.key = key
        self.path = path
        self.reason = reason
        super().__init__(f"{key}:{path}:{reason}")


def get_library_location_label(key: str) -> str:
    return _LABEL_BY_KEY.get(key, key)


def normalize_library_path(raw: str) -> str:
    text = str(raw or "").strip().strip('"').strip("'")
    if not text:
        return ""
    if text.startswith("//"):
        text = "\\\\" + text[2:].replace("/", "\\")
    elif text.startswith("\\\\"):
        text = "\\\\" + text[2:].replace("/", "\\")
    return text


def _looks_like_unc(path: str) -> bool:
    return path.startswith("\\\\") and len(path) >= 4 and path[2] != "?"


def _looks_like_local_absolute(path: str) -> bool:
    if len(path) >= 2 and path[1] == ":":
        return True
    return path.startswith("\\\\?\\")


def validate_library_path(raw: str) -> str:
    path = normalize_library_path(raw)
    if not path:
        raise LibraryLocationError("", "", "empty")

    if _looks_like_unc(path):
        parts = [part for part in path[2:].split("\\") if part]
        if len(parts) < 2:
            raise LibraryLocationError("", path, "invalid_unc")
        return path

    folder = Path(path)
    if folder.is_dir():
        return str(folder.resolve())

    if _looks_like_local_absolute(path):
        return path

    raise LibraryLocationError("", path, "invalid")


def _normalize_stored_paths(value: object) -> list[str]:
    if isinstance(value, list):
        return [normalize_library_path(str(item)) for item in value if normalize_library_path(str(item))]
    if isinstance(value, str):
        single = normalize_library_path(value)
        return [single] if single else []
    return []


def _dedupe_paths(paths: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for path in paths:
        key = path.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def load_library_locations() -> dict[str, list[str]]:
    stored = _read_config().get("library_locations", {})
    if not isinstance(stored, dict):
        stored = {}

    result: dict[str, list[str]] = {}
    for key, _label in LIBRARY_LOCATION_KEYS:
        paths = _normalize_stored_paths(stored.get(key))
        validated: list[str] = []
        for path in paths:
            try:
                validated.append(validate_library_path(path))
            except LibraryLocationError:
                validated.append(path)
        result[key] = _dedupe_paths(validated)
    return result


def save_library_locations(locations: dict[str, list[str]]) -> dict[str, list[str]]:
    validated: dict[str, list[str]] = {}
    for key, _label in LIBRARY_LOCATION_KEYS:
        raw_paths = locations.get(key, [])
        if not isinstance(raw_paths, list):
            raw_paths = [raw_paths] if raw_paths else []

        paths: list[str] = []
        for raw in raw_paths:
            text = normalize_library_path(str(raw or ""))
            if not text:
                continue
            try:
                paths.append(validate_library_path(text))
            except LibraryLocationError as exc:
                raise LibraryLocationError(key, text, exc.reason) from exc
        validated[key] = _dedupe_paths(paths)

    data = _read_config()
    data["library_locations"] = validated
    _write_config(data)
    return validated


def get_effective_paths(key: str, explicit: dict[str, list[str]] | None = None) -> list[str]:
    data = explicit if explicit is not None else load_library_locations()
    return list(data.get(key, []))


def get_effective_library_locations() -> dict[str, list[str]]:
    return load_library_locations()


def get_library_locations_payload() -> dict[str, list[str]]:
    return get_effective_library_locations()
