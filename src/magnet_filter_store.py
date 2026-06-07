"""Persist magnet filter priority rules for 18mag TXT generation.

4K detection for magnet names is defined in src.parser.is_4k_magnet_name
(marks: [4K], .4k., 2160p, uhd). Example name_pattern values:
{CODE}.[4K], {CODE}.4K, {CODE}-4K, {CODE} 2160p — see FOUR_K_MAGNET_PATTERN_HINTS.
"""

from __future__ import annotations

import json
from typing import Any

from src.config import APP_DIR

RULES_PATH = APP_DIR / "magnet_filter_rules.json"
PRIORITY_COUNT = 8
PREVIEW_KEYWORDS = "keywords"
PREVIEW_SINGLE_MP4 = "single_mp4"

CODE_PLACEHOLDER = "{CODE}"

TXT_STAGE_4K = "4k"
TXT_STAGE_SUBTITLE = "subtitle"
TXT_STAGE_HD = "hd"
DEFAULT_TXT_SCREEN_STAGES = [TXT_STAGE_4K, TXT_STAGE_SUBTITLE, TXT_STAGE_HD]
VALID_TXT_STAGES = frozenset(DEFAULT_TXT_SCREEN_STAGES)


def _empty_rule(priority: int) -> dict[str, Any]:
    return {
        "priority": priority,
        "enabled": False,
        "name_pattern": "",
        "preview_mode": PREVIEW_KEYWORDS,
        "preview_keywords": [],
    }


def default_rules() -> dict[str, Any]:
    rules = [_empty_rule(i) for i in range(1, PRIORITY_COUNT + 1)]
    rules[0] = {
        "priority": 1,
        "enabled": True,
        "name_pattern": f"{CODE_PLACEHOLDER}-C",
        "preview_mode": PREVIEW_KEYWORDS,
        "preview_keywords": ["社区最新情报"],
    }
    rules[1] = {
        "priority": 2,
        "enabled": True,
        "name_pattern": f"{CODE_PLACEHOLDER}ch",
        "preview_mode": PREVIEW_SINGLE_MP4,
        "preview_keywords": [],
    }
    return {
        "version": 1,
        "reject_keywords": [
            "乐鱼体育",
            "少女激情游戏",
            "广告合作.txt",
            "日韩欧美国产同步",
            "有趣台妹小视频",
        ],
        "display_hide_keywords": ["合集", "合輯"],
        "display_highlight_rules": [
            {
                "id": 1,
                "enabled": True,
                "keywords": ["4K", "4k", "2160p", "UHD"],
                "color": "#dc2626",
            }
        ],
        "priorities": rules,
        "txt_screen_stages": list(DEFAULT_TXT_SCREEN_STAGES),
    }


def _split_semicolon_keywords(text: str) -> list[str]:
    parts: list[str] = []
    for item in str(text or "").split(";"):
        token = item.strip()
        if token:
            parts.append(token)
    return parts


def _split_keywords(text: str) -> list[str]:
    parts: list[str] = []
    for line in str(text or "").replace(",", "\n").splitlines():
        item = line.strip()
        if item:
            parts.append(item)
    return parts


def _normalize_rule(raw: dict[str, Any], priority: int) -> dict[str, Any]:
    base = _empty_rule(priority)
    preview_mode = str(raw.get("preview_mode", PREVIEW_KEYWORDS)).strip().lower()
    if preview_mode not in (PREVIEW_KEYWORDS, PREVIEW_SINGLE_MP4):
        preview_mode = PREVIEW_KEYWORDS

    keywords = raw.get("preview_keywords")
    if isinstance(keywords, str):
        keywords = _split_keywords(keywords)
    elif isinstance(keywords, list):
        keywords = [str(k).strip() for k in keywords if str(k).strip()]
    else:
        keywords = []

    base.update(
        {
            "priority": priority,
            "enabled": bool(raw.get("enabled", False)),
            "name_pattern": str(raw.get("name_pattern", "")).strip(),
            "preview_mode": preview_mode,
            "preview_keywords": keywords,
        }
    )
    return base


def is_usable_enabled_rule(rule: dict[str, Any]) -> bool:
    if not rule.get("enabled"):
        return False
    if not str(rule.get("name_pattern", "")).strip():
        return False
    mode = str(rule.get("preview_mode", PREVIEW_KEYWORDS)).strip().lower()
    if mode == PREVIEW_SINGLE_MP4:
        return True
    if mode == PREVIEW_KEYWORDS:
        return bool(rule.get("preview_keywords"))
    return False


def has_enabled_magnet_filter_rules(data: dict[str, Any] | None = None) -> bool:
    payload = data if data is not None else load_magnet_filter_rules()
    priorities = payload.get("priorities") or []
    return any(is_usable_enabled_rule(rule) for rule in priorities if isinstance(rule, dict))


def empty_rules_config() -> dict[str, Any]:
    return {
        "version": 1,
        "reject_keywords": [],
        "display_hide_keywords": [],
        "display_highlight_rules": [],
        "priorities": [_empty_rule(i) for i in range(1, PRIORITY_COUNT + 1)],
        "txt_screen_stages": list(DEFAULT_TXT_SCREEN_STAGES),
    }


def _normalize_txt_screen_stages(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return list(DEFAULT_TXT_SCREEN_STAGES)
    ordered: list[str] = []
    seen: set[str] = set()
    for item in raw:
        stage = str(item or "").strip().lower()
        if stage in VALID_TXT_STAGES and stage not in seen:
            seen.add(stage)
            ordered.append(stage)
    for stage in DEFAULT_TXT_SCREEN_STAGES:
        if stage not in seen:
            ordered.append(stage)
    return ordered


def _normalize_highlight_color(color: str) -> str:
    text = str(color or "#dc2626").strip() or "#dc2626"
    if not text.startswith("#"):
        text = f"#{text}"
    hex_part = text[1:]
    if len(hex_part) == 3 and all(ch in "0123456789abcdefABCDEF" for ch in hex_part):
        return f"#{hex_part[0] * 2}{hex_part[1] * 2}{hex_part[2] * 2}".lower()
    if len(hex_part) == 4 and all(ch in "0123456789abcdefABCDEF" for ch in hex_part):
        return f"#{hex_part}{hex_part[:2]}".lower()
    if len(hex_part) == 6 and all(ch in "0123456789abcdefABCDEF" for ch in hex_part):
        return f"#{hex_part}".lower()
    return "#dc2626"


def _normalize_highlight_rules(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        keywords = item.get("keywords")
        if isinstance(keywords, str):
            keywords = _split_keywords(keywords)
        elif isinstance(keywords, list):
            keywords = [str(k).strip() for k in keywords if str(k).strip()]
        else:
            keywords = []
        color = _normalize_highlight_color(str(item.get("color", "#dc2626")).strip() or "#dc2626")
        result.append(
            {
                "id": int(item.get("id", index + 1)),
                "enabled": bool(item.get("enabled", True)),
                "keywords": keywords,
                "color": color,
            }
        )
    return result


def normalize_rules(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data or not isinstance(data, dict):
        return empty_rules_config()

    reject = data.get("reject_keywords")
    if isinstance(reject, str):
        reject_keywords = _split_semicolon_keywords(reject)
    elif isinstance(reject, list):
        reject_keywords = [str(k).strip() for k in reject if str(k).strip()]
    else:
        reject_keywords = []

    display_hide = data.get("display_hide_keywords")
    if isinstance(display_hide, str):
        display_hide_keywords = _split_semicolon_keywords(display_hide)
    elif isinstance(display_hide, list):
        display_hide_keywords = [str(k).strip() for k in display_hide if str(k).strip()]
    else:
        display_hide_keywords = []

    display_highlight_rules = _normalize_highlight_rules(data.get("display_highlight_rules"))

    incoming = data.get("priorities") or []
    by_priority: dict[int, dict[str, Any]] = {}
    if isinstance(incoming, list):
        for item in incoming:
            if not isinstance(item, dict):
                continue
            try:
                p = int(item.get("priority", 0))
            except (TypeError, ValueError):
                continue
            if 1 <= p <= PRIORITY_COUNT:
                by_priority[p] = _normalize_rule(item, p)

    priorities = [by_priority.get(i, _empty_rule(i)) for i in range(1, PRIORITY_COUNT + 1)]
    txt_screen_stages = _normalize_txt_screen_stages(data.get("txt_screen_stages"))
    return {
        "version": 1,
        "reject_keywords": reject_keywords,
        "display_hide_keywords": display_hide_keywords,
        "display_highlight_rules": display_highlight_rules,
        "priorities": priorities,
        "txt_screen_stages": txt_screen_stages,
    }


def load_magnet_filter_rules() -> dict[str, Any]:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if not RULES_PATH.exists():
        return empty_rules_config()
    try:
        raw = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return empty_rules_config()
    return normalize_rules(raw)


def save_magnet_filter_rules(data: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_rules(data)
    APP_DIR.mkdir(parents=True, exist_ok=True)
    RULES_PATH.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return normalized


def get_magnet_filter_payload() -> dict[str, Any]:
    return load_magnet_filter_rules()
