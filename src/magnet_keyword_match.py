"""Keyword matching for magnet preview / filter rules."""

from __future__ import annotations

import re


def split_semicolon_keywords(text: str) -> list[str]:
    parts: list[str] = []
    for item in str(text or "").split(";"):
        token = item.strip()
        if token:
            parts.append(token)
    return parts


def normalize_keyword_match_text(text: str) -> str:
    return re.sub(r"\s+", "", str(text or ""))


def text_contains_keyword(text: str, keyword: str) -> bool:
    needle = normalize_keyword_match_text(keyword)
    if not needle:
        return False
    return needle in normalize_keyword_match_text(text)


def match_preview_keyword_content(files: list[str] | None, keywords: list[str] | str | None) -> bool:
    file_list = [str(name or "").strip() for name in (files or []) if str(name or "").strip()]
    if isinstance(keywords, str):
        active = split_semicolon_keywords(keywords)
    else:
        active = [str(keyword or "").strip() for keyword in (keywords or []) if str(keyword or "").strip()]
    if not active or not file_list:
        return False
    return any(
        all(text_contains_keyword(file_name, keyword) for keyword in active) for file_name in file_list
    )
