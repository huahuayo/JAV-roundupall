/**
 * {CODE} / {code} 等价，番号字母大小写不敏感（SSIS-204 = ssis-204）。
 * 字面量中的英文字母（如 -C）大小写不敏感：-C = -c。
 * 须完整匹配：{CODE}-C 不匹配 {CODE}。
 */
(function () {
  "use strict";

  const TOKEN_SPLIT = /(\{CODE\}|\{code\})/g;

  function splitNormalizedCode(code) {
    const text = String(code || "").toUpperCase().trim();
    const match = text.match(/^([A-Z]+)-?(\d+[A-Z]?)$/i);
    if (!match) {
      const lowered = text.toLowerCase();
      return { upper: text, lower: lowered };
    }
    return {
      upper: `${match[1].toUpperCase()}-${match[2]}`,
      lower: `${match[1].toLowerCase()}-${match[2]}`,
    };
  }

  function normalizeCode(code) {
    return splitNormalizedCode(code).upper;
  }

  function literalToRegex(fragment) {
    let out = "";
    for (const ch of fragment) {
      if (/[a-zA-Z]/.test(ch)) {
        out += `[${ch.toLowerCase()}${ch.toUpperCase()}]`;
      } else {
        out += ch.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      }
    }
    return out;
  }

  function codeTokenToRegex(code) {
    const { upper } = splitNormalizedCode(code);
    return literalToRegex(upper);
  }

  function patternToRegex(pattern, code) {
    const text = String(pattern || "").trim();
    if (!text) return null;

    const parts = text.split(TOKEN_SPLIT).map((token) => {
      if (token === "{CODE}" || token === "{code}") return codeTokenToRegex(code);
      if (!token) return "";
      return literalToRegex(token);
    });

    const body = parts.join("").replace(/\s+/g, "");
    if (!body) return null;
    return new RegExp(`^${body}$`);
  }

  function matchesPattern(text, pattern, code) {
    const regex = patternToRegex(pattern, code);
    if (!regex) return false;
    const normalized = String(text || "").replace(/\s+/g, "");
    return regex.test(normalized);
  }

  const FOUR_K_PATTERNS = [
    /\[4k\]/i,
    /(?:^|[^a-z0-9])4k(?:[^a-z0-9]|$)/i,
    /\b2160p\b/i,
    /\buhd\b/i,
  ];

  function is4kMagnetName(display) {
    const text = String(display || "").trim();
    if (!text) return false;
    return FOUR_K_PATTERNS.some((pattern) => pattern.test(text));
  }

  window.JM_magnetPatternMatch = {
    splitNormalizedCode,
    normalizeCode,
    matchesPattern,
    patternToRegex,
    is4kMagnetName,
    FOUR_K_PATTERNS,
  };
})();
