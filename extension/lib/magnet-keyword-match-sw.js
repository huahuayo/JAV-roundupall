/**
 * 磁链关键词匹配：分号分隔、忽略空格差异（斗 鱼 = 斗鱼）、连续子串匹配。
 */
(function (root) {
  "use strict";

  function splitSemicolonKeywords(text) {
    return String(text || "")
      .split(";")
      .map((part) => part.trim())
      .filter(Boolean);
  }

  function normalizeKeywordMatchText(text) {
    return String(text || "").replace(/\s+/g, "");
  }

  function textContainsKeyword(text, keyword) {
    const needle = normalizeKeywordMatchText(keyword);
    if (!needle) return false;
    return normalizeKeywordMatchText(text).includes(needle);
  }

  function textContainsAnyKeyword(text, keywords) {
    const list = Array.isArray(keywords) ? keywords : splitSemicolonKeywords(keywords);
    return list.some((keyword) => keyword && textContainsKeyword(text, keyword));
  }

  function allKeywordsInText(text, keywords) {
    const list = Array.isArray(keywords) ? keywords : splitSemicolonKeywords(keywords);
    const active = list.map((keyword) => String(keyword || "").trim()).filter(Boolean);
    if (!active.length) return false;
    return active.every((keyword) => textContainsKeyword(text, keyword));
  }

  function buildMagnetSearchText(title, preview, files) {
    const parts = [String(title || ""), String(preview || "")];
    if (Array.isArray(files)) {
      for (const name of files) {
        const line = String(name || "").trim();
        if (line) parts.push(line);
      }
    }
    return parts.join("\n");
  }

  function getKeywordQualifiedFiles(files, keywords) {
    const list = Array.isArray(files) ? files : [];
    const active = (Array.isArray(keywords) ? keywords : splitSemicolonKeywords(keywords))
      .map((keyword) => String(keyword || "").trim())
      .filter(Boolean);
    if (!active.length) return list;
    return list.filter((file) => active.every((keyword) => textContainsKeyword(file, keyword)));
  }

  function shouldRejectMagnetContent({
    title = "",
    preview = "",
    files = null,
    keywords = [],
    previewKeywords = null,
  } = {}) {
    if (!keywords?.length) return false;
    if (textContainsAnyKeyword(title, keywords)) return true;

    const fileList = Array.isArray(files) ? files : [];
    const previewLines = String(preview || "")
      .split("\n")
      .map((line) => line.trim())
      .filter(Boolean);
    const allFiles = fileList.length ? fileList : previewLines;
    if (!allFiles.length) return false;

    const qualified = previewKeywords ? getKeywordQualifiedFiles(allFiles, previewKeywords) : [];
    const filesToCheck = qualified.length ? qualified : allFiles;
    return filesToCheck.some((file) => textContainsAnyKeyword(file, keywords));
  }

  function matchPreviewKeywordContent(files, keywords) {
    const list = Array.isArray(files) ? files : [];
    const active = (Array.isArray(keywords) ? keywords : splitSemicolonKeywords(keywords))
      .map((keyword) => String(keyword || "").trim())
      .filter(Boolean);
    if (!active.length || !list.length) return false;
    return list.some((file) => {
      const text = String(file || "").trim();
      if (!text) return false;
      return active.every((keyword) => textContainsKeyword(text, keyword));
    });
  }

  root.JM_magnetKeywordMatch = {
    splitSemicolonKeywords,
    normalizeKeywordMatchText,
    textContainsKeyword,
    textContainsAnyKeyword,
    allKeywordsInText,
    buildMagnetSearchText,
    getKeywordQualifiedFiles,
    shouldRejectMagnetContent,
    matchPreviewKeywordContent,
  };
})(typeof globalThis !== "undefined" ? globalThis : self);
