/**
 * 18mag / JavDB 磁链三阶段筛查与 TXT 生成（Service Worker，无 DOMParser）
 *
 * 1. 4K 磁链筛查：JavDB 磁链区 → 18mag
 * 2. 字幕磁链筛查（优先级 1–4）：18mag → JavDB
 * 3. 高清磁链筛查（优先级 5–8）：18mag → JavDB
 */
(function (root) {
  "use strict";

  const MAGNET_ORIGIN = "https://18mag.net";
  const RULES_STORAGE_KEY = "magnetFilterRules";
  const PREVIEW_KEYWORDS = "keywords";
  const PREVIEW_SINGLE_MP4 = "single_mp4";
  const SUBTITLE_PRIORITY_MAX = 4;
  const HD_PRIORITY_MIN = 5;
  const DEFAULT_TXT_STAGES = ["4k", "subtitle", "hd"];

  const FETCH_HEADERS = {
    "User-Agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    Accept: "text/html,application/xhtml+xml",
  };

  const RULES_NOT_CONFIGURED_MSG =
    "未检测到有效的磁链筛选规则。请确认：① 桌面 JAV Manager 已运行且扩展已配对；② 在「磁链筛选规则」中勾选启用优先级 1–4 或 5–8 至少一条；③ 点击「保存并同步到扩展」后重试。";

  const matchApi = () => root.JM_magnetPatternMatch;
  const keywordApi = () => root.JM_magnetKeywordMatch;

  function normalizeCode(code) {
    const api = matchApi();
    if (api) return api.normalizeCode(code);
    return String(code || "").toUpperCase().trim();
  }

  function matchesPattern(text, pattern, code) {
    const api = matchApi();
    if (!api) return false;
    return api.matchesPattern(text, pattern, code);
  }

  function is4kMagnetName(display) {
    const api = matchApi();
    if (api?.is4kMagnetName) return api.is4kMagnetName(display);
    return false;
  }

  function decodeHtmlAttr(value) {
    return String(value || "")
      .replace(/&amp;/g, "&")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .trim();
  }

  function sanitizeActressName(name) {
    return String(name || "未知")
      .replace(/[<>:"/\\|?*\x00-\x1f]/g, "")
      .trim() || "未知";
  }

  async function fetchHtml(url) {
    const resp = await fetch(url, { credentials: "omit", headers: FETCH_HEADERS });
    if (!resp.ok) throw new Error(`页面请求失败 (${resp.status})`);
    return resp.text();
  }

  function parseSearchResults(html) {
    const results = [];
    const linkRegex = /<a href="(\/![^"]+)">([\s\S]*?)<\/a>/gi;
    let match;
    while ((match = linkRegex.exec(html)) !== null) {
      let block = match[2];
      block = block.split(/<p class="sample"/i)[0];
      let title = block.replace(/<[^>]+>/g, " ");
      title = title.replace(/\s+/g, " ").trim();
      if (!title) continue;
      results.push({ title, path: match[1] });
    }
    return results;
  }

  function parse18magDetailPage(html) {
    const files = [];
    const fileTableMatch = html.match(
      /<table class="table table-hover file-list">[\s\S]*?<\/table>/i
    );
    if (fileTableMatch && /文件/.test(fileTableMatch[0])) {
      const rowRegex = /<tr><td>\s*([\s\S]*?)\s*<\/td><td/gi;
      let row;
      while ((row = rowRegex.exec(fileTableMatch[0])) !== null) {
        const name = row[1].replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
        if (name && !/^文件\s*\(/i.test(name)) files.push(name);
      }
    }

    let actress = "";
    const actressMatch = html.match(/<dt>\s*演员\s*:?\s*<\/dt>\s*<dd>[\s\S]*?<a[^>]*>([^<]+)</i);
    if (actressMatch) actress = actressMatch[1].trim();

    let magnet = "";
    const inputMatch = html.match(/id="input-magnet"[^>]*value="([^"]+)"/i);
    if (inputMatch) magnet = decodeHtmlAttr(inputMatch[1]);
    if (!magnet) {
      const hrefMatch = html.match(/class="magnet-box"[\s\S]*?href="(magnet:\?[^"]+)"/i);
      if (hrefMatch) magnet = decodeHtmlAttr(hrefMatch[1]);
    }

    const titleMatch = html.match(/class="magnet-title"[^>]*>([^<]+)</i);
    const pageTitle = titleMatch ? titleMatch[1].trim() : "";

    return { files, actress, magnet, pageTitle };
  }

  function parseJavdbMagnetsFromHtml(html) {
    const magnets = [];
    const chunks = html.split(/<div class="item columns/gi).slice(1);
    for (const chunk of chunks) {
      const block = `<div class="item columns${chunk}`;
      const nameMatch = block.match(/class="name"[^>]*>([\s\S]*?)<\//i);
      const title = nameMatch
        ? nameMatch[1].replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()
        : "";
      const magnetMatch =
        block.match(/data-clipboard-text="(magnet:[^"]+)"/i) ||
        block.match(/href="(magnet:[^"]+)"/i);
      const magnet = magnetMatch ? decodeHtmlAttr(magnetMatch[1]) : "";
      if (title && magnet.startsWith("magnet:?")) {
        magnets.push({ title, preview: "", magnet });
      }
    }
    return magnets;
  }

  function parseJavdbActressFromHtml(html) {
    const patterns = [
      /<a[^>]+href="[^"]*\/(?:actors|stars)\/[^"]+"[^>]*>([^<]+)</i,
      /演员[\s\S]{0,120}?<a[^>]*>([^<]+)</i,
    ];
    for (const pattern of patterns) {
      const match = html.match(pattern);
      if (match?.[1]) return match[1].trim();
    }
    return "";
  }

  function isRuleEnabled(rule) {
    const v = rule?.enabled;
    return v === true || v === 1 || v === "true" || v === "1";
  }

  function isUsableEnabledRule(rule) {
    if (!isRuleEnabled(rule)) return false;
    if (!String(rule.name_pattern || "").trim()) return false;
    const mode = rule.preview_mode === PREVIEW_SINGLE_MP4 ? PREVIEW_SINGLE_MP4 : PREVIEW_KEYWORDS;
    if (mode === PREVIEW_SINGLE_MP4) return true;
    const keywords = Array.isArray(rule.preview_keywords) ? rule.preview_keywords : [];
    return keywords.some((k) => String(k || "").trim());
  }

  function getEnabledRules(rulesConfig, minPriority = 1, maxPriority = 8) {
    return (rulesConfig?.priorities || [])
      .filter((rule) => isUsableEnabledRule(rule))
      .filter((rule) => {
        const p = Number(rule.priority);
        return p >= minPriority && p <= maxPriority;
      })
      .sort((a, b) => Number(a.priority) - Number(b.priority));
  }

  function hasEnabledUsableRules(rulesConfig, minPriority = 1, maxPriority = 8) {
    return getEnabledRules(rulesConfig, minPriority, maxPriority).length > 0;
  }

  function assertRulesConfigured(rulesConfig) {
    const subtitle = hasEnabledUsableRules(rulesConfig, 1, SUBTITLE_PRIORITY_MAX);
    const hd = hasEnabledUsableRules(rulesConfig, HD_PRIORITY_MIN, 8);
    if (!subtitle && !hd) {
      throw new Error(RULES_NOT_CONFIGURED_MSG);
    }
  }

  function normalizeTxtScreenStages(raw) {
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

  function normalizeRulesConfig(raw) {
    if (!raw || typeof raw !== "object") return null;
    const priorities = Array.isArray(raw.priorities) ? raw.priorities : [];
    return {
      version: raw.version || 1,
      reject_keywords: Array.isArray(raw.reject_keywords) ? raw.reject_keywords : [],
      display_hide_keywords: Array.isArray(raw.display_hide_keywords) ? raw.display_hide_keywords : [],
      display_highlight_rules: Array.isArray(raw.display_highlight_rules)
        ? raw.display_highlight_rules
        : [],
      priorities,
      txt_screen_stages: normalizeTxtScreenStages(raw.txt_screen_stages),
    };
  }

  async function loadFilterRules(getRulesFromDesktop) {
    if (typeof getRulesFromDesktop === "function") {
      const remote = normalizeRulesConfig(await getRulesFromDesktop());
      if (remote) {
        await chrome.storage.local.set({ [RULES_STORAGE_KEY]: remote });
        assertRulesConfigured(remote);
        return remote;
      }
    }

    const stored = await chrome.storage.local.get(RULES_STORAGE_KEY);
    const config = normalizeRulesConfig(stored[RULES_STORAGE_KEY]);
    assertRulesConfigured(config);
    return config;
  }

  function buildTxtFilename(code, actress, suffix) {
    const codePart = normalizeCode(code);
    const actressPart = sanitizeActressName(actress);
    const tail = String(suffix || "").trim();
    return `${codePart}${actressPart}${tail}.txt`;
  }

  function hasRejectKeywords(files, rejectKeywords, extraText = "", previewKeywords = null) {
    const kw = keywordApi();
    if (!kw) {
      const list = Array.isArray(rejectKeywords) ? rejectKeywords : [];
      if (!list.length) return false;
      return files.some((name) => list.some((keyword) => keyword && name.includes(keyword)));
    }
    return kw.shouldRejectMagnetContent({
      title: extraText,
      preview: "",
      files,
      keywords: rejectKeywords,
      previewKeywords,
    });
  }

  function shouldRejectEntry(title, preview, rejectKeywords, previewKeywords = null) {
    const kw = keywordApi();
    if (!kw) return false;
    return kw.shouldRejectMagnetContent({
      title,
      preview,
      files: previewSources({ preview }),
      keywords: rejectKeywords,
      previewKeywords,
    });
  }

  function previewSources(entry) {
    return String(entry.preview || "")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
  }

  function matchPreviewContent(files, rule) {
    const mode = rule.preview_mode === PREVIEW_SINGLE_MP4 ? PREVIEW_SINGLE_MP4 : PREVIEW_KEYWORDS;

    if (mode === PREVIEW_SINGLE_MP4) {
      if (files.length !== 1) return false;
      return /\.mp4$/i.test(String(files[0] || "").trim());
    }

    const kw = keywordApi();
    if (kw?.matchPreviewKeywordContent) {
      return kw.matchPreviewKeywordContent(files, rule.preview_keywords);
    }

    const keywords = Array.isArray(rule.preview_keywords) ? rule.preview_keywords : [];
    const activeKeywords = keywords.map((k) => String(k || "").trim()).filter(Boolean);
    if (!activeKeywords.length || !files.length) return false;
    const normalize = (text) => String(text || "").replace(/\s+/g, "");
    return files.some((file) => {
      const text = normalize(file);
      if (!text) return false;
      return activeKeywords.every((keyword) => {
        const needle = normalize(keyword);
        return needle && text.includes(needle);
      });
    });
  }

  function titleMatchesCode(title, code) {
    const normalized = normalizeCode(code);
    const compact = normalized.replace(/-/g, "");
    const text = String(title || "").replace(/\s+/g, "").toUpperCase();
    return text.includes(normalized) || text.includes(compact);
  }

  function normalizeJavdbMagnets(raw) {
    if (!Array.isArray(raw)) return [];
    return raw
      .map((row) => ({
        title: String(row?.title || "").replace(/\s+/g, " ").trim(),
        preview: String(row?.preview || "").trim(),
        magnet: String(row?.magnet || row?.magnetUri || "").trim(),
      }))
      .filter((row) => row.title && row.magnet.startsWith("magnet:?"));
  }

  async function resolveJavdbContext(detailUrl, javdbMagnets, actressHint) {
    let magnets = normalizeJavdbMagnets(javdbMagnets);
    let actress = sanitizeActressName(actressHint);

    if ((!magnets.length || actress === "未知") && detailUrl) {
      try {
        const html = await fetchHtml(detailUrl);
        if (!magnets.length) magnets = parseJavdbMagnetsFromHtml(html);
        if (actress === "未知") {
          const parsedActress = parseJavdbActressFromHtml(html);
          if (parsedActress) actress = sanitizeActressName(parsedActress);
        }
      } catch (_) {
        /* optional fallback */
      }
    }

    return { magnets, actress };
  }

  function detailToolsApi() {
    return root.JM_detailTools;
  }

  async function fetch18magRows(code, maxResults = 30) {
    const api = detailToolsApi();
    if (!api?.search18mag) return [];
    return api.search18mag(code, { maxResults });
  }

  function previewFilesFromRow(row) {
    return String(row?.preview || "")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
  }

  function rulePreviewKeywords(rule) {
    return rule.preview_mode === PREVIEW_KEYWORDS ? rule.preview_keywords : null;
  }

  function listTitleFromRow(row) {
    return String(row?.listTitle || row?.title || "").trim();
  }

  function tryPick18magRow(row, code, rule, rulesConfig) {
    const normalized = normalizeCode(code);
    const listTitle = listTitleFromRow(row);
    if (!matchesPattern(listTitle, rule.name_pattern, normalized)) return null;
    const previewFiles = previewFilesFromRow(row);
    if (
      shouldRejectEntry(
        listTitle,
        row.preview,
        rulesConfig.reject_keywords,
        rulePreviewKeywords(rule)
      )
    ) {
      return null;
    }
    if (!matchPreviewContent(previewFiles, rule)) return null;
    if (!String(row.magnet || "").startsWith("magnet:?")) return null;
    return {
      ok: true,
      magnet: row.magnet,
      actress: "",
      priority: rule.priority,
      source: "18mag",
      sourceTitle: listTitle,
    };
  }

  function pick4kFromJavdb(javdbMagnets, rulesConfig) {
    for (const entry of javdbMagnets) {
      if (!is4kMagnetName(entry.title)) continue;
      if (shouldRejectEntry(entry.title, entry.preview, rulesConfig.reject_keywords)) continue;
      if (!entry.magnet.startsWith("magnet:?")) continue;
      return {
        ok: true,
        magnet: entry.magnet,
        source: "javdb",
        sourceTitle: entry.title,
      };
    }
    return { ok: false };
  }

  async function pick4kFrom18mag(code, rulesConfig) {
    const normalized = normalizeCode(code);
    const rows = await fetch18magRows(normalized);
    for (const row of rows) {
      const listTitle = listTitleFromRow(row);
      const previewFiles = previewFilesFromRow(row);
      const titleHit = is4kMagnetName(listTitle) && titleMatchesCode(listTitle, normalized);
      const fileHit = previewFiles.some(
        (name) => is4kMagnetName(name) && titleMatchesCode(name, normalized)
      );
      if (!titleHit && !fileHit) continue;
      if (shouldRejectEntry(listTitle, row.preview, rulesConfig.reject_keywords)) continue;
      if (!String(row.magnet || "").startsWith("magnet:?")) continue;
      return {
        ok: true,
        magnet: row.magnet,
        actress: "",
        source: "18mag",
        sourceTitle: listTitle,
      };
    }

    return { ok: false };
  }

  async function screen4kMagnets({ code, javdbMagnets, rulesConfig }) {
    const fromJavdb = pick4kFromJavdb(javdbMagnets, rulesConfig);
    if (fromJavdb.ok) return fromJavdb;
    return pick4kFrom18mag(code, rulesConfig);
  }

  function pickFromJavdbByPriorities(javdbMagnets, code, rulesConfig, minPriority, maxPriority) {
    const enabledRules = getEnabledRules(rulesConfig, minPriority, maxPriority);
    for (const rule of enabledRules) {
      for (const entry of javdbMagnets) {
        if (!matchesPattern(entry.title, rule.name_pattern, code)) continue;
        if (
          shouldRejectEntry(
            entry.title,
            entry.preview,
            rulesConfig.reject_keywords,
            rule.preview_mode === PREVIEW_KEYWORDS ? rule.preview_keywords : null
          )
        )
          continue;
        if (!matchPreviewContent(previewSources(entry), rule)) continue;
        if (!entry.magnet.startsWith("magnet:?")) continue;
        return {
          ok: true,
          magnet: entry.magnet,
          priority: rule.priority,
          source: "javdb",
          sourceTitle: entry.title,
        };
      }
    }
    return { ok: false };
  }

  async function pickFrom18magByPriorities(code, rulesConfig, minPriority, maxPriority) {
    const normalized = normalizeCode(code);
    const enabledRules = getEnabledRules(rulesConfig, minPriority, maxPriority);
    if (!enabledRules.length) return { ok: false };

    const rows = await fetch18magRows(normalized);
    if (!rows.length) return { ok: false };

    for (const rule of enabledRules) {
      for (const row of rows) {
        const picked = tryPick18magRow(row, normalized, rule, rulesConfig);
        if (picked) return picked;
      }
    }

    return { ok: false };
  }

  async function screenByPriorities({ code, javdbMagnets, rulesConfig, minPriority, maxPriority }) {
    const from18mag = await pickFrom18magByPriorities(code, rulesConfig, minPriority, maxPriority);
    if (from18mag.ok) return from18mag;
    return pickFromJavdbByPriorities(javdbMagnets, code, rulesConfig, minPriority, maxPriority);
  }

  async function screenMagnetAllStages({
    code,
    detailUrl = "",
    javdbMagnets = null,
    actressHint = "",
    rulesConfig,
  }) {
    const normalized = normalizeCode(code);
    if (!normalized) throw new Error("未能识别番号");

    const context = await resolveJavdbContext(detailUrl, javdbMagnets, actressHint);
    const magnets = context.magnets;
    const actress = context.actress;

    const fourK = await screen4kMagnets({ code: normalized, javdbMagnets: magnets, rulesConfig });
    let subtitle = { ok: false };
    if (hasEnabledUsableRules(rulesConfig, 1, SUBTITLE_PRIORITY_MAX)) {
      subtitle = await screenByPriorities({
        code: normalized,
        javdbMagnets: magnets,
        rulesConfig,
        minPriority: 1,
        maxPriority: SUBTITLE_PRIORITY_MAX,
      });
    }
    let hd = { ok: false };
    if (hasEnabledUsableRules(rulesConfig, HD_PRIORITY_MIN, 8)) {
      hd = await screenByPriorities({
        code: normalized,
        javdbMagnets: magnets,
        rulesConfig,
        minPriority: HD_PRIORITY_MIN,
        maxPriority: 8,
      });
    }

    return { normalized, actress, fourK, subtitle, hd };
  }

  function buildBatchSummaryText(summary) {
    const lines = [];
    lines.push("4K资源：");
    for (const code of summary?.fourK || []) lines.push(code);
    lines.push("");
    lines.push("字幕资源：");
    for (const code of summary?.subtitle || []) lines.push(code);
    lines.push("");
    lines.push("高清资源：");
    for (const code of summary?.hd || []) lines.push(code);
    lines.push("");
    lines.push("无合适资源：");
    for (const code of summary?.none || []) lines.push(code);
    return `${lines.join("\n").trim()}\n`;
  }

  async function runTxtScreenStage(stage, { normalized, magnets, rulesConfig }) {
    if (stage === "4k") {
      return screen4kMagnets({ code: normalized, javdbMagnets: magnets, rulesConfig });
    }
    if (stage === "subtitle") {
      if (!hasEnabledUsableRules(rulesConfig, 1, SUBTITLE_PRIORITY_MAX)) {
        return { ok: false };
      }
      return screenByPriorities({
        code: normalized,
        javdbMagnets: magnets,
        rulesConfig,
        minPriority: 1,
        maxPriority: SUBTITLE_PRIORITY_MAX,
      });
    }
    if (stage === "hd") {
      if (!hasEnabledUsableRules(rulesConfig, HD_PRIORITY_MIN, 8)) {
        return { ok: false };
      }
      return screenByPriorities({
        code: normalized,
        javdbMagnets: magnets,
        rulesConfig,
        minPriority: HD_PRIORITY_MIN,
        maxPriority: 8,
      });
    }
    return { ok: false };
  }

  function buildTxtStageResult(stage, picked, normalized, actress) {
    if (stage === "4k") {
      return {
        ok: true,
        empty: false,
        stage: "4k",
        stageLabel: "4K磁链筛查",
        filename: buildTxtFilename(normalized, picked.actress || actress, "4k待匹配字幕"),
        magnet: picked.magnet,
        actress: picked.actress || actress,
        source: picked.source,
        sourceTitle: picked.sourceTitle || "",
      };
    }
    if (stage === "subtitle") {
      return {
        ok: true,
        empty: false,
        stage: "subtitle",
        stageLabel: "字幕磁链筛查",
        filename: buildTxtFilename(normalized, picked.actress || actress, "C"),
        magnet: picked.magnet,
        actress: picked.actress || actress,
        priority: picked.priority,
        source: picked.source,
        sourceTitle: picked.sourceTitle || "",
      };
    }
    return {
      ok: true,
      empty: false,
      stage: "hd",
      stageLabel: "高清磁链筛查",
      filename: buildTxtFilename(normalized, picked.actress || actress, "待匹配字幕"),
      magnet: picked.magnet,
      actress: picked.actress || actress,
      priority: picked.priority,
      source: picked.source,
      sourceTitle: picked.sourceTitle || "",
    };
  }

  async function pickMagnetForTxt({
    code,
    detailUrl = "",
    javdbMagnets = null,
    actressHint = "",
    rulesConfig,
  }) {
    const normalized = normalizeCode(code);
    if (!normalized) throw new Error("未能识别番号");
    assertRulesConfigured(rulesConfig);

    const context = await resolveJavdbContext(detailUrl, javdbMagnets, actressHint);
    const actress = context.actress;
    const magnets = context.magnets;
    const stages = normalizeTxtScreenStages(rulesConfig.txt_screen_stages);

    for (const stage of stages) {
      const picked = await runTxtScreenStage(stage, { normalized, magnets, rulesConfig });
      if (picked.ok) {
        return buildTxtStageResult(stage, picked, normalized, actress);
      }
    }

    return {
      ok: true,
      empty: true,
      stage: "none",
      stageLabel: "无合适资源",
      filename: buildTxtFilename(normalized, actress, "无合适资源"),
      magnet: "",
      actress,
    };
  }

  /** @deprecated 保留旧接口，内部走高清阶段逻辑 */
  async function pickMagnetFrom18mag(code, rulesConfig) {
    const picked = await pickFrom18magByPriorities(code, rulesConfig, HD_PRIORITY_MIN, 8);
    if (!picked.ok) {
      throw new Error("18mag 中未找到符合优先级 5–8 的磁链。");
    }
    return {
      ok: true,
      filename: buildTxtFilename(code, picked.actress, "待匹配字幕"),
      magnet: picked.magnet,
      actress: picked.actress,
      priority: picked.priority,
      sourceTitle: picked.sourceTitle,
    };
  }

  root.JM_magnetTxtCore = {
    RULES_STORAGE_KEY,
    RULES_NOT_CONFIGURED_MSG,
    SUBTITLE_PRIORITY_MAX,
    HD_PRIORITY_MIN,
    loadFilterRules,
    pickMagnetForTxt,
    pickMagnetFrom18mag,
    screenMagnetAllStages,
    buildBatchSummaryText,
    buildTxtFilename,
    normalizeCode,
    hasEnabledUsableRules,
    parseJavdbMagnetsFromHtml,
    parseJavdbActressFromHtml,
  };
})(typeof globalThis !== "undefined" ? globalThis : self);
