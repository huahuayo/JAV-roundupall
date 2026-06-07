"""Parse JAV metadata from filenames and folder names."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import unquote
from pathlib import Path

# Common patterns: SSIS-001, ABC123, FC2-PPV-1234567, HEYZO-1234
# Subtitle release tags (C/CH) are matched but not captured — they are not part of the code.
_SUBTITLE_SUFFIX = r"(?:[-_.]?(?:CH|C)(?=\b|[._\s\[(@]|$))"
_CODE_PATTERNS = [
    re.compile(rf"(FC2-PPV-\d{{6,7}})(?:{_SUBTITLE_SUFFIX})?", re.IGNORECASE),
    re.compile(rf"(HEYZO-\d{{4}})(?:{_SUBTITLE_SUFFIX})?", re.IGNORECASE),
    re.compile(rf"([A-Z]{{2,10}}-\d{{2,5}})(?:{_SUBTITLE_SUFFIX})?", re.IGNORECASE),
    re.compile(r"([A-Z]{2,10}-\d{2,5}[A-Z])(?=\b|[._\s\[(@]|$)", re.IGNORECASE),
    re.compile(rf"([A-Z]{{2,10}}\d{{2,5}})(?:{_SUBTITLE_SUFFIX})?", re.IGNORECASE),
    re.compile(r"([A-Z]{2,10}\d{2,5}[A-Z])(?=\b|[._\s\[(@]|$)", re.IGNORECASE),
]

# 4K markers in magnet/ed2k display names (shared with magnet filter priority rules).
_FOUR_K_PATTERNS = (
    re.compile(r"\[4k\]", re.IGNORECASE),
    re.compile(r"(?:^|[^a-z0-9])4k(?:[^a-z0-9]|$)", re.IGNORECASE),
    re.compile(r"\b2160p\b", re.IGNORECASE),
    re.compile(r"\buhd\b", re.IGNORECASE),
)

# Example name_pattern values for magnet filter UI (detection uses is_4k_magnet_name).
FOUR_K_MAGNET_PATTERN_HINTS = (
    "{CODE}.[4K]",
    "{CODE}.4K",
    "{CODE}-4K",
    "{CODE} 2160p",
)

# Strip common release tags before matching
_NOISE_PATTERN = re.compile(
    r"[\[\(（【].*?[\]\)）】]|"
    r"\b(1080p|720p|4k|2160p|hd|fhd|uhd|x264|x265|h264|h265|hevc|"
    r"uncensored|censored|chinese|subtitle|sub|无码|有码|中字|字幕)\b",
    re.IGNORECASE,
)


def normalize_code(raw: str) -> str:
    """Normalize a code like abc-123 -> ABC-123 (without subtitle suffix C/CH)."""
    raw = raw.upper().strip()
    match = re.match(r"^([A-Z]+)-?(\d{2,5})([A-Z]{0,2})?$", raw)
    if match:
        prefix, number, suffix = match.group(1), match.group(2), match.group(3) or ""
        if suffix.upper() in ("C", "CH"):
            suffix = ""
        return f"{prefix}-{number}{suffix}"
    return raw


def extract_code_from_text(text: str) -> str | None:
    cleaned = _NOISE_PATTERN.sub(" ", text)
    cleaned = re.sub(r"[_\.\s]+", " ", cleaned)

    for pattern in _CODE_PATTERNS:
        match = pattern.search(cleaned)
        if match:
            return normalize_code(match.group(1))

    return None


def extract_code_from_magnet_line(line: str) -> str | None:
    """Extract JAV code from a magnet link, ed2k link, or plain text line."""
    text = str(line or "").strip()
    if not text:
        return None

    lower = text.lower()
    if lower.startswith("magnet:"):
        dn_match = re.search(r"[?&]dn=([^&]+)", text, re.IGNORECASE)
        if dn_match:
            code = extract_code_from_text(unquote(dn_match.group(1)))
            if code:
                return code

    if lower.startswith("ed2k://"):
        parts = text.split("|")
        if len(parts) >= 3:
            code = extract_code_from_text(parts[2])
            if code:
                return code

    return extract_code_from_text(text)


def _magnet_display_name(line: str) -> str:
    text = str(line or "").strip()
    lower = text.lower()
    if lower.startswith("magnet:"):
        dn_match = re.search(r"[?&]dn=([^&]+)", text, re.IGNORECASE)
        if dn_match:
            return unquote(dn_match.group(1))
    if lower.startswith("ed2k://"):
        parts = text.split("|")
        if len(parts) >= 3:
            return parts[2]
    return text


def is_4k_magnet_name(display: str) -> bool:
    """Return True when magnet/ed2k display name indicates a 4K release."""
    text = str(display or "").strip()
    if not text:
        return False
    return any(pattern.search(text) for pattern in _FOUR_K_PATTERNS)


def is_4k_in_magnet_line(line: str) -> bool:
    """Return True when a magnet/ed2k line points to a 4K release."""
    return is_4k_magnet_name(_magnet_display_name(line))


def has_subtitle_marker_in_text(display: str, code: str) -> bool:
    """Return True when text indicates subtitles (-c, -C, ch, CH after code)."""
    text = str(display or "").strip()
    if not text or not code:
        return False

    normalized = normalize_code(code)
    compact = normalized.replace("-", "")
    variants = (normalized, compact)
    for variant in variants:
        escaped = re.escape(variant)
        pattern = rf"{escaped}(?:[-_.](?:C|CH)|(?:C|CH))(?=\b|[._\s\[(@]|$)"
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return has_loose_subtitle_token(text)


def has_subtitle_in_magnet_line(line: str, code: str) -> bool:
    """Return True when magnet/ed2k name indicates subtitles (-c, -C, ch, CH after code)."""
    return has_subtitle_marker_in_text(_magnet_display_name(line), code)


def has_subtitle_in_filename(filename: str, code: str) -> bool:
    """Return True when a video filename indicates embedded subtitle markers."""
    return has_subtitle_marker_in_text(filename, code)


def subtitle_marker_kind_in_text(display: str, code: str) -> str:
    """Return 'ch', 'c', or '' for subtitle marker after code in a filename."""
    text = str(display or "").strip()
    if not text or not code:
        return ""

    normalized = normalize_code(code)
    compact = normalized.replace("-", "")
    for variant in (normalized, compact):
        escaped = re.escape(variant)
        if re.search(rf"{escaped}(?:[-_.](?:CH))(?=\b|[._\s\[(@]|$)", text, re.IGNORECASE):
            return "ch"
        if re.search(rf"{escaped}(?:[-_.](?:C))(?=\b|[._\s\[(@]|$)", text, re.IGNORECASE):
            return "c"
        if re.search(rf"{escaped}(?:CH)(?=\b|[._\s\[(@]|$)", text, re.IGNORECASE):
            return "ch"
        if re.search(rf"{escaped}(?:C)(?=\b|[._\s\[(@]|$)", text, re.IGNORECASE):
            return "c"
    return loose_subtitle_token_kind(text)


def subtitle_marker_kind_in_filename(filename: str, code: str) -> str:
    return subtitle_marker_kind_in_text(filename, code)


def is_4k_in_filename(filename: str) -> bool:
    """Return True when a video filename indicates 4K."""
    return is_4k_magnet_name(filename)


_LOOSE_TOKEN_BOUNDARY = r"(?:^|[^\w])"
_LOOSE_TOKEN_END = r"(?:$|[^\w])"
_LOOSE_UC_TOKEN = re.compile(rf"{_LOOSE_TOKEN_BOUNDARY}UC{_LOOSE_TOKEN_END}", re.IGNORECASE)
_LOOSE_U_TOKEN = re.compile(rf"{_LOOSE_TOKEN_BOUNDARY}U{_LOOSE_TOKEN_END}", re.IGNORECASE)
_LOOSE_RESTORED_TOKEN = re.compile(rf"{_LOOSE_TOKEN_BOUNDARY}restored{_LOOSE_TOKEN_END}", re.IGNORECASE)
_LOOSE_CH_TOKEN = re.compile(rf"{_LOOSE_TOKEN_BOUNDARY}CH{_LOOSE_TOKEN_END}", re.IGNORECASE)
_LOOSE_C_TOKEN = re.compile(rf"{_LOOSE_TOKEN_BOUNDARY}C{_LOOSE_TOKEN_END}", re.IGNORECASE)
_LOOSE_RELEASE_TOKENS = re.compile(
    r"\b(?:UC|U|CH|C|RESTORED|4K|2160P|1080P|720P|HD|FHD|UHD|HEVC|X264|X265|H264|H265)\b",
    re.IGNORECASE,
)
_PLACEHOLDER_ACTRESS_NAMES = {
    "NA",
    "N/A",
    "N-A",
    "UNKNOWN",
    "NONE",
    "NULL",
    "未知",
    "无",
    "-",
    "—",
}


def has_loose_uncensored_token(text: str) -> bool:
    """Detect standalone U / UC / restored release tags anywhere in a filename."""
    body = str(text or "")
    if _LOOSE_UC_TOKEN.search(body):
        return True
    if _LOOSE_U_TOKEN.search(body):
        return True
    return bool(_LOOSE_RESTORED_TOKEN.search(body))


def has_loose_subtitle_token(text: str) -> bool:
    body = str(text or "")
    if _LOOSE_CH_TOKEN.search(body):
        return True
    return bool(_LOOSE_C_TOKEN.search(body))


def loose_subtitle_token_kind(text: str) -> str:
    body = str(text or "")
    if _LOOSE_CH_TOKEN.search(body):
        return "ch"
    if _LOOSE_C_TOKEN.search(body):
        return "c"
    return ""


def is_placeholder_actress_name(name: str) -> bool:
    text = str(name or "").strip()
    if not text:
        return True
    compact = re.sub(r"[\s_\-./\\]+", "", text).upper()
    if compact in _PLACEHOLDER_ACTRESS_NAMES:
        return True
    if re.fullmatch(r"N[\s\-/]*A", text, re.IGNORECASE):
        return True
    return False


def extract_actress_from_loose_filename(filename: str, code: str) -> str:
    """Extract actress text already present in a loose video filename."""
    stem = Path(filename).stem if str(filename or "").strip() else str(filename or "")
    text = str(stem or "").strip()
    normalized = normalize_code(code)
    if not text or not normalized:
        return ""

    for variant in (normalized, normalized.replace("-", "")):
        text = re.sub(re.escape(variant), " ", text, flags=re.IGNORECASE)

    text = _LOOSE_RELEASE_TOKENS.sub(" ", text)
    text = _NOISE_PATTERN.sub(" ", text)
    text = re.sub(r"[\s_\-\.\[\]（）()【】]+", " ", text).strip()
    if is_placeholder_actress_name(text) or len(text) < 2:
        return ""
    return text


def resolve_loose_actress_name(
    *,
    filename_actress: str = "",
    javdb_actress: str = "",
) -> str:
    from_file = str(filename_actress or "").strip()
    from_javdb = str(javdb_actress or "").split("、")[0].strip()
    if from_file and not is_placeholder_actress_name(from_file):
        return from_file
    if from_javdb and not is_placeholder_actress_name(from_javdb):
        return from_javdb
    if from_file:
        return from_file
    if from_javdb:
        return from_javdb
    return "未知"


def refresh_loose_media_flags(item: dict[str, Any]) -> dict[str, Any]:
    """Re-parse release flags from the current filename before rename/classify."""
    source_file = str(item.get("source_file") or "")
    code = normalize_code(str(item.get("code") or ""))
    if not source_file or not code:
        return item

    has_uncensored = has_uncensored_marker_in_filename(source_file, code) or has_loose_uncensored_token(
        source_file
    )
    has_sub_name = has_subtitle_in_filename(source_file, code)
    has_uncensored_sub = has_cracked_subtitle_burned_in_filename(source_file, code)
    subtitle_kind = subtitle_marker_kind_in_filename(source_file, code)
    is_4k = is_4k_in_filename(source_file)
    has_sub_file = bool(item.get("has_subtitle_file"))
    has_censored_ch_file = bool(has_sub_name and not has_uncensored)

    updated = dict(item)
    updated["has_uncensored"] = has_uncensored
    updated["has_subtitle_name"] = has_sub_name
    updated["has_uncensored_sub_in_name"] = has_uncensored_sub
    updated["subtitle_kind"] = subtitle_kind
    updated["is_4k"] = is_4k
    updated["has_subtitle"] = bool(has_sub_name or has_sub_file or has_uncensored_sub)
    updated["has_censored_ch_file"] = has_censored_ch_file
    updated["crack_status"] = resolve_video_crack_status(
        has_uncensored_file=has_uncensored,
        has_uncensored_sub_in_name=has_uncensored_sub,
        has_censored_ch_file=has_censored_ch_file,
        has_subtitle_file=has_sub_file,
    )
    extracted = extract_actress_from_loose_filename(source_file, code)
    existing = str(item.get("filename_actress") or "").strip()
    if extracted and not is_placeholder_actress_name(extracted):
        updated["filename_actress"] = extracted
    elif existing and not is_placeholder_actress_name(existing):
        updated["filename_actress"] = existing
    elif extracted:
        updated["filename_actress"] = extracted
    return updated


def has_uncensored_marker_in_text(display: str, code: str) -> bool:
    """Return True when filename indicates mosaic removed (-U / -UC / restored after code)."""
    text = str(display or "").strip()
    if not text or not code:
        return False

    normalized = normalize_code(code)
    compact = normalized.replace("-", "")
    for variant in (normalized, compact):
        idx = text.upper().find(variant.upper())
        if idx < 0:
            continue
        tail = text[idx + len(variant) :]
        tail = re.sub(r"^[-_.\s]+", "", tail, flags=re.IGNORECASE)
        if re.match(r"UC(?:[-_.]|$)", tail, re.IGNORECASE):
            return True
        if re.match(r"U(?:[-_.\d\s]|$)", tail, re.IGNORECASE):
            return True
    return has_loose_uncensored_token(text)


def has_uncensored_marker_in_filename(filename: str, code: str) -> bool:
    return has_uncensored_marker_in_text(filename, code)


def has_cracked_subtitle_burned_in_text(display: str, code: str) -> bool:
    """Return True when cracked release name includes burned subtitle marker (-UC)."""
    text = str(display or "").strip()
    if not text or not code:
        return False

    normalized = normalize_code(code)
    compact = normalized.replace("-", "")
    for variant in (normalized, compact):
        idx = text.upper().find(variant.upper())
        if idx < 0:
            continue
        tail = text[idx + len(variant) :]
        tail = re.sub(r"^[-_.\s]+", "", tail, flags=re.IGNORECASE)
        if re.match(r"UC(?:[-_.]|$)", tail, re.IGNORECASE):
            return True
    return False


def has_cracked_subtitle_burned_in_filename(filename: str, code: str) -> bool:
    return has_cracked_subtitle_burned_in_text(filename, code)


CRACK_STATUS_CRACKED = "cracked"
CRACK_STATUS_CRACKED_SUB_PENDING_BURN = "cracked_sub_pending_burn"
CRACK_STATUS_PENDING_EXTRACT_SUB = "pending_extract_sub"
CRACK_STATUS_PENDING_CRACK = "pending_crack"

CRACK_STATUS_LABELS: dict[str, str] = {
    CRACK_STATUS_CRACKED: "已破解",
    CRACK_STATUS_CRACKED_SUB_PENDING_BURN: "已破解·字幕待烧录",
    CRACK_STATUS_PENDING_EXTRACT_SUB: "待提取字幕",
    CRACK_STATUS_PENDING_CRACK: "待破解",
}


def resolve_video_crack_status(
    *,
    has_uncensored_file: bool,
    has_uncensored_sub_in_name: bool,
    has_censored_ch_file: bool,
    has_subtitle_file: bool,
) -> str:
    if has_uncensored_file:
        if has_subtitle_file and not has_uncensored_sub_in_name:
            return CRACK_STATUS_CRACKED_SUB_PENDING_BURN
        return CRACK_STATUS_CRACKED
    if has_censored_ch_file:
        return CRACK_STATUS_PENDING_EXTRACT_SUB
    return CRACK_STATUS_PENDING_CRACK


def build_video_cracked_code_info(
    *,
    code: str,
    has_uncensored_file: bool,
    has_uncensored_sub_in_name: bool,
    has_censored_ch_file: bool,
    has_subtitle_file: bool,
    has_subtitle_name: bool,
    is_4k: bool,
    crack_status: str,
    source_file: str = "",
    source_path: str = "",
    uncensored_source_file: str = "",
    censored_ch_source_file: str = "",
) -> dict[str, str | bool]:
    normalized = normalize_code(code)
    has_subtitle = bool(
        has_uncensored_sub_in_name
        or (crack_status == CRACK_STATUS_CRACKED and (has_subtitle_file or has_subtitle_name))
        or (crack_status == CRACK_STATUS_PENDING_EXTRACT_SUB and (has_subtitle_name or has_subtitle_file))
    )
    return {
        "code": normalized,
        "source_file": source_file,
        "source_path": source_path,
        "uncensored_source_file": uncensored_source_file,
        "censored_ch_source_file": censored_ch_source_file,
        "is_4k": is_4k,
        "has_subtitle": has_subtitle,
        "has_subtitle_file": has_subtitle_file,
        "has_subtitle_name": has_subtitle_name,
        "has_uncensored_file": has_uncensored_file,
        "has_uncensored_sub_in_name": has_uncensored_sub_in_name,
        "has_censored_ch_file": has_censored_ch_file,
        "crack_status": crack_status,
        "crack_status_label": CRACK_STATUS_LABELS.get(crack_status, crack_status),
    }


def build_video_downloaded_code_info(
    *,
    code: str,
    has_subtitle_file: bool,
    has_subtitle_name: bool,
    is_4k: bool,
    source_file: str = "",
    source_path: str = "",
) -> dict[str, str | bool]:
    """Aggregate per-code flags for video-downloaded library scan."""
    normalized = normalize_code(code)
    has_subtitle = bool(has_subtitle_file or has_subtitle_name)
    return {
        "code": normalized,
        "source_file": source_file,
        "source_path": source_path,
        "is_4k": is_4k,
        "has_subtitle": has_subtitle,
        "has_subtitle_file": has_subtitle_file,
        "has_subtitle_name": has_subtitle_name,
    }


def build_magnet_code_media_info(
    *,
    code: str,
    has_4k_magnet: bool,
    has_subtitle_magnet: bool,
    has_non_4k_subtitle_magnet: bool,
    has_subtitle_file: bool,
    source_file: str = "",
    source_line: int = 0,
    raw_line: str = "",
) -> dict[str, str | int | bool]:
    """Aggregate per-code flags for magnet-saved scan and TXT summaries."""
    normalized = normalize_code(code)
    subtitle_extract_for_4k = bool(has_4k_magnet and has_non_4k_subtitle_magnet)
    four_k_has_subtitle_file = bool(has_4k_magnet and has_subtitle_file)
    four_k_has_subtitle_via_ch = subtitle_extract_for_4k
    four_k_has_subtitle = bool(has_4k_magnet and (has_subtitle_file or subtitle_extract_for_4k))

    if has_4k_magnet:
        has_subtitle = four_k_has_subtitle
    else:
        has_subtitle = bool(has_subtitle_magnet or has_subtitle_file)

    return {
        "code": normalized,
        "source_file": source_file,
        "source_line": source_line,
        "raw_line": raw_line,
        "is_4k": has_4k_magnet,
        "has_subtitle": has_subtitle,
        "has_subtitle_file": has_subtitle_file,
        "has_subtitle_magnet": has_subtitle_magnet,
        "four_k_has_subtitle": four_k_has_subtitle,
        "four_k_has_subtitle_file": four_k_has_subtitle_file,
        "four_k_has_subtitle_via_ch": four_k_has_subtitle_via_ch,
        "subtitle_extract_for_4k": subtitle_extract_for_4k,
    }


def code_sort_key(raw_code: str) -> tuple[str, int, str]:
    """Sort key: letter prefix, numeric part, trailing letter suffix."""
    normalized = normalize_code(raw_code)
    match = re.match(r"^([A-Z]+)-(\d+)([A-Z]?)$", normalized)
    if match:
        return match.group(1), int(match.group(2)), match.group(3)
    return normalized, 0, ""


def parse_video_metadata(path: Path) -> dict[str, str | None]:
    """Extract code and title hints from file path."""
    stem = path.stem
    parent = path.parent.name

    code = extract_code_from_text(stem) or extract_code_from_text(parent)
    title = stem if code is None else stem.replace(code, "").replace(code.replace("-", ""), "")
    title = re.sub(r"^[\s_\-\.]+|[\s_\-\.]+$", "", title) or None

    return {"code": code, "title": title}
