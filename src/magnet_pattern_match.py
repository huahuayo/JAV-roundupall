"""Match magnet names / file names using {CODE} / {code} placeholder rules."""

from __future__ import annotations

import re

CODE_UPPER = "{CODE}"
CODE_LOWER = "{code}"

_TOKEN_SPLIT = re.compile(r"(\{CODE\}|\{code\})")


def split_normalized_code(code: str) -> tuple[str, str]:
    """Return (upper_prefix_code, lower_prefix_code) e.g. IPZZ-576, ipzz-576."""
    normalized = str(code or "").upper().strip()
    match = re.match(r"^([A-Z]+)-?(\d+[A-Z]?)$", normalized)
    if not match:
        lowered = normalized.lower()
        return normalized, lowered
    upper = f"{match.group(1).upper()}-{match.group(2)}"
    lower = f"{match.group(1).lower()}-{match.group(2)}"
    return upper, lower


def normalize_code(code: str) -> str:
    return split_normalized_code(code)[0]


def _literal_to_regex(fragment: str) -> str:
    parts: list[str] = []
    for char in fragment:
        if char.isalpha():
            parts.append(f"[{char.lower()}{char.upper()}]")
        else:
            parts.append(re.escape(char))
    return "".join(parts)


def _code_token_to_regex(code: str) -> str:
    upper, _ = split_normalized_code(code)
    return _literal_to_regex(upper)


def pattern_to_regex(pattern: str, code: str) -> re.Pattern[str] | None:
    """Build anchored regex: {CODE}/{code} are equivalent; code letters are case-insensitive."""
    text = str(pattern or "").strip()
    if not text:
        return None

    body_parts: list[str] = []
    for token in _TOKEN_SPLIT.split(text):
        if token in (CODE_UPPER, CODE_LOWER):
            body_parts.append(_code_token_to_regex(code))
        elif token:
            body_parts.append(_literal_to_regex(token))

    body = re.sub(r"\s+", "", "".join(body_parts))
    if not body:
        return None
    return re.compile(f"^{body}$")


def matches_pattern(text: str, pattern: str, code: str) -> bool:
    """
    Full-string match. {CODE}-C matches IPZZ-576-c but not IPZZ-576.
    {CODE} and {code} are equivalent; code letters match case-insensitively.
    """
    regex = pattern_to_regex(pattern, code)
    if regex is None:
        return False
    normalized = re.sub(r"\s+", "", str(text or ""))
    return bool(regex.match(normalized))


def expand_pattern_display(pattern: str, code: str) -> str:
    """Best-effort preview string for UI (uses upper/lower placeholders only)."""
    upper, lower = split_normalized_code(code)
    return (
        str(pattern or "")
        .replace(CODE_UPPER, upper)
        .replace(CODE_LOWER, lower)
    )
