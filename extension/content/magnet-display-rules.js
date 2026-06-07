/**

 * 磁链列表显示规则（隐藏 / 着色 / 排序），配置来自桌面端 magnet_filter_rules.json

 */

(function () {

  "use strict";



  const STORAGE_KEY = "magnetFilterRules";

  const PREVIEW_KEYWORDS = "keywords";

  const PREVIEW_SINGLE_MP4 = "single_mp4";

  const DEFAULT_TXT_STAGES = ["4k", "subtitle", "hd"];

  const kwApi = () => window.JM_magnetKeywordMatch;

  const patternApi = () => window.JM_magnetPatternMatch;



  function splitSemicolonKeywords(text) {

    const api = kwApi();

    if (api?.splitSemicolonKeywords) return api.splitSemicolonKeywords(text);

    return String(text || "")

      .split(";")

      .map((part) => part.trim())

      .filter(Boolean);

  }



  function normalizeKeywordList(raw) {

    if (Array.isArray(raw)) {

      return raw.map((k) => String(k || "").trim()).filter(Boolean);

    }

    return splitSemicolonKeywords(raw);

  }



  function normalizeHighlightColor(color) {

    let text = String(color || "#dc2626").trim() || "#dc2626";

    if (!text.startsWith("#")) text = `#${text}`;

    const hex = text.slice(1);

    if (/^[0-9a-fA-F]{3}$/.test(hex)) {

      return `#${hex[0]}${hex[0]}${hex[1]}${hex[1]}${hex[2]}${hex[2]}`.toLowerCase();

    }

    if (/^[0-9a-fA-F]{4}$/.test(hex)) {

      return `#${hex}${hex.slice(0, 2)}`.toLowerCase();

    }

    if (/^[0-9a-fA-F]{6}$/.test(hex)) {

      return `#${hex}`.toLowerCase();

    }

    return "#dc2626";

  }



  function normalizeHighlightRules(raw) {

    if (!Array.isArray(raw)) return [];

    return raw

      .map((rule, index) => {

        if (!rule || typeof rule !== "object") return null;

        let keywords = rule.keywords;

        if (typeof keywords === "string") {

          keywords = keywords

            .split(",")

            .map((k) => k.trim())

            .filter(Boolean);

        }

        if (!Array.isArray(keywords)) keywords = [];

        keywords = keywords.map((k) => String(k || "").trim()).filter(Boolean);

        return {

          id: rule.id || index + 1,

          enabled: rule.enabled !== false,

          keywords,

          color: normalizeHighlightColor(rule.color),

        };

      })

      .filter(Boolean);

  }



  function normalizePriorities(raw) {

    if (!Array.isArray(raw)) return [];

    return raw.map((rule) => ({

      priority: Number(rule?.priority) || 0,

      enabled: rule?.enabled === true || rule?.enabled === 1 || rule?.enabled === "1",

      name_pattern: String(rule?.name_pattern || "").trim(),

      preview_mode:

        rule?.preview_mode === PREVIEW_SINGLE_MP4 ? PREVIEW_SINGLE_MP4 : PREVIEW_KEYWORDS,

      preview_keywords: Array.isArray(rule?.preview_keywords)

        ? rule.preview_keywords.map((k) => String(k || "").trim()).filter(Boolean)

        : [],

    }));

  }



  function normalizeTxtStages(raw) {

    if (!Array.isArray(raw)) return DEFAULT_TXT_STAGES.slice();

    const ordered = [];

    const seen = new Set();

    for (const item of raw) {

      const stage = String(item || "").trim().toLowerCase();

      if ((stage === "4k" || stage === "subtitle" || stage === "hd") && !seen.has(stage)) {

        seen.add(stage);

        ordered.push(stage);

      }

    }

    for (const stage of DEFAULT_TXT_STAGES) {

      if (!seen.has(stage)) ordered.push(stage);

    }

    return ordered;

  }



  function normalizeRules(raw) {

    if (!raw || typeof raw !== "object") {

      return {

        reject_keywords: [],

        display_hide_keywords: [],

        display_highlight_rules: [],

        priorities: [],

        txt_screen_stages: DEFAULT_TXT_STAGES.slice(),

      };

    }

    return {

      reject_keywords: normalizeKeywordList(raw.reject_keywords),

      display_hide_keywords: normalizeKeywordList(raw.display_hide_keywords),

      display_highlight_rules: normalizeHighlightRules(raw.display_highlight_rules),

      priorities: normalizePriorities(raw.priorities),

      txt_screen_stages: normalizeTxtStages(raw.txt_screen_stages),

    };

  }



  async function loadMagnetDisplayRules() {

    try {

      const stored = await chrome.storage.local.get(STORAGE_KEY);

      return normalizeRules(stored[STORAGE_KEY]);

    } catch (_) {

      return normalizeRules(null);

    }

  }



  function getCombinedHideKeywords(rules) {

    const merged = new Set();

    for (const kw of rules?.display_hide_keywords || []) {

      if (kw) merged.add(String(kw));

    }

    for (const kw of rules?.reject_keywords || []) {

      if (kw) merged.add(String(kw));

    }

    return Array.from(merged);

  }



  function previewFilesFromText(preview) {

    return String(preview || "")

      .split("\n")

      .map((line) => line.trim())

      .filter(Boolean);

  }



  function buildEntrySearchText(title, preview) {

    const api = kwApi();

    const previewFiles = previewFilesFromText(preview);

    if (api?.buildMagnetSearchText) {

      return api.buildMagnetSearchText(title, preview, previewFiles);

    }

    return `${String(title || "")}\n${String(preview || "")}`;

  }



  function shouldHideMagnetEntry(title, preview, rules) {

    const text = buildEntrySearchText(title, preview);

    if (!text.trim()) return false;

    const keywords = getCombinedHideKeywords(rules);

    const api = kwApi();

    if (api?.textContainsAnyKeyword) {

      return api.textContainsAnyKeyword(text, keywords);

    }

    return keywords.some((kw) => kw && text.includes(kw));

  }



  function getMagnetHighlightStyle(title, preview, rules) {

    const text = buildEntrySearchText(title, preview);

    const api = kwApi();

    for (const rule of rules?.display_highlight_rules || []) {

      if (!rule.enabled) continue;

      for (const kw of rule.keywords || []) {

        if (!kw) continue;

        if (api?.textContainsKeyword ? api.textContainsKeyword(text, kw) : text.includes(kw)) {

          return { color: normalizeHighlightColor(rule.color), fontWeight: "700" };

        }

      }

    }

    return null;

  }



  function parseSizeBytes(sizeStr) {

    const match = String(sizeStr || "")

      .trim()

      .match(/([\d.]+)\s*(TB|GB|MB|KB|T|G|M|K)?B?/i);

    if (!match) return 0;

    const value = Number(match[1]);

    if (!Number.isFinite(value) || value <= 0) return 0;

    const unit = String(match[2] || "B").toUpperCase();

    const multipliers = { T: 1e12, G: 1e9, M: 1e6, K: 1e3, B: 1 };

    return value * (multipliers[unit[0]] || 1);

  }



  function extractSizeFromText(text) {

    const match = String(text || "").match(/(\d+(?:\.\d+)?\s*(?:TB|GB|MB|KB))/i);

    return match ? match[1].replace(/\s+/g, "") : "";

  }



  function isUsablePriorityRule(rule) {

    if (!rule?.enabled) return false;

    if (!String(rule.name_pattern || "").trim()) return false;

    if (rule.preview_mode === PREVIEW_SINGLE_MP4) return true;

    return (rule.preview_keywords || []).some((k) => String(k || "").trim());

  }



  function matchPreviewContent(files, rule) {

    const mode = rule.preview_mode === PREVIEW_SINGLE_MP4 ? PREVIEW_SINGLE_MP4 : PREVIEW_KEYWORDS;

    if (mode === PREVIEW_SINGLE_MP4) {

      if (files.length !== 1) return false;

      return /\.mp4$/i.test(String(files[0] || "").trim());

    }

    const keywords = rule.preview_keywords || [];

    if (!keywords.length) return false;

    const api = kwApi();

    if (api?.matchPreviewKeywordContent) {

      return api.matchPreviewKeywordContent(files, keywords);

    }

    const normalize = (text) => String(text || "").replace(/\s+/g, "");

    return files.some((file) => {

      const text = normalize(file);

      if (!text) return false;

      return keywords.every((kw) => {

        const needle = normalize(kw);

        return needle && text.includes(needle);

      });

    });

  }



  function rowTitleForMatch(row) {

    return String(row?.listTitle || row?.title || "").trim();

  }



  function isRow4k(row) {

    const is4k = patternApi()?.is4kMagnetName;

    if (!is4k) return false;

    if (is4k(rowTitleForMatch(row))) return true;

    return previewFilesFromText(row?.preview).some((name) => is4k(name));

  }



  function getPriorityMatch(row, code, rules) {

    const pm = patternApi();

    if (!pm?.matchesPattern) return null;

    const title = rowTitleForMatch(row);

    const files = previewFilesFromText(row?.preview);

    const priorities = (rules?.priorities || [])

      .filter(isUsablePriorityRule)

      .sort((a, b) => Number(a.priority) - Number(b.priority));

    for (const rule of priorities) {

      if (!pm.matchesPattern(title, rule.name_pattern, code)) continue;

      if (!matchPreviewContent(files, rule)) continue;

      return Number(rule.priority);

    }

    return null;

  }



  function compareMagnetRows(a, b, code, rules) {

    const a4k = isRow4k(a) ? 0 : 1;

    const b4k = isRow4k(b) ? 0 : 1;

    if (a4k !== b4k) return a4k - b4k;



    const ap = getPriorityMatch(a, code, rules) ?? 999;

    const bp = getPriorityMatch(b, code, rules) ?? 999;

    if (ap !== bp) return ap - bp;



    const aSize = parseSizeBytes(a.size || extractSizeFromText(a.metaText || ""));

    const bSize = parseSizeBytes(b.size || extractSizeFromText(b.metaText || ""));

    return bSize - aSize;

  }



  function sortMagnetRows(rows, code, rules) {

    return [...(rows || [])].sort((a, b) => compareMagnetRows(a, b, code, rules));

  }



  function filterMagnetRows(rows, rules) {

    return (rows || []).filter((row) => {

      const title = rowTitleForMatch(row);

      const preview = row.preview || row.magnet || "";

      return !shouldHideMagnetEntry(title, preview, rules);

    });

  }



  function sortNativeMagnetElements(root, code, rules) {

    if (!root) return;

    const selector = ".item.columns.is-desktop, .item.columns, #magnets-content > .item";

    const rowEls = Array.from(root.querySelectorAll(selector));

    if (rowEls.length < 2) return;



    const wrapped = rowEls.map((el) => {

      const nameEl = el.querySelector(".magnet-name .name, .name");

      const title = nameEl?.textContent?.replace(/\s+/g, " ").trim() || "";

      const previewEl = el.querySelector(".jm-magnet-file-preview");

      const preview = previewEl?.textContent || "";

      const size = extractSizeFromText(el.textContent || "");

      return {

        el,

        row: { title, listTitle: title, preview, size, metaText: el.textContent || "" },

      };

    });



    wrapped.sort((a, b) => compareMagnetRows(a.row, b.row, code, rules));

    for (const item of wrapped) {

      root.appendChild(item.el);

    }

  }



  window.JM_magnetDisplayRules = {

    loadMagnetDisplayRules,

    shouldHideMagnetEntry,

    getMagnetHighlightStyle,

    filterMagnetRows,

    sortMagnetRows,

    sortNativeMagnetElements,

    normalizeRules,

  };

})();


