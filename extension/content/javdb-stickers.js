/**
 * JavDB 列表页：预览贴纸操作按钮（屏蔽 / 已鉴定 / 已下载 / 标记等）
 */

(function () {
  "use strict";

  if (window.__JM_JAVDB_STICKERS__) return;
  window.__JM_JAVDB_STICKERS__ = true;

  const DATA_KEY = "javdbStickerData";
  const SETTINGS_KEY = "javdbStickerSettings";
  const SHORTCUTS_KEY = "javdbStickerShortcuts";
  const DEFAULT_SETTINGS = {
    showBlocked: false,
    showVerified: false,
    showDownloaded: false,
    showBlockedSeries: false,
    showBlockedActressSeries: false,
    showBlockedTitleKeywords: false,
  };
  const DEFAULT_SHORTCUTS = {
    blocked: "q",
    verified: "w",
    downloaded: "d",
    marked: "e",
    wiki: "r",
    wj: "c",
    magnet: "x",
    sub: "z",
    gentxt: "f",
    save115: "s",
  };
  const SHORTCUT_LABELS = {
    blocked: "屏蔽",
    verified: "已鉴定",
    downloaded: "已下载",
    marked: "标记",
    wiki: "女优鉴定",
    wj: "wj磁链",
    magnet: "磁力搜索",
    sub: "字幕(迅雷)",
    gentxt: "生成TXT",
    save115: "保存到115",
  };
  const EXCLUSIVE_STATE_CONFIG = {
    blocked: {
      listKey: "blocked",
      label: "已屏蔽",
      persistAction: "blocked",
      removeAction: "unblocked",
      useRawCode: false,
    },
    verified: {
      listKey: "verified",
      label: "已鉴定",
      persistAction: "verified",
      removeAction: "unverified",
      useRawCode: false,
    },
    downloaded: {
      listKey: "downloaded",
      label: "已下载",
      persistAction: "downloaded",
      removeAction: "undownloaded",
      useRawCode: false,
    },
    marked: {
      listKey: "marked",
      label: "已标记",
      persistAction: "marked",
      removeAction: "unmarked",
      useRawCode: true,
    },
  };
  const EXCLUSIVE_STATE_ORDER = ["blocked", "verified", "downloaded", "marked"];

  const CODE_PATTERNS = [
    /FC2-PPV-\d{6,7}/i,
    /HEYZO-\d{4}/i,
    /[A-Z]{2,10}-\d{2,5}[A-Z]?/i,
    /[A-Z]{2,10}\d{2,5}[A-Z]?/i,
  ];

  let stickerData = {
    blocked: {},
    verified: {},
    downloaded: {},
    marked: {},
    blockedSeries: {},
    blockedTitleKeywords: {},
    blockedActresses: {},
    blockedActressSeries: {},
    mediocreActresses: {},
    collectedActresses: {},
    actressByCode: {},
    magnetSavedVideos: {},
    videoDownloadedVideos: {},
    videoCrackedVideos: {},
  };
  let stickerSettings = { ...DEFAULT_SETTINGS };
  let stickerShortcuts = { ...DEFAULT_SHORTCUTS };
  let detailPageMeta = null;
  let shortcutListenerBound = false;
  let observer = null;
  let refreshTimer = null;
  let visibilityPassTimer = null;
  let visibilityPassGeneration = 0;
  let detailEnhanceBootstrappedCode = "";

  const JM_IGNORE_MUTATION_SELECTOR =
    ".jm-sticker-actions, .jm-list-meta-row, .jm-detail-sticker-actions, " +
    "#jm-detail-sticker-actions, #jm-magnet-saved-tags, .jm-magnet-saved-tags, " +
    "#jm-list-toolbar, #jm-header-tools, #jm-javdb-settings-panel, " +
    ".jm-magnet-file-preview, .jm-list-meta-actresses, .jm-mark-check, " +
    "#jm-block-modal, #jm-verified-modal, #jm-new-works-modal";

  function isExtensionOwnedNode(node) {
    if (!node) return false;
    if (node.nodeType === Node.TEXT_NODE) {
      const parent = node.parentElement;
      return parent ? isExtensionOwnedNode(parent) : false;
    }
    if (!(node instanceof Element)) return false;
    if (node.id?.startsWith("jm-")) return true;
    if ([...node.classList].some((cls) => cls.startsWith("jm-"))) return true;
    return Boolean(node.closest(JM_IGNORE_MUTATION_SELECTOR));
  }

  function shouldRefreshForMutations(records) {
    for (const record of records) {
      if (record.type !== "childList") continue;
      const added = [...record.addedNodes].some(
        (node) => node.nodeType === Node.ELEMENT_NODE && !isExtensionOwnedNode(node)
      );
      const removed = [...record.removedNodes].some(
        (node) => node.nodeType === Node.ELEMENT_NODE && !isExtensionOwnedNode(node)
      );
      if (added || removed) return true;
    }
    return false;
  }
  let blockModal = null;
  let seriesModal = null;
  let titleKeywordModal = null;
  let titleKeywordRemoveModal = null;
  let pendingBlockMeta = null;
  const actressFetchPending = new Set();
  const actressFetchQueue = [];
  let actressFetchActive = 0;
  const ACTRESS_FETCH_LIMIT = 5;
  const ACTRESS_BATCH_SIZE = 20;
  let actressVisibilityObserver = null;

  let extensionInvalidNotified = false;

  function isExtensionContextValid() {
    try {
      return Boolean(chrome?.runtime?.id);
    } catch (_) {
      return false;
    }
  }

  function isExtensionInvalidatedMessage(message) {
    return /extension context invalidated|context invalidated|receiving end does not exist/i.test(
      String(message || "")
    );
  }

  function notifyExtensionReloadNeeded() {
    if (extensionInvalidNotified) return;
    extensionInvalidNotified = true;
    const text = "扩展已更新，请刷新页面后继续。";
    if (typeof showJmToast === "function") showJmToast(text, "error");
    else console.warn(`[JAV Manager] ${text}`);
  }

  function sendRuntimeMessage(payload) {
    return new Promise((resolve) => {
      try {
        if (!isExtensionContextValid()) {
          notifyExtensionReloadNeeded();
          resolve({ ok: false, message: "Extension context invalidated.", invalidated: true });
          return;
        }
        chrome.runtime.sendMessage(payload, (response) => {
          if (chrome.runtime.lastError) {
            const message = chrome.runtime.lastError.message || "";
            if (isExtensionInvalidatedMessage(message)) notifyExtensionReloadNeeded();
            resolve({
              ok: false,
              message,
              invalidated: isExtensionInvalidatedMessage(message),
            });
            return;
          }
          resolve(response || { ok: false });
        });
      } catch (err) {
        const message = String(err.message || err);
        if (isExtensionInvalidatedMessage(message)) notifyExtensionReloadNeeded();
        resolve({ ok: false, message, invalidated: isExtensionInvalidatedMessage(message) });
      }
    });
  }

  const CRACK_STATUS_LABELS = {
    cracked: "已破解",
    cracked_sub_pending_burn: "已破解·字幕待烧录",
    pending_extract_sub: "待提取字幕",
    pending_crack: "待破解",
  };

  function getCrackStatusLabel(rec) {
    return String(rec?.crack_status_label || CRACK_STATUS_LABELS[rec?.crack_status] || "已破解");
  }

  function getCrackSubtitleLabel(rec) {
    const status = String(rec?.crack_status || "");
    if (status === "cracked_sub_pending_burn") return "外挂字幕待烧录";
    if (status === "pending_extract_sub") return "待提取字幕";
    return rec?.has_subtitle ? "有字幕" : "无字幕";
  }

  function getCrackStatusTagClass(status) {
    switch (status) {
      case "cracked":
        return "jm-video-cracked-status-tag jm-cracked-done";
      case "cracked_sub_pending_burn":
        return "jm-video-cracked-status-tag jm-cracked-sub-pending";
      case "pending_extract_sub":
        return "jm-video-cracked-status-tag jm-cracked-extract-pending";
      case "pending_crack":
        return "jm-video-cracked-status-tag jm-cracked-pending";
      default:
        return "jm-video-cracked-status-tag";
    }
  }

  function isJavdbHost() {
    return /javdb/i.test(location.hostname);
  }

  function isDetailPage() {
    if (/^\/v\/[a-zA-Z0-9]+\/?$/.test(location.pathname)) return true;
    if (document.querySelector(".video-detail, .column-video-cover, .movie-panel-info")) return true;
    return false;
  }

  function findVideoItems() {
    const movieList = document.querySelector(
      ".movie-list:not(.movie-list-related):not(.related-movies)"
    );
    if (movieList) {
      const items = Array.from(movieList.children).filter((el) =>
        el.matches(".item, .column, .grid-item")
      );
      if (items.length > 0) return items;
    }

    const videos = document.getElementById("videos");
    if (!videos) return [];

    const grid =
      videos.querySelector(".grid.columns") ||
      (videos.classList.contains("columns") ? videos : null) ||
      videos.querySelector(".columns");
    if (!grid) return [];

    return Array.from(grid.querySelectorAll(".grid-item.column, .column.grid-item, .grid-item"));
  }

  function isListPage() {
    return isJavdbHost() && !isDetailPage() && findVideoItems().length > 0;
  }

  function normalizeCode(raw) {
    const text = String(raw || "").toUpperCase().trim();
    const match = text.match(/^([A-Z]+)-?(\d+[A-Z]?)$/);
    if (match) return `${match[1]}-${match[2]}`;
    return text;
  }

  function extractCode(text) {
    const cleaned = String(text || "")
      .replace(/[\[\(（【].*?[\]\)）】]/g, " ")
      .replace(
        /\b(1080p|720p|4k|2160p|hd|fhd|uhd|x264|x265|h264|h265|hevc|uncensored|censored|chinese|subtitle|sub|无码|有码|中字|字幕)\b/gi,
        " "
      )
      .replace(/[_\.\s]+/g, " ");

    for (const pattern of CODE_PATTERNS) {
      const match = cleaned.match(pattern);
      if (match) return normalizeCode(match[0]);
    }
    return null;
  }

  function extractSeries(codeOrSeries) {
    const text = String(codeOrSeries || "").toUpperCase().trim();
    if (!text) return "";
    if (text.startsWith("FC2-PPV")) return "FC2-PPV";
    if (text.startsWith("HEYZO")) return "HEYZO";
    const code = extractCode(text);
    const source = code || text;
    const dash = source.indexOf("-");
    if (dash > 0) return source.slice(0, dash);
    return source.replace(/-?\d.*$/, "").replace(/-$/, "") || source;
  }

  function normalizeSeriesInput(input) {
    return extractSeries(String(input || "").trim());
  }

  function isSeriesBlocked(code, title) {
    const blocked = stickerData.blockedSeries || {};
    const keys = Object.keys(blocked);
    if (keys.length === 0) return false;

    const parsedCode = code || extractCode(title || "");
    const series = parsedCode ? extractSeries(parsedCode) : "";
    const haystack = `${parsedCode || ""} ${title || ""}`.toUpperCase();

    for (const key of keys) {
      const blockedSeries = String(key).toUpperCase();
      if (!blockedSeries) continue;
      if (series && series === blockedSeries) return true;
      if (parsedCode && parsedCode.startsWith(`${blockedSeries}-`)) return true;
      if (haystack.includes(`${blockedSeries}-`) || haystack.includes(`${blockedSeries} `)) return true;
    }
    return false;
  }

  function extractReleaseDate(itemEl) {
    const selectors = [".meta-value", ".value", "time", "[datetime]"];
    for (const sel of selectors) {
      const el = itemEl.querySelector(sel);
      if (!el) continue;
      const text = (el.getAttribute("datetime") || el.textContent || "").trim();
      const match = text.match(/\d{4}[-/.]\d{1,2}[-/.]\d{1,2}/);
      if (match) return match[0].replace(/\//g, "-");
    }

    const tagsText = itemEl.textContent || "";
    const dateMatch = tagsText.match(/\b(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2})\b/);
    return dateMatch ? dateMatch[1].replace(/\//g, "-") : "";
  }

  function parseStickerItem(itemEl) {
    const titleEl =
      itemEl.querySelector(".video-title") ||
      itemEl.querySelector(".video-title a") ||
      itemEl.querySelector("a[title]");
    const title = (titleEl?.textContent || titleEl?.getAttribute("title") || "").trim();
    const code = extractCode(title);
    const linkEl = itemEl.querySelector('a[href*="/v/"]');
    let detailUrl = "";
    if (linkEl) {
      try {
        detailUrl = new URL(linkEl.getAttribute("href"), location.origin).href;
      } catch (_) {
        detailUrl = linkEl.href || "";
      }
    }
    return {
      code,
      title,
      releaseDate: extractReleaseDate(itemEl),
      detailUrl,
      pageUrl: location.href,
      pageTitle: document.title,
    };
  }

  function extractCodeFromPanel() {
    for (const block of document.querySelectorAll(
      ".movie-panel-info .panel-block, .movie-panel-info .meta, .video-meta-panel .panel-block"
    )) {
      const label = block.querySelector("strong, .label")?.textContent || "";
      if (!/番号|识别|識別|番號|ID|Code|編號|编号/i.test(label)) continue;
      const value = block.querySelector(".value")?.textContent || block.textContent || "";
      const code = extractCode(value);
      if (code) return code;
    }
    return "";
  }

  function parseDetailPageMeta() {
    const titleEl =
      document.querySelector(".movie-panel-info h2.title") ||
      document.querySelector(".video-detail h2.title") ||
      document.querySelector("h2.title") ||
      document.querySelector(".current-title") ||
      document.querySelector("h1.title");
    const title = (titleEl?.textContent || document.title.split("|")[0] || "").trim();
    let code = extractCode(title);
    if (!code) code = extractCodeFromPanel();
    if (!code) {
      for (const el of document.querySelectorAll(".movie-panel-info .value, .panel-block .value")) {
        code = extractCode(el.textContent || "");
        if (code) break;
      }
    }

    let releaseDate = "";
    document.querySelectorAll(".movie-panel-info .panel-block, .movie-panel-info .meta").forEach((block) => {
      const label = block.querySelector("strong, .label")?.textContent || "";
      if (/日期|發行|发行|released/i.test(label)) {
        const value = block.querySelector(".value")?.textContent?.trim() || block.textContent || "";
        const match = value.match(/\d{4}[-/.]\d{1,2}[-/.]\d{1,2}/);
        if (match) releaseDate = match[0].replace(/\//g, "-");
      }
    });

    return {
      code,
      title,
      releaseDate,
      detailUrl: location.href,
      pageUrl: location.href,
      pageTitle: document.title,
    };
  }

  function buildMetaFromPayload(payload) {
    const pageMeta = isDetailPage() ? parseDetailPageMeta() : {};
    return {
      code: extractCode(payload?.code || pageMeta.code || ""),
      title: String(payload?.title || pageMeta.title || ""),
      releaseDate: String(payload?.release_date || pageMeta.releaseDate || ""),
      detailUrl: String(payload?.detail_url || pageMeta.detailUrl || location.href),
      pageUrl: String(payload?.page_url || pageMeta.pageUrl || location.href),
      pageTitle: String(payload?.page_title || pageMeta.pageTitle || document.title),
    };
  }

  function nowString() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  function getMagnetSavedStorageLabel(storageType) {
    return String(storageType || "") === "115" ? "已保存到115" : "已保存磁链到本地";
  }

  function getMagnetSavedSubtitleLabel(hasSubtitle) {
    return hasSubtitle ? "有字幕" : "无字幕";
  }

  function findDetailTitleEl() {
    return (
      document.querySelector(".video-detail h2.title") ||
      document.querySelector(".movie-panel-info h2.title") ||
      document.querySelector(".column-video-cover h2.title") ||
      document.querySelector("h2.title")
    );
  }

  function removeDetailMagnetSavedTags() {
    document.querySelectorAll("#jm-magnet-saved-tags, .jm-magnet-saved-tags").forEach((el) => el.remove());
  }

  function updateDetailMagnetSavedTags() {
    if (!isDetailPage()) {
      removeDetailMagnetSavedTags();
      return;
    }
    detailPageMeta = parseDetailPageMeta();
    const code = detailPageMeta?.code;
    const titleEl = findDetailTitleEl();
    if (!titleEl || !code) {
      removeDetailMagnetSavedTags();
      return;
    }

    const rec = stickerData.magnetSavedVideos?.[code];
    if (!rec) {
      removeDetailMagnetSavedTags();
      return;
    }

    const storageText = getMagnetSavedStorageLabel(rec.storage_type);
    const subText = getMagnetSavedSubtitleLabel(Boolean(rec.has_subtitle));
    const existing = document.getElementById("jm-magnet-saved-tags");
    if (existing && existing.dataset.jmCode === code) {
      const storageEl = existing.querySelector(".jm-magnet-saved-storage-tag");
      const subEl = existing.querySelector(".jm-magnet-saved-subtitle-tag");
      if (storageEl?.textContent === storageText && subEl?.textContent === subText) {
        return;
      }
    }

    removeDetailMagnetSavedTags();

    const wrap = document.createElement("div");
    wrap.id = "jm-magnet-saved-tags";
    wrap.className = "jm-magnet-saved-tags";
    wrap.dataset.jmCode = code;

    const storageTag = document.createElement("span");
    storageTag.className = "jm-magnet-saved-storage-tag";
    storageTag.textContent = storageText;

    const subTag = document.createElement("span");
    subTag.className = rec.has_subtitle
      ? "jm-magnet-saved-subtitle-tag jm-has-sub"
      : "jm-magnet-saved-subtitle-tag jm-no-sub";
    subTag.textContent = subText;

    wrap.appendChild(storageTag);
    wrap.appendChild(subTag);
    titleEl.insertAdjacentElement("afterend", wrap);
  }

  async function markMagnetSavedVideo(payload) {
    detailPageMeta = parseDetailPageMeta();
    const code = normalizeCode(payload?.code || detailPageMeta?.code || "");
    if (!code) {
      return { ok: false, message: "无法识别番号" };
    }

    const storageType = String(payload?.storage_type || "local_magnet").trim() === "115" ? "115" : "local_magnet";
    const record = {
      code,
      title: String(payload?.title || detailPageMeta?.title || ""),
      storage_type: storageType,
      has_subtitle: Boolean(payload?.has_subtitle),
      is_4k: Boolean(payload?.is_4k),
      detail_url: String(payload?.detail_url || location.href),
      folder_name: String(payload?.folder_name || ""),
      recorded_at: nowString(),
    };

    const desktop = await sendToDesktop("magnet_saved_video", record);
    if (!desktop?.offline && !desktop?.ok) {
      return { ok: false, message: desktop?.message || "桌面数据库保存失败" };
    }

    if (!stickerData.magnetSavedVideos) stickerData.magnetSavedVideos = {};
    stickerData.magnetSavedVideos[code] = record;
    await saveLocalState();
    updateDetailMagnetSavedTags();
    return { ok: true };
  }

  function removeDetailVideoDownloadedTags() {
    document.querySelectorAll("#jm-video-downloaded-tags, .jm-video-downloaded-tags").forEach((el) => el.remove());
  }

  function updateDetailVideoDownloadedTags() {
    if (!isDetailPage()) {
      removeDetailVideoDownloadedTags();
      return;
    }
    detailPageMeta = parseDetailPageMeta();
    const code = detailPageMeta?.code;
    const titleEl = findDetailTitleEl();
    if (!titleEl || !code) {
      removeDetailVideoDownloadedTags();
      return;
    }

    const rec = stickerData.videoDownloadedVideos?.[code];
    if (!rec) {
      removeDetailVideoDownloadedTags();
      return;
    }

    const subText = rec.has_subtitle ? "有字幕" : "无字幕";
    const is4k = Boolean(rec.is_4k);
    const existing = document.getElementById("jm-video-downloaded-tags");
    if (
      existing &&
      existing.dataset.jmCode === code &&
      existing.dataset.jmSub === subText &&
      existing.dataset.jm4k === (is4k ? "1" : "0")
    ) {
      return;
    }

    removeDetailVideoDownloadedTags();

    const wrap = document.createElement("div");
    wrap.id = "jm-video-downloaded-tags";
    wrap.className = "jm-video-downloaded-tags";
    wrap.dataset.jmCode = code;
    wrap.dataset.jmSub = subText;
    wrap.dataset.jm4k = is4k ? "1" : "0";

    const downloadedTag = document.createElement("span");
    downloadedTag.className = "jm-video-downloaded-status-tag";
    downloadedTag.textContent = "已下载";

    const subTag = document.createElement("span");
    subTag.className = rec.has_subtitle
      ? "jm-video-downloaded-subtitle-tag jm-has-sub"
      : "jm-video-downloaded-subtitle-tag jm-no-sub";
    subTag.textContent = subText;

    wrap.appendChild(downloadedTag);
    wrap.appendChild(subTag);
    if (is4k) {
      const fourKTag = document.createElement("span");
      fourKTag.className = "jm-video-downloaded-4k-tag";
      fourKTag.textContent = "4K";
      wrap.appendChild(fourKTag);
    }

    titleEl.insertAdjacentElement("beforebegin", wrap);
  }

  async function markVideoDownloadedVideo(payload) {
    detailPageMeta = parseDetailPageMeta();
    const code = normalizeCode(payload?.code || detailPageMeta?.code || "");
    if (!code) {
      return { ok: false, message: "无法识别番号" };
    }

    const record = {
      code,
      title: String(payload?.title || detailPageMeta?.title || ""),
      has_subtitle: Boolean(payload?.has_subtitle),
      is_4k: Boolean(payload?.is_4k),
      detail_url: String(payload?.detail_url || location.href),
      folder_name: String(payload?.folder_name || ""),
      recorded_at: nowString(),
    };

    const hideMeta = {
      code,
      title: record.title,
      detail_url: record.detail_url,
      page_url: record.detail_url,
    };
    if (!stickerData.downloaded[code]) {
      const hidden = await persistListAction("downloaded", "downloaded", hideMeta, {});
      if (!hidden) {
        return { ok: false, message: "已下载贴纸隐藏失败" };
      }
    } else {
      applyAllVisibility();
    }

    const desktop = await sendToDesktop("video_downloaded_video", record);
    if (!desktop?.offline && !desktop?.ok) {
      return { ok: false, message: desktop?.message || "桌面数据库保存失败" };
    }

    if (!stickerData.videoDownloadedVideos) stickerData.videoDownloadedVideos = {};
    stickerData.videoDownloadedVideos[code] = record;
    await saveLocalState();
    updateDetailVideoDownloadedTags();
    return { ok: true };
  }

  function removeDetailVideoCrackedTags() {
    document.querySelectorAll("#jm-video-cracked-tags, .jm-video-cracked-tags").forEach((el) => el.remove());
  }

  function updateDetailVideoCrackedTags() {
    if (!isDetailPage()) {
      removeDetailVideoCrackedTags();
      return;
    }
    detailPageMeta = parseDetailPageMeta();
    const code = detailPageMeta?.code;
    const titleEl = findDetailTitleEl();
    if (!titleEl || !code) {
      removeDetailVideoCrackedTags();
      return;
    }

    const rec = stickerData.videoCrackedVideos?.[code];
    if (!rec) {
      removeDetailVideoCrackedTags();
      return;
    }

    const status = String(rec.crack_status || "cracked");
    const statusText = getCrackStatusLabel(rec);
    const subText = getCrackSubtitleLabel(rec);
    const is4k = Boolean(rec.is_4k);
    const existing = document.getElementById("jm-video-cracked-tags");
    if (
      existing &&
      existing.dataset.jmCode === code &&
      existing.dataset.jmStatus === status &&
      existing.dataset.jmSub === subText &&
      existing.dataset.jm4k === (is4k ? "1" : "0")
    ) {
      return;
    }

    removeDetailVideoCrackedTags();

    const wrap = document.createElement("div");
    wrap.id = "jm-video-cracked-tags";
    wrap.className = "jm-video-cracked-tags";
    wrap.dataset.jmCode = code;
    wrap.dataset.jmStatus = status;
    wrap.dataset.jmSub = subText;
    wrap.dataset.jm4k = is4k ? "1" : "0";

    const statusTag = document.createElement("span");
    statusTag.className = getCrackStatusTagClass(status);
    statusTag.textContent = statusText;

    const subTag = document.createElement("span");
    const subPositive =
      Boolean(rec.has_subtitle) ||
      status === "cracked_sub_pending_burn" ||
      status === "pending_extract_sub";
    subTag.className = subPositive
      ? "jm-video-cracked-subtitle-tag jm-has-sub"
      : "jm-video-cracked-subtitle-tag jm-no-sub";
    subTag.textContent = subText;

    wrap.appendChild(statusTag);
    wrap.appendChild(subTag);
    if (is4k) {
      const fourKTag = document.createElement("span");
      fourKTag.className = "jm-video-cracked-4k-tag";
      fourKTag.textContent = "4K";
      wrap.appendChild(fourKTag);
    }

    titleEl.insertAdjacentElement("beforebegin", wrap);
  }

  async function markVideoCrackedVideo(payload) {
    detailPageMeta = parseDetailPageMeta();
    const code = normalizeCode(payload?.code || detailPageMeta?.code || "");
    if (!code) {
      return { ok: false, message: "无法识别番号" };
    }

    const crackStatus = String(payload?.crack_status || "pending_crack");
    const record = {
      code,
      title: String(payload?.title || detailPageMeta?.title || ""),
      crack_status: crackStatus,
      crack_status_label: String(
        payload?.crack_status_label || CRACK_STATUS_LABELS[crackStatus] || crackStatus
      ),
      has_subtitle: Boolean(payload?.has_subtitle),
      is_4k: Boolean(payload?.is_4k),
      has_subtitle_file: Boolean(payload?.has_subtitle_file),
      has_uncensored_file: Boolean(payload?.has_uncensored_file),
      detail_url: String(payload?.detail_url || location.href),
      folder_name: String(payload?.folder_name || ""),
      source_file: String(payload?.source_file || ""),
      recorded_at: nowString(),
    };

    const desktop = await sendToDesktop("video_cracked_video", record);
    if (!desktop?.offline && !desktop?.ok) {
      return { ok: false, message: desktop?.message || "桌面数据库保存失败" };
    }

    if (!stickerData.videoCrackedVideos) stickerData.videoCrackedVideos = {};
    stickerData.videoCrackedVideos[code] = record;
    await saveLocalState();
    updateDetailVideoCrackedTags();
    return { ok: true };
  }

  let pendingAsyncDetailClose = null;

  function closeCurrentDetailTab() {
    void sendRuntimeMessage({ type: "close_current_tab" }).then((res) => {
      if (res?.invalidated) window.close();
    });
  }

  function queueAsyncDetailClose(meta, actionKey) {
    if (!isDetailPage()) return;
    const code = normalizeCode(meta?.code || "");
    if (!code) return;
    pendingAsyncDetailClose = { code, actionKey: String(actionKey || "") };
  }

  function clearAsyncDetailClose(code, actionKey = "") {
    const normalized = normalizeCode(code || "");
    const action = String(actionKey || "").trim();
    if (!pendingAsyncDetailClose) return;
    if (pendingAsyncDetailClose.code !== normalized) return;
    if (action && pendingAsyncDetailClose.actionKey && pendingAsyncDetailClose.actionKey !== action) {
      return;
    }
    pendingAsyncDetailClose = null;
  }

  function finishAsyncDetailClose(message) {
    const pending = pendingAsyncDetailClose;
    if (!pending || !message?.code) return;
    if (normalizeCode(message.code) !== pending.code) return;
    const msgAction = String(message.actionKey || message.action || "").trim();
    if (msgAction && pending.actionKey && msgAction !== pending.actionKey) return;
    if (message.status === "done") {
      applyAllVisibility();
      closeCurrentDetailTab();
      pendingAsyncDetailClose = null;
      return;
    }
    if (message.status === "error") {
      pendingAsyncDetailClose = null;
    }
  }

  function closeDetailAfterListAction() {
    applyAllVisibility();
    if (isDetailPage()) {
      closeCurrentDetailTab();
    }
  }

  function setupListItemNavigation() {
    if (setupListItemNavigation._bound) return;
    setupListItemNavigation._bound = true;

    document.addEventListener(
      "mousedown",
      (event) => {
        if (!isListPage()) return;
        if (event.button !== 0 && event.button !== 1) return;
        if (event.defaultPrevented) return;

        const item = event.target.closest(".jm-sticker-item");
        if (!item) return;
        const link = item.querySelector('a[href*="/v/"]');
        if (!link) return;

        const inCover =
          event.target.closest(".box, .cover, .video-cover, .tile-images, .video-title, a[href*='/v/']") &&
          !event.target.closest(".jm-sticker-actions, .jm-list-actresses");
        if (!inCover) return;

        event.preventDefault();
        event.stopPropagation();

        const url = link.href;
        void sendRuntimeMessage({
          type: "open_tab",
          url,
          active: event.button === 0,
        }).then((res) => {
          if (!res?.invalidated && res?.ok !== false) return;
          if (event.button === 0) location.assign(url);
          else window.open(url, "_blank", "noopener");
        });
      },
      true
    );
  }

  async function runStickerAction(actionKey, meta) {
    if (!meta?.code && actionKey !== "save115") {
      return { ok: false, message: "未能识别番号" };
    }

    switch (actionKey) {
      case "blocked":
      case "verified":
      case "downloaded":
      case "marked":
        return tryApplyExclusiveState(actionKey, meta);
      case "wiki":
        window.open(`https://shiroutowiki.work/?s=${encodeURIComponent(meta.code)}`, "_blank", "noopener");
        return { ok: true };
      case "wj":
        if (typeof window.__JM_openWjMagnetModal === "function") {
          window.__JM_openWjMagnetModal(meta.code);
        } else {
          window.open(`https://18mag.net/search?q=${encodeURIComponent(meta.code)}`, "_blank", "noopener");
        }
        return { ok: true };
      case "magnet":
        if (typeof window.__JM_openMagnetSearch === "function") {
          window.__JM_openMagnetSearch(meta.code);
        } else {
          window.open(`https://18mag.net/search?q=${encodeURIComponent(meta.code)}`, "_blank", "noopener");
        }
        return { ok: true };
      case "sub":
        if (typeof window.__JM_openSubtitleSearch === "function") {
          window.__JM_openSubtitleSearch(meta.code);
        } else {
          showJmToast("字幕功能尚未就绪，请刷新页面后重试。", "error");
          return { ok: false, message: "字幕功能尚未就绪" };
        }
        return { ok: true };
      case "gentxt":
        queueAsyncDetailClose(meta, "gentxt");
        runGenerateMagnetTxt(meta);
        return { ok: true };
      case "save115": {
        queueAsyncDetailClose(meta, "save115");
        const res = await sendRuntimeMessage({
          type: "save115_filtered",
          code: meta.code,
          detailUrl: meta.detailUrl || location.href,
          javdbMagnets: scrapeJavdbMagnetsForTxt(),
          actress: scrapeActressFromDetailPage(),
          title: meta.title || "",
        });
        if (res?.invalidated) {
          clearAsyncDetailClose(meta.code);
          showJmToast("扩展已更新，请刷新页面后重试。", "error");
          return { ok: false, message: "Extension context invalidated." };
        }
        if (!res?.ok) {
          clearAsyncDetailClose(meta.code);
          showJmToast(res?.message || "115 提交失败", "error");
          return { ok: false, message: res?.message || "115 提交失败" };
        }
        showJmToast("正在筛选磁链并提交 115，完成后将通过通知提示。", "running");
        return { ok: true };
      }
      default:
        return { ok: false, message: `未知操作: ${actionKey}` };
    }
  }

  function isEditableTarget(target) {
    if (!target) return false;
    const tag = String(target.tagName || "").toLowerCase();
    return tag === "input" || tag === "textarea" || tag === "select" || target.isContentEditable;
  }

  async function handleShortcutKey(event) {
    if (event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey) return;
    if (isEditableTarget(event.target)) return;
    if (!isJavdbHost() || !isDetailPage()) return;

    const pressed = String(event.key || "").toLowerCase();
    if (!pressed) return;

    const actionKey = Object.keys(stickerShortcuts).find((key) => stickerShortcuts[key] === pressed);
    if (!actionKey) return;

    detailPageMeta = parseDetailPageMeta();
    if (!detailPageMeta?.code && actionKey !== "save115") return;

    event.preventDefault();
    event.stopImmediatePropagation();
    await runStickerAction(actionKey, detailPageMeta);
  }

  function ensureShortcutListener() {
    if (shortcutListenerBound) return;
    window.addEventListener("keydown", handleShortcutKey, true);
    document.addEventListener("keydown", handleShortcutKey, true);
    shortcutListenerBound = true;
  }

  async function handleStickerMessage(msg) {
    if (msg?.type === "ping") {
      return { ok: true, ready: true };
    }
    if (msg?.type === "apply_sticker_action") {
      const actionKey = String(msg.action || msg.actionKey || "").trim();
      if (!actionKey) {
        return { ok: false, message: "缺少 action" };
      }
      const meta = buildMetaFromPayload(msg);
      if (!meta.code) {
        return { ok: false, message: "未能识别番号" };
      }
      return runStickerAction(actionKey, meta);
    }
    if (msg?.type === "mark_magnet_saved_video") {
      return markMagnetSavedVideo(msg.video || msg);
    }
    if (msg?.type === "mark_video_downloaded") {
      return markVideoDownloadedVideo(msg.video || msg);
    }
    if (msg?.type === "mark_video_cracked") {
      return markVideoCrackedVideo(msg.video || msg);
    }
    if (msg?.type === "refresh_list_visibility") {
      return loadLocalState().then(() => {
        reconcileDownloadedHideState();
        if (isListPage()) decorateItems();
        scheduleVisibilityPass();
        updateDetailMagnetSavedTags();
        updateDetailVideoDownloadedTags();
        updateDetailVideoCrackedTags();
        return { ok: true };
      });
    }
    return null;
  }

  window.__JM_handleStickerMessage = handleStickerMessage;

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    const handledTypes = new Set([
      "ping",
      "apply_sticker_action",
      "mark_magnet_saved_video",
      "mark_video_downloaded",
      "mark_video_cracked",
      "refresh_list_visibility",
    ]);
    if (!handledTypes.has(msg?.type)) return false;
    handleStickerMessage(msg)
      .then((result) => {
        if (result !== null) sendResponse(result);
      })
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  });

  chrome.runtime.onMessage.addListener((message) => {
    if (message?.type === "magnet_filter_rules_push" && message.rules) {
      chrome.storage.local.set({ magnetFilterRules: message.rules }).catch(() => {});
    }
    if (message?.type === "magnet_txt_status") {
      showJmToast(message.message || "", message.status);
      finishAsyncDetailClose(message);
    }
  });

  function shortcutHint(actionKey) {
    const key = stickerShortcuts[actionKey];
    return key ? ` (${key})` : "";
  }

  function createActionBarElement() {
    const bar = document.createElement("div");
    bar.className = "jm-sticker-actions";
    bar.innerHTML = `
      <button type="button" class="jm-act jm-act-block">屏蔽</button>
      <button type="button" class="jm-act jm-act-verified">已鉴定</button>
      <button type="button" class="jm-act jm-act-downloaded">已下载</button>
      <button type="button" class="jm-act jm-act-mark">标记</button>
      <button type="button" class="jm-act jm-act-wiki">女优鉴定</button>
      <button type="button" class="jm-act jm-act-wj">wj磁链</button>
      <button type="button" class="jm-act jm-act-magnet">磁力搜索</button>
      <button type="button" class="jm-act jm-act-sub">字幕(迅雷)</button>
      <button type="button" class="jm-act jm-act-gentxt">生成TXT</button>
      <button type="button" class="jm-act jm-act-save115">保存到115</button>
    `;
    return bar;
  }

  function isDetailActionBar(bar) {
    return Boolean(
      bar && (bar.id === "jm-detail-sticker-actions" || bar.classList.contains("jm-detail-sticker-actions"))
    );
  }

  function updateActionBarShortcutLabels(bar) {
    if (!bar) return;
    const showHints = isDetailActionBar(bar);
    const map = {
      ".jm-act-block": { actionKey: "blocked", label: "屏蔽" },
      ".jm-act-verified": { actionKey: "verified", label: "已鉴定" },
      ".jm-act-downloaded": { actionKey: "downloaded", label: "已下载" },
      ".jm-act-mark": { actionKey: "marked", label: "标记", activeLabel: "取消标记" },
      ".jm-act-wiki": { actionKey: "wiki", label: "女优鉴定" },
      ".jm-act-wj": { actionKey: "wj", label: "wj磁链" },
      ".jm-act-magnet": { actionKey: "magnet", label: "磁力搜索" },
      ".jm-act-sub": { actionKey: "sub", label: "字幕(迅雷)" },
      ".jm-act-gentxt": { actionKey: "gentxt", label: "生成TXT" },
      ".jm-act-save115": { actionKey: "save115", label: "保存到115" },
    };
    for (const [selector, info] of Object.entries(map)) {
      const btn = bar.querySelector(selector);
      if (!btn) continue;
      let base = info.label;
      if (selector === ".jm-act-mark" && btn.classList.contains("jm-active")) {
        base = info.activeLabel || "取消标记";
      }
      const nextText = showHints ? `${base}${shortcutHint(info.actionKey)}` : base;
      if (btn.textContent !== nextText) {
        btn.textContent = nextText;
      }
    }
  }

  function refreshDetailActionBarShortcutLabels() {
    const bar = document.getElementById("jm-detail-sticker-actions");
    if (bar) updateActionBarShortcutLabels(bar);
  }

  function openWjMagnetPage(code) {
    window.open(`https://18mag.net/search?q=${encodeURIComponent(code)}`, "_blank", "noopener");
  }

  function openWjMagnetPopup(code) {
    if (typeof window.__JM_openWjMagnetModal === "function") {
      window.__JM_openWjMagnetModal(code);
      return;
    }
    openWjMagnetPage(code);
  }

  function attachActionBarHandlers(bar, meta) {
    bar.querySelector(".jm-act-block").addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      openBlockModal(meta);
    });

    bar.querySelector(".jm-act-verified").addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      await runStickerAction("verified", meta);
    });

    bar.querySelector(".jm-act-downloaded").addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      await runStickerAction("downloaded", meta);
    });

    bar.querySelector(".jm-act-mark").addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      await runStickerAction("marked", meta);
    });

    bar.querySelector(".jm-act-wiki").addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      runStickerAction("wiki", meta);
    });

    const wjBtn = bar.querySelector(".jm-act-wj");
    wjBtn.addEventListener("click", (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      e.stopPropagation();
      if (!meta.code) {
        alert("未能识别番号。");
        return;
      }
      openWjMagnetPopup(meta.code);
    });
    wjBtn.addEventListener("auxclick", (e) => {
      if (e.button !== 1 || !meta.code) return;
      e.preventDefault();
      e.stopPropagation();
      openWjMagnetPage(meta.code);
    });
    wjBtn.addEventListener("mousedown", (e) => {
      if (e.button !== 1 || !meta.code) return;
      e.preventDefault();
      openWjMagnetPage(meta.code);
    });

    bar.querySelector(".jm-act-magnet").addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (!meta.code) {
        alert("未能识别番号。");
        return;
      }
      if (typeof window.__JM_openMagnetSearch === "function") {
        window.__JM_openMagnetSearch(meta.code);
      } else {
        window.open(`https://18mag.net/search?q=${encodeURIComponent(meta.code)}`, "_blank", "noopener");
      }
    });

    bar.querySelector(".jm-act-sub")?.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (!meta.code) {
        alert("未能识别番号。");
        return;
      }
      if (typeof window.__JM_openSubtitleSearch === "function") {
        window.__JM_openSubtitleSearch(meta.code);
      } else {
        alert("字幕功能尚未就绪，请刷新页面后重试。");
      }
    });

    bar.querySelector(".jm-act-gentxt").addEventListener(
      "click",
      (e) => {
        e.preventDefault();
        e.stopPropagation();
        e.stopImmediatePropagation();
        runStickerAction("gentxt", meta);
      },
      true
    );

    bar.querySelector(".jm-act-save115").addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      runStickerAction("save115", meta);
    });

    updateActionBarShortcutLabels(bar);
  }

  function showJmToast(text, status) {
    if (!text) return;
    let el = document.getElementById("jm-toast");
    if (!el) {
      el = document.createElement("div");
      el.id = "jm-toast";
      document.body.appendChild(el);
    }
    el.className = "jm-toast";
    if (status === "running") el.classList.add("jm-toast-running");
    else if (status === "done") el.classList.add("jm-toast-ok");
    else el.classList.add("jm-toast-err");
    el.textContent = text;
    el.hidden = false;
    const hideMs = status === "running" ? 120000 : 10000;
    clearTimeout(showJmToast._hideTimer);
    showJmToast._hideTimer = setTimeout(() => {
      el.hidden = true;
    }, hideMs);
  }

  window.showJmToast = showJmToast;

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeHtmlAttr(text) {
    return escapeHtml(text).replace(/'/g, "&#39;");
  }

  function normalizeActressName(name) {
    return String(name || "")
      .normalize("NFKC")
      .trim()
      .toLowerCase()
      .replace(/\s+/g, "");
  }

  function buildActressLookups() {
    const collectedById = {};
    const collectedByName = new Map();
    for (const row of Object.values(stickerData.collectedActresses || {})) {
      const id = String(row?.javdb_id || row?.starId || row?.id || "").trim();
      if (id) collectedById[id] = row;
      const names = [row?.name, ...(Array.isArray(row?.allName) ? row.allName : []), row?.alias]
        .filter(Boolean)
        .map((name) => String(name).trim())
        .filter(Boolean);
      for (const name of names) {
        collectedByName.set(normalizeActressName(name), row);
      }
    }

    const mediocreById = stickerData.mediocreActresses || {};
    const mediocreByName = new Map();
    for (const row of Object.values(mediocreById)) {
      if (row?.name) mediocreByName.set(normalizeActressName(row.name), row);
    }

    return {
      collectedById,
      collectedByName,
      mediocreById,
      mediocreByName,
    };
  }

  function parseActressesFromItem(itemEl) {
    const seen = new Set();
    const list = [];
    itemEl.querySelectorAll('a[href*="/actors/"], a[href*="/stars/"]').forEach((anchor) => {
      const href = anchor.getAttribute("href") || "";
      const match = href.match(/\/(actors|stars)\/([^/?#]+)/i);
      const javdbId = match ? match[2] : "";
      const name = (anchor.textContent || "").trim();
      const key = javdbId || name;
      if (!name || seen.has(key)) return;
      seen.add(key);
      list.push({ javdb_id: javdbId, name });
    });
    return list;
  }

  function parseActressesFromDetailPanel() {
    const seen = new Set();
    const list = [];
    for (const block of document.querySelectorAll(
      ".movie-panel-info .panel-block, .movie-panel-info .meta, .video-meta-panel .panel-block"
    )) {
      const label = block.querySelector("strong, .label")?.textContent || "";
      if (!/演员|演員|actress|star|女优|女優/i.test(label)) continue;
      block.querySelectorAll('a[href*="/actors/"], a[href*="/stars/"]').forEach((anchor) => {
        const href = anchor.getAttribute("href") || "";
        const match = href.match(/\/(actors|stars)\/([^/?#]+)/i);
        const javdbId = match ? match[2] : "";
        const name = (anchor.textContent || "").trim();
        const key = javdbId || name;
        if (!name || seen.has(key)) return;
        seen.add(key);
        list.push({ javdb_id: javdbId, name });
      });
    }
    return list;
  }

  async function cacheActressesForCode(code) {
    const normalized = normalizeCode(code);
    if (!normalized) return;
    const actresses = parseActressesFromDetailPanel();
    if (!actresses.length) return;
    if (!stickerData.actressByCode) stickerData.actressByCode = {};
    stickerData.actressByCode[normalized] = actresses;
    await saveLocalState();
  }

  function getActressDisplayClass(actress, lookups) {
    const id = String(actress.javdb_id || "").trim();
    if (id && lookups.collectedById[id]) return "jm-actress-collected";
    if (lookups.collectedByName.has(normalizeActressName(actress.name))) return "jm-actress-collected";
    if (id && lookups.mediocreById[id]) return "jm-actress-mediocre";
    if (lookups.mediocreByName?.has(normalizeActressName(actress.name))) return "jm-actress-mediocre";
    for (const row of Object.values(lookups.mediocreById)) {
      if (normalizeActressName(row.name) === normalizeActressName(actress.name)) return "jm-actress-mediocre";
    }
    return "";
  }

  function getMediocreReason(actress, lookups) {
    const byId = lookups.mediocreById[actress.javdb_id];
    if (byId) return String(byId.complaints || byId.reason || "").trim();
    for (const row of Object.values(lookups.mediocreById)) {
      if (normalizeActressName(row.name) === normalizeActressName(actress.name)) {
        return String(row.complaints || row.reason || "").trim();
      }
    }
    return "";
  }

  function extractListRating(itemEl) {
    const scoreEl = itemEl.querySelector(".score");
    if (!scoreEl) return "";
    return scoreEl.textContent.replace(/\s+/g, " ").trim();
  }

  function extractListMagnetTag(itemEl) {
    for (const tag of itemEl.querySelectorAll(".tags .tag")) {
      const text = tag.textContent.replace(/\s+/g, " ").trim();
      if (/含磁|含中字|无磁/i.test(text)) return text;
    }
    return "";
  }

  function extractActressGuessFromTitle(title, code) {
    const normalizedCode = normalizeCode(code);
    if (!normalizedCode || !title) return [];
    const trimmed = title.trim();
    const codeRe = new RegExp(`^${normalizedCode.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*`, "i");
    if (!codeRe.test(trimmed)) return [];
    let rest = trimmed.replace(codeRe, "").trim().replace(/^[-–—:|]\s*/, "");
    if (!rest) return [];

    const guesses = [];
    const seen = new Set();
    const parts = rest.split(/[\s、，,/|]+/).filter(Boolean);
    for (const part of parts.slice(0, 4)) {
      if (!part || part.length > 18) continue;
      if (/^(第\d|【|\[|「|http)/.test(part)) break;
      if (/^[A-Z0-9][A-Z0-9.-]{4,}$/i.test(part) && /\d/.test(part)) continue;
      const key = normalizeActressName(part);
      if (seen.has(key)) continue;
      seen.add(key);
      guesses.push({ javdb_id: "", name: part, guessed: true });
      if (guesses.length >= 3) break;
    }
    return guesses;
  }

  function actressFetchPriority(itemEl) {
    if (!itemEl?.getBoundingClientRect) return 0;
    const rect = itemEl.getBoundingClientRect();
    if (rect.top < window.innerHeight && rect.bottom > 0) return 30;
    if (rect.top < window.innerHeight + 800) return 15;
    return 1;
  }

  function requestActressFetch(itemEl, meta, priority = 0) {
    const code = normalizeCode(meta?.code || "");
    if (!code) return;
    if (stickerData.actressByCode?.[code]?.length) return;
    if (actressFetchPending.has(code)) return;
    const detailUrl = meta?.detailUrl || "";
    if (!detailUrl.includes("/v/")) return;
    actressFetchPending.add(code);
    actressFetchQueue.push({ code, detailUrl, itemEl, meta, priority });
    actressFetchQueue.sort((a, b) => b.priority - a.priority);
    drainActressFetchQueue();
  }

  function ensureActressVisibilityObserver() {
    if (actressVisibilityObserver || !("IntersectionObserver" in window)) return;
    actressVisibilityObserver = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          const itemEl = entry.target;
          const meta = {
            code: itemEl.dataset.jmCode || "",
            detailUrl: itemEl.querySelector('a[href*="/v/"]')?.href || "",
            title: itemEl.querySelector(".video-title")?.textContent?.trim() || "",
          };
          requestActressFetch(itemEl, meta, 10);
          actressVisibilityObserver.unobserve(itemEl);
        }
      },
      { root: null, rootMargin: "1200px 0px", threshold: 0.01 }
    );
  }

  function observeActressFetch(itemEl, meta) {
    if (!meta?.code) return;
    const priority = Math.max(actressFetchPriority(itemEl), 0);
    requestActressFetch(itemEl, meta, priority);
    ensureActressVisibilityObserver();
    if (!actressVisibilityObserver || itemEl.dataset.jmActressObserved) return;
    itemEl.dataset.jmActressObserved = "1";
    actressVisibilityObserver.observe(itemEl);
  }

  function applyActressBatchResults(batch, results) {
    if (!results || typeof results !== "object") return false;
    let changed = false;
    for (const job of batch) {
      const actresses = results[job.code] || results[normalizeCode(job.code)];
      if (!Array.isArray(actresses) || !actresses.length) continue;
      if (!stickerData.actressByCode) stickerData.actressByCode = {};
      stickerData.actressByCode[job.code] = actresses;
      changed = true;
      if (document.contains(job.itemEl)) {
        renderListMetaRow(job.itemEl, job.meta);
      }
    }
    return changed;
  }

  function drainActressFetchQueue() {
    while (actressFetchActive < ACTRESS_FETCH_LIMIT && actressFetchQueue.length > 0) {
      const batch = actressFetchQueue.splice(0, ACTRESS_BATCH_SIZE);
      if (!batch.length) return;
      actressFetchActive++;
      sendRuntimeMessage({
        type: "detail_fetch_actresses_batch",
        items: batch.map((job) => ({ code: job.code, url: job.detailUrl })),
        concurrency: 12,
      }).then(async (res) => {
        actressFetchActive--;
        for (const job of batch) {
          actressFetchPending.delete(job.code);
        }
        if (res?.ok) {
          const changed = applyActressBatchResults(batch, res.results);
          if (changed) await saveLocalState();
        }
        drainActressFetchQueue();
      });
    }
  }

  function queueMissingActresses(items) {
    for (const itemEl of items) {
      const code = normalizeCode(itemEl.dataset.jmCode || "");
      if (!code) continue;
      if (stickerData.actressByCode?.[code]?.length) continue;
      const meta = parseStickerItem(itemEl);
      if (!meta.code) continue;
      requestActressFetch(itemEl, meta, actressFetchPriority(itemEl));
    }
  }

  function renderListMetaRow(itemEl, meta) {
    let actresses = parseActressesFromItem(itemEl);
    if (!actresses.length && meta?.code) {
      actresses = stickerData.actressByCode?.[normalizeCode(meta.code)] || [];
    }

    let row = itemEl.querySelector(".jm-list-meta-row");
    const rating = extractListRating(itemEl);
    const releaseDate = meta?.releaseDate || extractReleaseDate(itemEl);
    const magnetTag = extractListMagnetTag(itemEl);
    const hasMeta = actresses.length || rating || releaseDate || magnetTag;

    if (!hasMeta) {
      itemEl.querySelector(".jm-list-meta-row")?.remove();
      itemEl.classList.remove("jm-has-list-meta");
      return;
    }

    const lookups = buildActressLookups();
    if (!row) {
      row = document.createElement("div");
      row.className = "jm-list-meta-row";
      const bar = itemEl.querySelector(".jm-sticker-actions");
      if (bar) bar.insertAdjacentElement("beforebegin", row);
      else (itemEl.querySelector(".box") || itemEl).appendChild(row);
    }
    itemEl.classList.add("jm-has-list-meta");

    const actressHtml = actresses.length
      ? actresses
          .map((actress) => {
            const cls = getActressDisplayClass(actress, lookups) || "jm-actress-default";
            const reason = cls === "jm-actress-mediocre" ? getMediocreReason(actress, lookups) : "";
            const titleAttr = reason ? ` title="${escapeHtmlAttr(reason)}"` : "";
            const reasonHtml = reason
              ? ` <span class="jm-actress-mediocre-reason">(${escapeHtml(reason)})</span>`
              : "";
            return `<span class="jm-list-actress ${cls}"${titleAttr}>${escapeHtml(actress.name)}${reasonHtml}</span>`;
          })
          .join('<span class="jm-list-meta-sep">·</span>')
      : "";

    const bits = [];
    if (actressHtml) bits.push(`<span class="jm-list-meta-actresses">${actressHtml}</span>`);
    if (rating) bits.push(`<span class="jm-list-meta-rating">${escapeHtml(rating)}</span>`);
    if (releaseDate) bits.push(`<span class="jm-list-meta-date">${escapeHtml(releaseDate)}</span>`);
    if (magnetTag) bits.push(`<span class="jm-list-meta-magnet">${escapeHtml(magnetTag)}</span>`);

    const nextHtml = bits.join('<span class="jm-list-meta-sep">·</span>');
    if (row.dataset.jmMetaHtml !== nextHtml) {
      row.dataset.jmMetaHtml = nextHtml;
      row.innerHTML = nextHtml;
    }

    if (meta?.code) {
      const cached = stickerData.actressByCode?.[normalizeCode(meta.code)] || [];
      const needsFetch = !cached.length || cached.every((row) => row.guessed);
      if (needsFetch) observeActressFetch(itemEl, meta);
    }
  }

  function renderListActresses(itemEl, meta) {
    renderListMetaRow(itemEl, meta);
  }

  function renderVerifiedHistoryTable(container) {
    const rows = Object.values(stickerData.verified || {}).sort((a, b) =>
      String(b.recorded_at || "").localeCompare(String(a.recorded_at || ""))
    );
    if (!rows.length) {
      container.innerHTML = `<p class="jm-verified-empty">暂无已鉴定记录</p>`;
      return;
    }
    container.innerHTML = `
      <table class="jm-verified-table">
        <thead>
          <tr>
            <th>番号</th>
            <th>标题</th>
            <th>发行</th>
            <th>记录时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
            <tr>
              <td>${escapeHtml(row.code || "-")}</td>
              <td>${escapeHtml(row.title || "-")}</td>
              <td>${escapeHtml(row.release_date || "-")}</td>
              <td>${escapeHtml(row.recorded_at || "-")}</td>
              <td>
                ${
                  row.detail_url
                    ? `<a href="${escapeHtmlAttr(row.detail_url)}" target="_blank" rel="noopener">详情</a> `
                    : ""
                }
                <button type="button" class="jm-verified-delete" data-code="${escapeHtmlAttr(row.code || "")}">删除</button>
              </td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>
    `;
    container.querySelectorAll(".jm-verified-delete").forEach((btn) => {
      btn.addEventListener("click", () => removeVerifiedRecord(btn.dataset.code));
    });
  }

  async function removeVerifiedRecord(code) {
    const normalized = normalizeCode(code);
    if (!normalized) return;
    if (!confirm(`确定删除 ${normalized} 的鉴定记录？`)) return;

    delete stickerData.verified[normalized];
    await saveLocalState();
    sendToDesktop("unverified", { code: normalized });
    applyAllVisibility();
    document.querySelectorAll(`.jm-sticker-item[data-jm-code="${normalized}"]`).forEach((itemEl) => {
      applyItemVisibility(normalized, itemEl, itemEl.querySelector(".video-title")?.textContent?.trim() || "");
    });
    const wrap = document.getElementById("jm-verified-table-wrap");
    if (wrap) renderVerifiedHistoryTable(wrap);
    showJmToast(`已删除 ${normalized} 的鉴定记录`, "done");
  }

  function openVerifiedHistoryModal() {
    let modal = document.getElementById("jm-verified-history-modal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "jm-verified-history-modal";
      modal.innerHTML = `
        <div class="jm-modal-dialog" role="dialog">
          <div class="jm-modal-header">
            <h4>鉴定记录</h4>
            <button type="button" class="jm-modal-close" aria-label="关闭">×</button>
          </div>
          <div class="jm-verified-table-wrap" id="jm-verified-table-wrap"></div>
        </div>
      `;
      document.body.appendChild(modal);
      modal.querySelector(".jm-modal-close").addEventListener("click", () => modal.classList.remove("jm-visible"));
      modal.addEventListener("click", (e) => {
        if (e.target === modal) modal.classList.remove("jm-visible");
      });
    }
    renderVerifiedHistoryTable(modal.querySelector("#jm-verified-table-wrap"));
    modal.classList.add("jm-visible");
  }

  function openNewWorksCheckModal() {
    let modal = document.getElementById("jm-new-works-modal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "jm-new-works-modal";
      modal.innerHTML = `
        <div class="jm-modal-dialog jm-new-works-dialog" role="dialog">
          <div class="jm-modal-header">
            <h4>收藏女优新作检测</h4>
            <button type="button" class="jm-modal-close" aria-label="关闭">×</button>
          </div>
          <div class="jm-new-works-toolbar">
            <button type="button" class="jm-toolbar-btn jm-nw-sync">同步收藏女优</button>
            <button type="button" class="jm-toolbar-btn jm-nw-back" hidden>返回列表</button>
            <button type="button" class="jm-toolbar-btn jm-toolbar-verified">鉴定记录</button>
          </div>
          <div class="jm-new-works-body" id="jm-new-works-body">
            <p>请先同步收藏女优，再点击头像开始检测。</p>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
      modal.querySelector(".jm-modal-close").addEventListener("click", () => modal.classList.remove("jm-visible"));
      modal.addEventListener("click", (e) => {
        if (e.target === modal) modal.classList.remove("jm-visible");
      });
      modal.querySelector(".jm-nw-sync").addEventListener("click", () => {
        const body = modal.querySelector("#jm-new-works-body");
        body.innerHTML = `<p class="jm-hint">正在同步收藏女优…</p>`;
        void sendRuntimeMessage({ type: "sync_actresses", force: true }).then((result) => {
          if (result?.invalidated) {
            body.innerHTML = `<p>扩展已更新，请刷新页面后重试。</p>`;
            return;
          }
          if (result?.ok) {
            renderNewWorksActressGrid(modal);
            return;
          }
          body.innerHTML = `<p>${escapeHtml(result?.message || "同步失败")}</p>`;
        });
      });
      modal.querySelector(".jm-nw-back").addEventListener("click", () => {
        modal.querySelector(".jm-nw-back").hidden = true;
        renderNewWorksActressGrid(modal);
      });
      modal.querySelector(".jm-toolbar-verified").addEventListener("click", () => openVerifiedHistoryModal());
    }
    modal.classList.add("jm-visible");
    modal.querySelector(".jm-nw-back").hidden = true;
    renderNewWorksActressGrid(modal);
  }

  function renderNewWorksActressGrid(modal) {
    const body = modal.querySelector("#jm-new-works-body");
    const actresses = Object.values(stickerData.collectedActresses || {}).sort((a, b) =>
      String(a.name || "").localeCompare(String(b.name || ""), "zh-CN")
    );
    if (!actresses.length) {
      body.innerHTML = `<p>暂无收藏女优，请先点击「同步收藏女优」。</p>`;
      return;
    }
    body.innerHTML = `
      <p class="jm-hint">共 ${actresses.length} 位收藏女优。点击头像检测该女优作品页上仍可见的预览贴纸。</p>
      <div class="jm-new-works-actress-grid">
        ${actresses
          .map((actress) => {
            const id = String(actress.javdb_id || actress.id || actress.starId || "").trim();
            const name = String(actress.name || id || "未知").trim();
            const avatar = String(actress.avatar_url || "").trim();
            const avatarHtml = avatar
              ? `<img src="${escapeHtmlAttr(avatar)}" alt="${escapeHtmlAttr(name)}" class="jm-nw-avatar-img">`
              : `<span class="jm-nw-avatar-fallback">${escapeHtml(name.slice(0, 1) || "?")}</span>`;
            return `
              <button type="button" class="jm-new-works-actress-card" data-javdb-id="${escapeHtmlAttr(id)}" title="${escapeHtmlAttr(name)}">
                ${avatarHtml}
                <span class="jm-new-works-actress-name">${escapeHtml(name)}</span>
              </button>`;
          })
          .join("")}
      </div>
    `;
    body.querySelectorAll(".jm-new-works-actress-card").forEach((btn) => {
      btn.addEventListener("click", () => {
        const javdbId = btn.getAttribute("data-javdb-id") || "";
        const actress = (stickerData.collectedActresses || {})[javdbId];
        if (!actress) return;
        runActressVisibleStickerDetect(modal, actress);
      });
    });
  }

  function renderActressDetectResults(modal, actress, items) {
    const body = modal.querySelector("#jm-new-works-body");
    const backBtn = modal.querySelector(".jm-nw-back");
    backBtn.hidden = false;
    const name = String(actress.name || actress.javdb_id || "未知").trim();
    const profileUrl =
      String(actress.profile_url || "").trim() ||
      (actress.javdb_id ? `https://javdb.com/actors/${encodeURIComponent(actress.javdb_id)}` : "");
    if (!items.length) {
      body.innerHTML = `
        <div class="jm-new-works-detect-head">
          <h5>${escapeHtml(name)}</h5>
          ${
            profileUrl
              ? `<a class="jm-toolbar-btn jm-nw-open-profile" href="${escapeHtmlAttr(profileUrl)}" target="_blank" rel="noopener">打开女优详情页</a>`
              : ""
          }
        </div>
        <p class="jm-hint">未发现仍可见的预览贴纸（可能已全部屏蔽/鉴定/已下载，或列表为空）。</p>
      `;
      return;
    }
    body.innerHTML = `
      <div class="jm-new-works-detect-head">
        <h5>${escapeHtml(name)} · 可见 ${items.length} 部</h5>
        ${
          profileUrl
            ? `<a class="jm-toolbar-btn jm-nw-open-profile" href="${escapeHtmlAttr(profileUrl)}" target="_blank" rel="noopener">打开女优详情页</a>`
            : ""
        }
      </div>
      <div class="jm-new-works-sticker-grid">
        ${items
          .map((item) => {
            const code = normalizeCode(item.code || "");
            const title = String(item.title || code).trim();
            const detailUrl = String(item.detailUrl || item.detail_url || "").trim();
            const coverUrl = String(item.coverUrl || item.cover_url || "").trim();
            const coverHtml = coverUrl
              ? `<img src="${escapeHtmlAttr(coverUrl)}" alt="${escapeHtmlAttr(code)}" class="jm-nw-sticker-cover">`
              : `<span class="jm-nw-sticker-cover-fallback">${escapeHtml(code)}</span>`;
            const openHtml = detailUrl
              ? `<a href="${escapeHtmlAttr(detailUrl)}" target="_blank" rel="noopener" class="jm-nw-sticker-link">${escapeHtml(code)}</a>`
              : `<span class="jm-nw-sticker-link">${escapeHtml(code)}</span>`;
            return `
              <div class="jm-new-works-sticker-card">
                ${coverHtml}
                <div class="jm-new-works-sticker-meta">
                  ${openHtml}
                  <p title="${escapeHtmlAttr(title)}">${escapeHtml(title.slice(0, 48))}</p>
                </div>
              </div>`;
          })
          .join("")}
      </div>
    `;
  }

  function runActressVisibleStickerDetect(modal, actress) {
    const body = modal.querySelector("#jm-new-works-body");
    const profileUrl =
      String(actress.profile_url || "").trim() ||
      (actress.javdb_id ? `https://javdb.com/actors/${encodeURIComponent(actress.javdb_id)}` : "");
    if (!profileUrl) {
      body.innerHTML = `<p>无法识别该女优的主页地址。</p>`;
      return;
    }
    body.innerHTML = `<p class="jm-hint">正在加载 ${escapeHtml(actress.name || "女优")} 的作品列表…</p>`;
    modal.querySelector(".jm-nw-back").hidden = false;
    void sendRuntimeMessage({
      type: "fetch_actress_page_items",
      profileUrl,
      javdbId: actress.javdb_id || actress.id || actress.starId || "",
    }).then((res) => {
      if (res?.invalidated) {
        body.innerHTML = `<p>扩展已更新，请刷新页面后重试。</p>`;
        return;
      }
      if (!res?.ok) {
        body.innerHTML = `<p>${escapeHtml(res?.message || "加载失败")}</p>`;
        return;
      }
      const visible = (res.items || []).filter((item) => {
        const code = normalizeCode(item.code || "");
        if (!code) return false;
        return !shouldHide(code, String(item.title || ""));
      });
      renderActressDetectResults(modal, actress, visible);
    });
  }

  window.JM_openVerifiedHistory = openVerifiedHistoryModal;
  window.JM_openNewWorksCheck = openNewWorksCheckModal;

  async function loadLocalState() {
    try {
      const stored = await chrome.storage.local.get([DATA_KEY, SETTINGS_KEY, SHORTCUTS_KEY]);
      stickerData = {
        blocked: {},
        verified: {},
        downloaded: {},
        marked: {},
        blockedSeries: {},
        blockedTitleKeywords: {},
        blockedActresses: {},
        blockedActressSeries: {},
        mediocreActresses: {},
        collectedActresses: {},
        actressByCode: {},
        magnetSavedVideos: {},
        videoDownloadedVideos: {},
        videoCrackedVideos: {},
        ...(stored[DATA_KEY] || {}),
      };
      stickerData.blocked = normalizeStickerListMap(stickerData.blocked);
      stickerData.verified = normalizeStickerListMap(stickerData.verified);
      stickerData.downloaded = normalizeStickerListMap(stickerData.downloaded);
      stickerData.marked = normalizeStickerListMap(stickerData.marked);
      reconcileDownloadedHideState();
      stickerSettings = { ...DEFAULT_SETTINGS, ...(stored[SETTINGS_KEY] || {}) };
      for (const key of Object.keys(DEFAULT_SETTINGS)) {
        stickerSettings[key] = stickerSettings[key] === true;
      }
      stickerShortcuts = normalizeShortcuts(stored[SHORTCUTS_KEY]);
    } catch (_) {
      stickerData = {
        blocked: {},
        verified: {},
        downloaded: {},
        marked: {},
        blockedSeries: {},
        blockedTitleKeywords: {},
        blockedActresses: {},
        blockedActressSeries: {},
        mediocreActresses: {},
        collectedActresses: {},
        actressByCode: {},
        magnetSavedVideos: {},
        videoDownloadedVideos: {},
        videoCrackedVideos: {},
      };
      stickerSettings = { ...DEFAULT_SETTINGS };
      stickerShortcuts = { ...DEFAULT_SHORTCUTS };
    }
  }

  function normalizeStickerListMap(raw) {
    if (!raw) return {};
    if (Array.isArray(raw)) {
      const map = {};
      for (const row of raw) {
        if (!row?.code) continue;
        const code = normalizeCode(row.code);
        map[code] = { ...row, code };
      }
      return map;
    }
    if (typeof raw === "object") {
      const map = {};
      for (const [key, row] of Object.entries(raw)) {
        const code = normalizeCode(row?.code || key);
        if (!code) continue;
        map[code] = { ...(row || {}), code };
      }
      return map;
    }
    return {};
  }

  function reconcileDownloadedHideState() {
    if (!stickerData.downloaded || typeof stickerData.downloaded !== "object") {
      stickerData.downloaded = {};
    }
    for (const [code, rec] of Object.entries(stickerData.videoDownloadedVideos || {})) {
      const normalized = normalizeCode(code);
      if (!normalized) continue;
      if (stickerData.downloaded[normalized]) continue;
      stickerData.downloaded[normalized] = {
        code: normalized,
        title: String(rec?.title || ""),
        detail_url: String(rec?.detail_url || ""),
        page_url: String(rec?.detail_url || rec?.page_url || ""),
        recorded_at: String(rec?.recorded_at || ""),
      };
    }
  }

  function scheduleVisibilityPass() {
    const generation = ++visibilityPassGeneration;
    if (visibilityPassTimer) clearTimeout(visibilityPassTimer);
    const run = () => {
      if (generation !== visibilityPassGeneration) return;
      if (isListPage()) applyAllVisibility();
    };
    visibilityPassTimer = setTimeout(run, 80);
    for (const delay of [400, 1200, 3000]) {
      setTimeout(run, delay);
    }
  }

  async function saveLocalState() {
    try {
      reconcileDownloadedHideState();
      await chrome.storage.local.set({
        [DATA_KEY]: stickerData,
        [SETTINGS_KEY]: stickerSettings,
        [SHORTCUTS_KEY]: stickerShortcuts,
      });
    } catch (_) {
      /* ignore */
    }
  }

  function normalizeShortcuts(raw) {
    const merged = { ...DEFAULT_SHORTCUTS, ...(raw && typeof raw === "object" ? raw : {}) };
    const used = new Set();
    for (const key of Object.keys(DEFAULT_SHORTCUTS)) {
      let value = String(merged[key] || DEFAULT_SHORTCUTS[key]).trim().toLowerCase();
      if (value.length !== 1 || !/^[a-z0-9]$/.test(value)) {
        value = DEFAULT_SHORTCUTS[key];
      }
      while (used.has(value)) {
        value = DEFAULT_SHORTCUTS[key];
        break;
      }
      merged[key] = value;
      used.add(value);
    }
    return merged;
  }

  function buildRecord(meta, extra) {
    return {
      code: meta.code,
      title: meta.title,
      release_date: meta.releaseDate,
      detail_url: meta.detailUrl,
      page_url: meta.pageUrl,
      page_title: meta.pageTitle,
      recorded_at: nowString(),
      ...extra,
    };
  }

  function findExclusiveRecordKey(meta, cfg) {
    const bucket = stickerData[cfg.listKey] || {};
    if (cfg.useRawCode) {
      if (meta.code && bucket[meta.code]) return meta.code;
      const normalized = normalizeCode(meta.code);
      const hit = Object.keys(bucket).find((key) => normalizeCode(key) === normalized);
      return hit || "";
    }
    const codeKey = normalizeCode(meta.code);
    return bucket[codeKey] ? codeKey : "";
  }

  function getActiveExclusiveState(meta) {
    if (!meta?.code) return null;
    for (const actionKey of EXCLUSIVE_STATE_ORDER) {
      const cfg = EXCLUSIVE_STATE_CONFIG[actionKey];
      if (findExclusiveRecordKey(meta, cfg)) {
        return { actionKey, ...cfg };
      }
    }
    return null;
  }

  function updateStickerStatusTag(code, itemEl, titleEl) {
    const meta = { code: code || "" };
    const title =
      titleEl ||
      itemEl?.querySelector(".video-title") ||
      (isDetailPage() ? findDetailTitleEl() : null);
    if (!title) return;

    const active = getActiveExclusiveState(meta);
    let row = title.nextElementSibling;
    if (!row || !row.classList.contains("jm-status-row")) {
      row = title.parentElement?.querySelector(":scope > .jm-status-row") || null;
    }
    if (!active) {
      row?.remove();
      return;
    }
    if (!row) {
      row = document.createElement("div");
      row.className = "jm-status-row";
      title.insertAdjacentElement("afterend", row);
    }
    let tag = row.querySelector(".jm-status-tag");
    if (!tag) {
      tag = document.createElement("span");
      row.appendChild(tag);
    }
    tag.className = `jm-status-tag jm-status-${active.actionKey}`;
    tag.textContent = active.label;
  }

  function updateStickerStatusForMeta(meta, itemEl) {
    if (!meta?.code) return;
    const normalized = normalizeCode(meta.code);
    const el =
      itemEl ||
      itemElFromCode(normalized) ||
      itemElFromCode(meta.code);
    updateStickerStatusTag(meta.code, el, null);
    if (
      isDetailPage() &&
      detailPageMeta?.code &&
      normalizeCode(detailPageMeta.code) === normalized
    ) {
      updateStickerStatusTag(meta.code, null, findDetailTitleEl());
    }
  }

  async function clearOtherExclusiveStatesLocal(meta, keepActionKey) {
    for (const actionKey of EXCLUSIVE_STATE_ORDER) {
      if (actionKey === keepActionKey) continue;
      const cfg = EXCLUSIVE_STATE_CONFIG[actionKey];
      const storageKey = findExclusiveRecordKey(meta, cfg);
      if (!storageKey) continue;
      delete stickerData[cfg.listKey][storageKey];
      await sendToDesktop(cfg.removeAction, {
        code: cfg.useRawCode ? storageKey : normalizeCode(storageKey),
      });
    }
  }

  async function confirmExclusiveSwitch(fromLabel, toLabel) {
    return confirm(`该影片当前为「${fromLabel}」，是否切换为「${toLabel}」？`);
  }

  async function tryApplyExclusiveState(actionKey, meta, extra = {}) {
    const cfg = EXCLUSIVE_STATE_CONFIG[actionKey];
    if (!cfg || !meta?.code) {
      return { ok: false, message: "未能识别番号" };
    }

    const storageKey = findExclusiveRecordKey(meta, cfg);
    if (storageKey) {
      if (await removeListAction(cfg.listKey, cfg.removeAction, meta)) {
        updateStickerStatusForMeta(meta);
        applyAllVisibility();
        if (isDetailPage()) {
          closeCurrentDetailTab();
        }
        return { ok: true, toggledOff: true };
      }
      return { ok: false, message: "桌面数据库保存失败" };
    }

    const current = getActiveExclusiveState(meta);
    if (current && current.actionKey !== actionKey) {
      const confirmed = await confirmExclusiveSwitch(current.label, cfg.label);
      if (!confirmed) return { ok: false, cancelled: true };
      await removeListAction(current.listKey, current.removeAction, meta);
    }

    if (actionKey === "blocked") {
      openBlockModal(meta);
      return { ok: true, pending: true };
    }

    if (!(await persistListAction(cfg.listKey, cfg.persistAction, meta, extra))) {
      return { ok: false, message: "桌面数据库保存失败" };
    }
    updateStickerStatusForMeta(meta);
    closeDetailAfterListAction();
    return { ok: true };
  }

  function getListActionConfig(listKey) {
    return Object.entries(EXCLUSIVE_STATE_CONFIG).find(([, cfg]) => cfg.listKey === listKey)?.[1] || null;
  }

  function resolveListStorageKey(meta, listKey) {
    const cfg = getListActionConfig(listKey);
    if (cfg?.useRawCode) return meta.code || "";
    return normalizeCode(meta.code);
  }

  function sendToDesktop(action, record) {
    return sendRuntimeMessage({ type: "sticker_action", action, ...record }).then((response) => {
      if (response?.invalidated) return { ok: false, offline: true, invalidated: true };
      if (response?.offline) return { ok: false, offline: true };
      if (response?.ok === false) {
        return { ok: false, message: response.message || "桌面保存失败" };
      }
      return response || { ok: false, message: "empty_response" };
    });
  }

  async function persistListAction(listKey, action, meta, extra) {
    if (!meta.code) {
      alert("未能从标题识别番号，无法记录。");
      return false;
    }

    const keepActionKey = Object.entries(EXCLUSIVE_STATE_CONFIG).find(
      ([, cfg]) => cfg.listKey === listKey
    )?.[0];
    if (keepActionKey) {
      await clearOtherExclusiveStatesLocal(meta, keepActionKey);
    }

    const record = buildRecord(meta, extra);
    const codeKey = resolveListStorageKey(meta, listKey);
    const desktop = await sendToDesktop(action, record);
    if (!desktop?.offline && !desktop?.ok) {
      return false;
    }
    stickerData[listKey][codeKey] = record;
    await saveLocalState();
    applyItemVisibility(codeKey, itemElFromCode(normalizeCode(meta.code)), meta.title);
    updateStickerStatusForMeta(meta, itemElFromCode(normalizeCode(meta.code)));
    return true;
  }

  async function removeListAction(listKey, desktopAction, meta) {
    if (!meta.code) {
      alert("未能从标题识别番号，无法记录。");
      return false;
    }

    const cfg = getListActionConfig(listKey);
    const codeKey = cfg ? findExclusiveRecordKey(meta, cfg) : resolveListStorageKey(meta, listKey);
    if (!codeKey || !stickerData[listKey][codeKey]) return true;

    const desktop = await sendToDesktop(desktopAction, {
      code: cfg?.useRawCode ? codeKey : normalizeCode(codeKey),
    });
    if (!desktop?.offline && !desktop?.ok) {
      return false;
    }
    delete stickerData[listKey][codeKey];
    await saveLocalState();
    applyItemVisibility(normalizeCode(meta.code), itemElFromCode(normalizeCode(meta.code)), meta.title);
    updateStickerStatusForMeta(meta, itemElFromCode(normalizeCode(meta.code)));
    return true;
  }

  async function persistBlockedSeries(series, reason) {
    const normalized = normalizeSeriesInput(series);
    if (!normalized) {
      alert("请输入有效的番号系列，例如 ABC 或 ABC-123。");
      return false;
    }

    const record = {
      series: normalized,
      reason: reason || "",
      page_url: location.href,
      page_title: document.title,
      recorded_at: nowString(),
    };
    stickerData.blockedSeries[normalized] = record;
    await saveLocalState();
    sendToDesktop("block_series", record);
    renderBlockedSeriesList();
    applyAllVisibility();
    return true;
  }

  async function removeBlockedSeries(series) {
    const normalized = normalizeSeriesInput(series);
    if (!normalized || !stickerData.blockedSeries[normalized]) return;
    delete stickerData.blockedSeries[normalized];
    await saveLocalState();
    sendToDesktop("unblock_series", { series: normalized });
    renderBlockedSeriesList();
    applyAllVisibility();
  }

  async function persistBlockedTitleKeyword(keyword) {
    const normalized = String(keyword || "").trim();
    if (!normalized) {
      alert("请输入标题关键词。");
      return false;
    }

    const existing = Object.values(stickerData.blockedTitleKeywords || {}).find(
      (item) => String(item.keyword || "").toLowerCase() === normalized.toLowerCase()
    );
    if (existing) {
      alert(`关键词「${existing.keyword}」已存在。`);
      return false;
    }

    const record = {
      keyword: normalized,
      page_url: location.href,
      page_title: document.title,
      recorded_at: nowString(),
    };
    stickerData.blockedTitleKeywords[normalized] = record;
    await saveLocalState();
    sendToDesktop("block_title_keyword", record);
    applyAllVisibility();
    return true;
  }

  async function removeBlockedTitleKeyword(keyword) {
    const normalized = String(keyword || "").trim();
    if (!normalized) return;

    const entry = Object.entries(stickerData.blockedTitleKeywords || {}).find(
      ([, item]) => String(item.keyword || "").toLowerCase() === normalized.toLowerCase()
    );
    if (!entry) return;

    const [key, item] = entry;
    delete stickerData.blockedTitleKeywords[key];
    await saveLocalState();
    sendToDesktop("unblock_title_keyword", { keyword: item.keyword || key });
    applyAllVisibility();
  }

  function itemElFromCode(code) {
    if (!code) return null;
    return document.querySelector(`.jm-sticker-item[data-jm-code="${CSS.escape(code)}"]`);
  }

  async function removeMark(meta) {
    if (!meta.code) return;
    delete stickerData.marked[meta.code];
    await saveLocalState();
    sendToDesktop("unmarked", { code: meta.code });
    updateMarkUi(meta.code, false);
  }

  async function addMark(meta) {
    if (!meta.code) {
      alert("未能从标题识别番号，无法标记。");
      return;
    }
    const record = buildRecord(meta, {});
    stickerData.marked[meta.code] = record;
    await saveLocalState();
    sendToDesktop("marked", record);
    updateMarkUi(meta.code, true);
  }

  function titleContainsBlockedKeyword(title, keyword) {
    const haystack = String(title || "").normalize("NFKC");
    const needle = String(keyword || "").trim().normalize("NFKC");
    if (!haystack || !needle) return false;

    const hayLower = haystack.toLocaleLowerCase("en-US");
    const needleLower = needle.toLocaleLowerCase("en-US");
    const isAsciiWord = /^[a-z0-9]+$/i.test(needle);
    const isWordChar = (ch) => /[a-z0-9]/i.test(ch);

    let index = 0;
    while (index <= hayLower.length - needleLower.length) {
      const hit = hayLower.indexOf(needleLower, index);
      if (hit < 0) return false;
      if (!isAsciiWord) return true;

      const before = hit > 0 ? hayLower[hit - 1] : "";
      const after =
        hit + needleLower.length < hayLower.length ? hayLower[hit + needleLower.length] : "";
      if ((!before || !isWordChar(before)) && (!after || !isWordChar(after))) {
        return true;
      }
      index = hit + 1;
    }
    return false;
  }

  function isTitleKeywordBlocked(title) {
    const blocked = stickerData.blockedTitleKeywords || {};
    const keys = Object.keys(blocked);
    if (keys.length === 0) return false;

    const haystack = String(title || "").trim();
    if (!haystack) return false;

    for (const key of keys) {
      const keyword = String(blocked[key]?.keyword || key).trim();
      if (!keyword) continue;
      if (titleContainsBlockedKeyword(haystack, keyword)) return true;
    }
    return false;
  }

  function isStickerHiddenAsDownloaded(code) {
    const normalized = normalizeCode(code);
    if (!normalized) return false;
    if (stickerData.downloaded?.[normalized]) return true;
    for (const key of Object.keys(stickerData.downloaded || {})) {
      if (normalizeCode(key) === normalized) return true;
    }
    return Boolean(stickerData.videoDownloadedVideos?.[normalized]);
  }

  function shouldHide(code, title) {
    const normalized = normalizeCode(code) || code;
    if (stickerData.blocked[normalized] && !stickerSettings.showBlocked) return true;
    if (stickerData.verified[normalized] && !stickerSettings.showVerified) return true;
    if (isStickerHiddenAsDownloaded(normalized) && !stickerSettings.showDownloaded) return true;
    if (isSeriesBlocked(normalized, title) && !stickerSettings.showBlockedSeries) return true;
    if (isActressSeriesBlocked(normalized, title) && !stickerSettings.showBlockedActressSeries) return true;
    if (isTitleKeywordBlocked(title) && !stickerSettings.showBlockedTitleKeywords) return true;
    return false;
  }

  function isActressSeriesBlocked(code, title) {
    const blocked = stickerData.blockedActressSeries || {};
    if (Object.keys(blocked).length === 0) return false;
    const parsedCode = code || extractCode(title || "");
    const series = parsedCode ? extractSeries(parsedCode) : "";
    if (!series) return false;
    return Boolean(blocked[series.toUpperCase()]);
  }

  function applyItemVisibility(code, itemEl, title) {
    if (!itemEl) return;
    const resolvedTitle =
      title ||
      itemEl.querySelector(".video-title")?.textContent?.trim() ||
      "";
    const hidden = shouldHide(code, resolvedTitle);
    if (itemEl.classList.contains("jm-sticker-hidden") !== hidden) {
      itemEl.classList.toggle("jm-sticker-hidden", hidden);
    }
  }

  function updateMarkUi(code, marked) {
    const itemEl = itemElFromCode(code);
    if (!itemEl) return;
    const titleEl = itemEl.querySelector(".video-title");
    if (!titleEl) return;
    titleEl.classList.toggle("jm-title-marked", marked);
    let badge = titleEl.querySelector(".jm-mark-check");
    if (marked && !badge) {
      badge = document.createElement("span");
      badge.className = "jm-mark-check";
      badge.textContent = "✓";
      badge.title = "已标记";
      titleEl.appendChild(badge);
    } else if (!marked && badge) {
      badge.remove();
    }
    const markBtn = itemEl.querySelector(".jm-act-mark");
    if (markBtn) {
      markBtn.classList.toggle("jm-active", marked);
      markBtn.textContent = marked ? "取消标记" : "标记";
    }
  }

  function ensureBlockModal() {
    if (blockModal) return blockModal;

    blockModal = document.createElement("div");
    blockModal.id = "jm-block-modal";
    blockModal.innerHTML = `
      <div class="jm-block-dialog" role="dialog" aria-modal="true">
        <h4>屏蔽原因</h4>
        <p class="jm-block-code"></p>
        <textarea id="jm-block-reason" rows="4" placeholder="请输入屏蔽原因（可选）"></textarea>
        <div class="jm-block-buttons">
          <button type="button" id="jm-block-cancel">取消</button>
          <button type="button" id="jm-block-confirm">确认屏蔽</button>
        </div>
      </div>
    `;
    document.body.appendChild(blockModal);

    blockModal.querySelector("#jm-block-cancel").addEventListener("click", () => {
      blockModal.classList.remove("jm-visible");
      pendingBlockMeta = null;
    });

    blockModal.querySelector("#jm-block-confirm").addEventListener("click", async () => {
      if (!pendingBlockMeta) return;
      const reason = blockModal.querySelector("#jm-block-reason").value.trim();
      const meta = pendingBlockMeta;
      blockModal.classList.remove("jm-visible");
      pendingBlockMeta = null;
      const ok = await persistListAction("blocked", "blocked", meta, { reason });
      if (!ok) return;
      updateStickerStatusForMeta(meta);
      closeDetailAfterListAction();
    });

    blockModal.addEventListener("click", (e) => {
      if (e.target === blockModal) {
        blockModal.classList.remove("jm-visible");
        pendingBlockMeta = null;
      }
    });

    return blockModal;
  }

  function openBlockModal(meta) {
    if (!meta.code) {
      alert("未能从标题识别番号，无法屏蔽。");
      return;
    }
    const modal = ensureBlockModal();
    modal.querySelector(".jm-block-code").textContent = meta.code;
    modal.querySelector("#jm-block-reason").value = "";
    pendingBlockMeta = meta;
    modal.classList.add("jm-visible");
    modal.querySelector("#jm-block-reason").focus();
  }

  function ensureSeriesModal() {
    if (seriesModal) return seriesModal;

    seriesModal = document.createElement("div");
    seriesModal.id = "jm-series-modal";
    seriesModal.innerHTML = `
      <div class="jm-block-dialog" role="dialog" aria-modal="true">
        <h4>屏蔽番号系列</h4>
        <p class="jm-hint">输入系列前缀，例如 ABC-123 中的 ABC。该系列所有贴纸将被隐藏。</p>
        <input type="text" id="jm-series-input" placeholder="例如 ABC 或 SSIS" />
        <textarea id="jm-series-reason" rows="3" placeholder="屏蔽原因（可选）"></textarea>
        <div class="jm-block-buttons">
          <button type="button" id="jm-series-cancel">取消</button>
          <button type="button" id="jm-series-confirm">确认屏蔽系列</button>
        </div>
      </div>
    `;
    document.body.appendChild(seriesModal);

    seriesModal.querySelector("#jm-series-cancel").addEventListener("click", () => {
      seriesModal.classList.remove("jm-visible");
    });

    seriesModal.querySelector("#jm-series-confirm").addEventListener("click", async () => {
      const series = seriesModal.querySelector("#jm-series-input").value.trim();
      const reason = seriesModal.querySelector("#jm-series-reason").value.trim();
      const ok = await persistBlockedSeries(series, reason);
      if (ok) {
        seriesModal.classList.remove("jm-visible");
        seriesModal.querySelector("#jm-series-input").value = "";
        seriesModal.querySelector("#jm-series-reason").value = "";
      }
    });

    seriesModal.addEventListener("click", (e) => {
      if (e.target === seriesModal) seriesModal.classList.remove("jm-visible");
    });

    return seriesModal;
  }

  function openSeriesModal() {
    const modal = ensureSeriesModal();
    modal.querySelector("#jm-series-input").value = "";
    modal.querySelector("#jm-series-reason").value = "";
    modal.classList.add("jm-visible");
    modal.querySelector("#jm-series-input").focus();
  }

  function renderBlockedSeriesList() {
    const listEl = document.getElementById("jm-blocked-series-list");
    if (!listEl) return;

    const entries = Object.values(stickerData.blockedSeries || {});
    if (entries.length === 0) {
      listEl.innerHTML = `<p class="jm-series-empty">暂无已屏蔽系列</p>`;
      return;
    }

    listEl.innerHTML = entries
      .sort((a, b) => String(b.recorded_at).localeCompare(String(a.recorded_at)))
      .map(
        (item) => `
        <div class="jm-series-item">
          <span class="jm-series-name">${item.series}</span>
          <button type="button" class="jm-series-remove" data-series="${item.series}" title="取消屏蔽">×</button>
        </div>
      `
      )
      .join("");

    listEl.querySelectorAll(".jm-series-remove").forEach((btn) => {
      btn.addEventListener("click", () => removeBlockedSeries(btn.dataset.series));
    });
  }

  function ensureTitleKeywordModal() {
    if (titleKeywordModal) return titleKeywordModal;

    titleKeywordModal = document.createElement("div");
    titleKeywordModal.id = "jm-title-keyword-modal";
    titleKeywordModal.innerHTML = `
      <div class="jm-block-dialog" role="dialog" aria-modal="true">
        <h4>屏蔽标题关键词</h4>
        <p class="jm-hint">标题中包含该关键词的预览贴纸将被隐藏（不区分大小写）。</p>
        <input type="text" id="jm-title-keyword-input" placeholder="例如 中字、合集、VR" />
        <div class="jm-block-buttons">
          <button type="button" id="jm-title-keyword-cancel">取消</button>
          <button type="button" id="jm-title-keyword-confirm">确认</button>
        </div>
      </div>
    `;
    document.body.appendChild(titleKeywordModal);

    titleKeywordModal.querySelector("#jm-title-keyword-cancel").addEventListener("click", () => {
      titleKeywordModal.classList.remove("jm-visible");
    });

    titleKeywordModal.querySelector("#jm-title-keyword-confirm").addEventListener("click", async () => {
      const keyword = titleKeywordModal.querySelector("#jm-title-keyword-input").value.trim();
      const ok = await persistBlockedTitleKeyword(keyword);
      if (ok) {
        titleKeywordModal.classList.remove("jm-visible");
        titleKeywordModal.querySelector("#jm-title-keyword-input").value = "";
      }
    });

    titleKeywordModal.addEventListener("click", (e) => {
      if (e.target === titleKeywordModal) titleKeywordModal.classList.remove("jm-visible");
    });

    return titleKeywordModal;
  }

  function openTitleKeywordModal() {
    const modal = ensureTitleKeywordModal();
    modal.querySelector("#jm-title-keyword-input").value = "";
    modal.classList.add("jm-visible");
    modal.querySelector("#jm-title-keyword-input").focus();
  }

  function renderTitleKeywordRemoveList() {
    const listEl = document.getElementById("jm-title-keyword-remove-list");
    if (!listEl) return;

    const entries = Object.values(stickerData.blockedTitleKeywords || {});
    if (entries.length === 0) {
      listEl.innerHTML = `<p class="jm-series-empty">暂无已屏蔽的标题关键词</p>`;
      return;
    }

    listEl.innerHTML = entries
      .sort((a, b) => String(b.recorded_at).localeCompare(String(a.recorded_at)))
      .map(
        (item) => `
        <div class="jm-series-item">
          <span class="jm-series-name">${item.keyword}</span>
          <button type="button" class="jm-series-remove" data-keyword="${item.keyword}" title="删除关键词">×</button>
        </div>
      `
      )
      .join("");

    listEl.querySelectorAll(".jm-series-remove").forEach((btn) => {
      btn.addEventListener("click", async () => {
        await removeBlockedTitleKeyword(btn.dataset.keyword);
        renderTitleKeywordRemoveList();
      });
    });
  }

  function ensureTitleKeywordRemoveModal() {
    if (titleKeywordRemoveModal) return titleKeywordRemoveModal;

    titleKeywordRemoveModal = document.createElement("div");
    titleKeywordRemoveModal.id = "jm-title-keyword-remove-modal";
    titleKeywordRemoveModal.innerHTML = `
      <div class="jm-block-dialog jm-block-dialog-wide" role="dialog" aria-modal="true">
        <h4>删减标题关键词</h4>
        <p class="jm-hint">点击 × 删除对应关键词，删除后相关贴纸将重新显示。</p>
        <div id="jm-title-keyword-remove-list" class="jm-title-keyword-remove-list"></div>
        <div class="jm-block-buttons">
          <button type="button" id="jm-title-keyword-remove-close">关闭</button>
        </div>
      </div>
    `;
    document.body.appendChild(titleKeywordRemoveModal);

    titleKeywordRemoveModal.querySelector("#jm-title-keyword-remove-close").addEventListener("click", () => {
      titleKeywordRemoveModal.classList.remove("jm-visible");
    });

    titleKeywordRemoveModal.addEventListener("click", (e) => {
      if (e.target === titleKeywordRemoveModal) titleKeywordRemoveModal.classList.remove("jm-visible");
    });

    return titleKeywordRemoveModal;
  }

  function openTitleKeywordRemoveModal() {
    const modal = ensureTitleKeywordRemoveModal();
    renderTitleKeywordRemoveList();
    modal.classList.add("jm-visible");
  }

  function showPlaceholder(label) {
    alert(`${label} 功能稍后实现。`);
  }

  function scrapeActressFromDetailPage() {
    const anchor =
      document.querySelector('.movie-panel-info a[href*="/actors/"], .movie-panel-info a[href*="/stars/"]') ||
      document.querySelector('.video-meta-panel a[href*="/actors/"], .video-meta-panel a[href*="/stars/"]');
    return (anchor?.textContent || "").trim();
  }

  function scrapeJavdbMagnetsForTxt() {
    const root = document.querySelector("#magnets-content");
    if (!root) return [];
    const rows = root.querySelectorAll(".item.columns.is-desktop, .item.columns, #magnets-content > .item");
    const magnets = [];
    rows.forEach((rowEl) => {
      if (rowEl.classList.contains("jm-magnet-hidden") || rowEl.style.display === "none") return;
      const nameEl = rowEl.querySelector(".magnet-name .name, .name");
      const title = (nameEl?.textContent || "").replace(/\s+/g, " ").trim();
      const previewEl = rowEl.querySelector(".jm-magnet-file-preview");
      const preview = (previewEl?.textContent || "").trim();
      const magnetEl = rowEl.querySelector("[data-clipboard-text*='magnet:'], a[href^='magnet:']");
      const magnet =
        magnetEl?.getAttribute("data-clipboard-text") || magnetEl?.getAttribute("href") || "";
      if (!title || !magnet.startsWith("magnet:")) return;
      magnets.push({ title, preview, magnet });
    });
    return magnets;
  }

  function runGenerateMagnetTxt(meta) {
    if (!meta.code) {
      showJmToast("未能识别番号，无法生成 TXT。", "error");
      return;
    }

    queueAsyncDetailClose(meta, "gentxt");
    void sendRuntimeMessage({
      type: "generate_magnet_txt_start",
      code: meta.code,
      detailUrl: meta.detailUrl || location.href,
      javdbMagnets: scrapeJavdbMagnetsForTxt(),
      actress: scrapeActressFromDetailPage(),
      title: meta.title || "",
    }).then((response) => {
      if (response?.invalidated) {
        clearAsyncDetailClose(meta.code);
        showJmToast("扩展已更新，请刷新页面后重试。", "error");
        return;
      }
      if (response?.ok && response.started) {
        showJmToast(
          `${meta.code}：正在执行 4K / 字幕 / 高清磁链筛查，完成后将通过通知提示。`,
          "running"
        );
        return;
      }
      clearAsyncDetailClose(meta.code);
      showJmToast(response?.message || "无法启动生成 TXT 任务", "error");
    });
  }

  function createActionBar(itemEl, meta) {
    if (itemEl.querySelector(".jm-sticker-actions")) return;

    const bar = createActionBarElement();
    attachActionBarHandlers(bar, meta);

    const box = itemEl.querySelector(".box") || itemEl;
    const tags = box.querySelector(".tags");
    if (tags && tags.parentElement === box) {
      tags.insertAdjacentElement("afterend", bar);
    } else {
      box.appendChild(bar);
    }
  }

  function reorderDetailActionButtons(bar) {
    const verified = bar.querySelector(".jm-act-verified");
    const gentxt = bar.querySelector(".jm-act-gentxt");
    const save115 = bar.querySelector(".jm-act-save115");
    if (verified && gentxt) verified.insertAdjacentElement("afterend", gentxt);
    if (gentxt && save115) gentxt.insertAdjacentElement("afterend", save115);
  }

  function injectDetailPageActionBar() {
    if (!isDetailPage()) return;
    detailPageMeta = parseDetailPageMeta();
    if (!detailPageMeta.code) return;

    if (typeof window.__JM_layoutDetailActionBar === "function") {
      window.__JM_layoutDetailActionBar();
    }

    let bar = document.getElementById("jm-detail-sticker-actions");
    if (bar && !bar.querySelector(".jm-act-magnet")) {
      bar.remove();
      bar = null;
    }
    const createdBar = !bar;
    if (!bar) {
      bar = createActionBarElement();
      bar.id = "jm-detail-sticker-actions";
      bar.classList.add("jm-detail-sticker-actions");
      reorderDetailActionButtons(bar);
      attachActionBarHandlers(bar, detailPageMeta);

      if (stickerData.marked[detailPageMeta.code]) {
        const markBtn = bar.querySelector(".jm-act-mark");
        if (markBtn) {
          markBtn.classList.add("jm-active");
          markBtn.textContent = `取消标记${shortcutHint("marked")}`;
        }
      }

      const actionsRow =
        document.getElementById("jm-detail-actions-row") ||
        (typeof window.__JM_ensureDetailActionsRow === "function"
          ? window.__JM_ensureDetailActionsRow(document.querySelector(".video-detail"))
          : null);
      const anchor =
        actionsRow ||
        document.querySelector(".movie-panel-info") ||
        document.querySelector(".video-detail") ||
        document.querySelector(".column-video-cover") ||
        document.querySelector("h2.title")?.parentElement;
      if (anchor) {
        anchor.appendChild(bar);
      } else {
        document.body.insertAdjacentElement("afterbegin", bar);
      }
      if (typeof window.__JM_relocateDetailActionBar === "function") {
        window.__JM_relocateDetailActionBar();
      }
    } else {
      updateActionBarShortcutLabels(bar);
      if (detailPageMeta.code && stickerData.marked[detailPageMeta.code]) {
        const markBtn = bar.querySelector(".jm-act-mark");
        if (markBtn) {
          markBtn.classList.add("jm-active");
          markBtn.textContent = `取消标记${shortcutHint("marked")}`;
        }
      }
    }
    cacheActressesForCode(detailPageMeta.code);
    updateStickerStatusTag(detailPageMeta.code, null, findDetailTitleEl());
    if (
      createdBar &&
      detailEnhanceBootstrappedCode !== detailPageMeta.code &&
      typeof window.__JM_refreshDetailEnhance === "function"
    ) {
      detailEnhanceBootstrappedCode = detailPageMeta.code;
      window.__JM_refreshDetailEnhance(detailPageMeta.code);
    }
  }

  function mountHeaderToolsGroup(group) {
    const navbarEnd =
      document.querySelector(".navbar .navbar-end") ||
      document.querySelector("#navbar-menu .navbar-end") ||
      document.querySelector(".navbar-menu .navbar-end");
    if (navbarEnd) {
      group.classList.add("jm-header-tools-inline");
      if (group.parentElement !== navbarEnd) {
        navbarEnd.insertBefore(group, navbarEnd.firstChild);
      }
      return;
    }
    group.classList.remove("jm-header-tools-inline");
    if (group.parentElement !== document.body) {
      document.body.appendChild(group);
    }
  }

  function ensureHeaderToolsGroup() {
    const settingsBtn = document.getElementById("jm-javdb-settings-btn");
    if (!settingsBtn) return null;
    let group = document.getElementById("jm-header-tools");
    if (!group) {
      group = document.createElement("div");
      group.id = "jm-header-tools";
      group.className = "jm-header-tools";
      document.body.appendChild(group);
    }
    if (settingsBtn.parentElement !== group) {
      group.appendChild(settingsBtn);
    }
    mountHeaderToolsGroup(group);
    return group;
  }

  function injectListPageToolbar() {
    if (!isListPage()) {
      document.getElementById("jm-list-toolbar")?.remove();
      const group = document.getElementById("jm-header-tools");
      const settingsBtn = document.getElementById("jm-javdb-settings-btn");
      if (group && settingsBtn && settingsBtn.parentElement === group) {
        document.body.appendChild(settingsBtn);
      }
      group?.remove();
      return;
    }
    const group = ensureHeaderToolsGroup();
    if (!group) return;
    let bar = document.getElementById("jm-list-toolbar");
    if (bar && bar.parentElement?.id !== "jm-header-tools") {
      bar.remove();
      bar = null;
    }
    if (bar) {
      mountHeaderToolsGroup(group);
      return;
    }
    mountHeaderToolsGroup(group);
    bar = document.createElement("div");
    bar.id = "jm-list-toolbar";
    bar.className = "jm-list-toolbar";
    bar.innerHTML = `
      <button type="button" class="jm-list-tool-btn" id="jm-list-verified-btn">鉴定记录</button>
      <button type="button" class="jm-list-tool-btn" id="jm-list-newworks-btn">检测新作</button>
    `;
    group.insertBefore(bar, group.firstChild);
    bar.querySelector("#jm-list-verified-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      openVerifiedHistoryModal();
    });
    bar.querySelector("#jm-list-newworks-btn").addEventListener("click", (e) => {
      e.stopPropagation();
      openNewWorksCheckModal();
    });
  }

  function ensureExtraSettingsButtons(grid) {
    const toolsBlock = grid.querySelector("#jm-sticker-settings-tools");
    if (!toolsBlock) return;
    if (!toolsBlock.querySelector("#jm-verified-history-btn")) {
      const syncBtn = toolsBlock.querySelector("#jm-sync-actresses-btn");
      const verifiedBtn = document.createElement("button");
      verifiedBtn.type = "button";
      verifiedBtn.id = "jm-verified-history-btn";
      verifiedBtn.className = "jm-settings-action jm-settings-action-compact jm-settings-action-secondary";
      verifiedBtn.textContent = "鉴定记录";
      verifiedBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        openVerifiedHistoryModal();
      });
      syncBtn?.insertAdjacentElement("afterend", verifiedBtn);
    }
    if (!toolsBlock.querySelector("#jm-check-new-works-btn")) {
      const verifiedBtn = toolsBlock.querySelector("#jm-verified-history-btn");
      const newWorksBtn = document.createElement("button");
      newWorksBtn.type = "button";
      newWorksBtn.id = "jm-check-new-works-btn";
      newWorksBtn.className = "jm-settings-action jm-settings-action-compact jm-settings-action-secondary";
      newWorksBtn.textContent = "检测收藏女优新作";
      newWorksBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        openNewWorksCheckModal();
      });
      verifiedBtn?.insertAdjacentElement("afterend", newWorksBtn);
    }
    if (!grid.querySelector("#jm-sticker-settings-backup")) {
      const backupBlock = document.createElement("section");
      backupBlock.id = "jm-sticker-settings-backup";
      backupBlock.className = "jm-settings-block";
      backupBlock.innerHTML = `
        <h3>115 数据库备份</h3>
        <p class="jm-hint">桌面端配置 115 WebDAV 后，将每天自动备份 jav_manager_state.db 到网盘。当前可在本地生成备份副本。</p>
        <button type="button" id="jm-backup-local-btn" class="jm-settings-action jm-settings-action-compact jm-settings-action-blue">生成本地备份</button>
        <p id="jm-backup-status" class="jm-actress-sync-status">尚未执行备份</p>
      `;
      grid.appendChild(backupBlock);
      backupBlock.querySelector("#jm-backup-local-btn")?.addEventListener("click", (e) => {
        e.stopPropagation();
        void sendRuntimeMessage({ type: "backup_db_local" }).then((res) => {
          const el = document.getElementById("jm-backup-status");
          if (!el) return;
          if (res?.invalidated) {
            el.textContent = "扩展已更新，请刷新页面后重试。";
            return;
          }
          el.textContent = res?.ok
            ? `本地备份已创建：${res.path || "成功"}`
            : res?.message || "备份失败（请确认桌面端已运行）";
        });
      });
    }
  }

  function decorateItems() {
    const items = findVideoItems();
    for (const itemEl of items) {
      const meta = parseStickerItem(itemEl);
      if (meta.code) {
        itemEl.classList.add("jm-sticker-item");
        if (itemEl.dataset.jmCode !== meta.code) {
          itemEl.dataset.jmCode = meta.code;
        }
      } else {
        itemEl.classList.add("jm-sticker-item");
        itemEl.removeAttribute("data-jm-code");
      }

      if (!itemEl.querySelector(".jm-sticker-actions")) {
        createActionBar(itemEl, meta);
      }

      if (meta.code) {
        applyItemVisibility(meta.code, itemEl, meta.title);
        updateMarkUi(meta.code, Boolean(stickerData.marked[meta.code]));
        updateStickerStatusTag(meta.code, itemEl);
        renderListActresses(itemEl, meta);
      } else {
        applyItemVisibility("", itemEl, meta.title);
      }
    }
    queueMissingActresses(items);
  }

  function applyAllVisibility() {
    for (const itemEl of findVideoItems()) {
      const meta = parseStickerItem(itemEl);
      if (meta.code) {
        itemEl.classList.add("jm-sticker-item");
        if (itemEl.dataset.jmCode !== meta.code) {
          itemEl.dataset.jmCode = meta.code;
        }
      }
      const code = itemEl.dataset.jmCode || meta.code || "";
      const title =
        itemEl.querySelector(".video-title")?.textContent?.trim() || meta.title || "";
      applyItemVisibility(code, itemEl, title);
    }
  }

  function syncSettingsInputs() {
    const filters = document.getElementById("jm-sticker-settings-filters");
    if (!filters) return;
    const showBlocked = filters.querySelector("#jm-show-blocked");
    const showVerified = filters.querySelector("#jm-show-verified");
    const showDownloaded = filters.querySelector("#jm-show-downloaded");
    const showBlockedSeries = filters.querySelector("#jm-show-blocked-series");
    const showBlockedActressSeries = filters.querySelector("#jm-show-blocked-actress-series");
    const showBlockedTitleKeywords = filters.querySelector("#jm-show-blocked-title-keywords");
    if (
      !showBlocked ||
      !showVerified ||
      !showDownloaded ||
      !showBlockedSeries ||
      !showBlockedActressSeries ||
      !showBlockedTitleKeywords
    )
      return;
    showBlocked.checked = stickerSettings.showBlocked;
    showVerified.checked = stickerSettings.showVerified;
    showDownloaded.checked = stickerSettings.showDownloaded;
    showBlockedSeries.checked = stickerSettings.showBlockedSeries;
    showBlockedActressSeries.checked = stickerSettings.showBlockedActressSeries;
    showBlockedTitleKeywords.checked = stickerSettings.showBlockedTitleKeywords;
  }

  function renderShortcutSettingsUI() {
    const container = document.getElementById("jm-shortcut-settings");
    if (!container) return;
    container.innerHTML = Object.keys(DEFAULT_SHORTCUTS)
      .map(
        (key) => `
        <div class="jm-shortcut-row">
          <label for="jm-shortcut-${key}">${SHORTCUT_LABELS[key]}</label>
          <input type="text" id="jm-shortcut-${key}" class="jm-shortcut-input" maxlength="1" value="${stickerShortcuts[key] || DEFAULT_SHORTCUTS[key]}" />
        </div>`
      )
      .join("");
  }

  async function saveShortcutSettingsFromUi() {
    const next = {};
    for (const key of Object.keys(DEFAULT_SHORTCUTS)) {
      const input = document.getElementById(`jm-shortcut-${key}`);
      next[key] = input?.value || DEFAULT_SHORTCUTS[key];
    }
    stickerShortcuts = normalizeShortcuts(next);
    await saveLocalState();
    refreshDetailActionBarShortcutLabels();
    renderShortcutSettingsUI();
    alert("快捷键已保存");
  }

  function appendStickerSettings() {
    const panel = document.getElementById("jm-javdb-settings-panel");
    const grid = panel?.querySelector("#jm-settings-grid-root");
    if (!grid) return;
    if (grid.querySelector("#jm-sticker-settings-filters")) {
      ensureExtraSettingsButtons(grid);
      syncSettingsInputs();
      renderBlockedSeriesList();
      renderShortcutSettingsUI();
      updateActressSyncStatus();
      return;
    }

    const filtersBlock = document.createElement("section");
    filtersBlock.id = "jm-sticker-settings-filters";
    filtersBlock.className = "jm-settings-block";
    filtersBlock.innerHTML = `
      <h3>贴纸筛选显示</h3>
      <p class="jm-hint">开启后重新显示已隐藏的贴纸。</p>
      <div class="jm-toggle-grid">
        <div class="jm-row">
          <label for="jm-show-blocked">已屏蔽</label>
          <label class="jm-switch"><input type="checkbox" id="jm-show-blocked" /><span class="jm-switch-slider"></span></label>
        </div>
        <div class="jm-row">
          <label for="jm-show-verified">已鉴定</label>
          <label class="jm-switch"><input type="checkbox" id="jm-show-verified" /><span class="jm-switch-slider"></span></label>
        </div>
        <div class="jm-row">
          <label for="jm-show-downloaded">显示已下载</label>
          <label class="jm-switch"><input type="checkbox" id="jm-show-downloaded" /><span class="jm-switch-slider"></span></label>
        </div>
        <div class="jm-row">
          <label for="jm-show-blocked-series">已屏蔽系列</label>
          <label class="jm-switch"><input type="checkbox" id="jm-show-blocked-series" /><span class="jm-switch-slider"></span></label>
        </div>
        <div class="jm-row">
          <label for="jm-show-blocked-title-keywords">标题关键词</label>
          <label class="jm-switch"><input type="checkbox" id="jm-show-blocked-title-keywords" /><span class="jm-switch-slider"></span></label>
        </div>
        <div class="jm-row">
          <label for="jm-show-blocked-actress-series">屏蔽女优</label>
          <label class="jm-switch"><input type="checkbox" id="jm-show-blocked-actress-series" /><span class="jm-switch-slider"></span></label>
        </div>
      </div>
    `;

    const shortcutsBlock = document.createElement("section");
    shortcutsBlock.id = "jm-sticker-settings-shortcuts";
    shortcutsBlock.className = "jm-settings-block";
    shortcutsBlock.innerHTML = `
      <h3>贴纸快捷键</h3>
      <p class="jm-hint">仅详情页可用，单键。</p>
      <div id="jm-shortcut-settings" class="jm-shortcut-settings"></div>
      <button type="button" id="jm-shortcut-save-btn" class="jm-settings-action jm-settings-action-compact">保存快捷键</button>
    `;

    const toolsBlock = document.createElement("section");
    toolsBlock.id = "jm-sticker-settings-tools";
    toolsBlock.className = "jm-settings-block";
    toolsBlock.innerHTML = `
      <h3>屏蔽与同步</h3>
      <button type="button" id="jm-block-series-btn" class="jm-settings-action jm-settings-action-compact">屏蔽系列</button>
      <div id="jm-blocked-series-list" class="jm-blocked-series-list"></div>
      <div class="jm-settings-action-row">
        <button type="button" id="jm-block-title-keyword-btn" class="jm-settings-action jm-settings-action-compact">屏蔽关键词</button>
        <button type="button" id="jm-remove-title-keyword-btn" class="jm-settings-action jm-settings-action-compact jm-settings-action-secondary">删减</button>
      </div>
      <button type="button" id="jm-sync-actresses-btn" class="jm-settings-action jm-settings-action-compact jm-settings-action-blue">同步已收藏女优</button>
      <button type="button" id="jm-verified-history-btn" class="jm-settings-action jm-settings-action-compact jm-settings-action-secondary">鉴定记录</button>
      <button type="button" id="jm-check-new-works-btn" class="jm-settings-action jm-settings-action-compact jm-settings-action-secondary">检测收藏女优新作</button>
      <p id="jm-actress-sync-status" class="jm-actress-sync-status">尚未同步</p>
    `;

    const backupBlock = document.createElement("section");
    backupBlock.id = "jm-sticker-settings-backup";
    backupBlock.className = "jm-settings-block";
    backupBlock.innerHTML = `
      <h3>115 数据库备份</h3>
      <p class="jm-hint">桌面端配置 115 WebDAV 后，将每天自动备份 jav_manager_state.db 到网盘。当前可在本地生成备份副本。</p>
      <button type="button" id="jm-backup-local-btn" class="jm-settings-action jm-settings-action-compact jm-settings-action-blue">生成本地备份</button>
      <p id="jm-backup-status" class="jm-actress-sync-status">尚未执行备份</p>
    `;

    grid.appendChild(filtersBlock);
    grid.appendChild(shortcutsBlock);
    grid.appendChild(toolsBlock);
    grid.appendChild(backupBlock);

    const section = filtersBlock;

    const showBlocked = section.querySelector("#jm-show-blocked");
    const showVerified = section.querySelector("#jm-show-verified");
    const showDownloaded = section.querySelector("#jm-show-downloaded");
    const showBlockedSeries = section.querySelector("#jm-show-blocked-series");
    const showBlockedActressSeries = section.querySelector("#jm-show-blocked-actress-series");
    const showBlockedTitleKeywords = section.querySelector("#jm-show-blocked-title-keywords");
    const blockSeriesBtn = toolsBlock.querySelector("#jm-block-series-btn");
    const blockTitleKeywordBtn = toolsBlock.querySelector("#jm-block-title-keyword-btn");
    const removeTitleKeywordBtn = toolsBlock.querySelector("#jm-remove-title-keyword-btn");

    async function onToggle(key, input) {
      stickerSettings[key] = input.checked === true;
      await saveLocalState();
      scheduleVisibilityPass();
    }

    showBlocked.addEventListener("change", () => onToggle("showBlocked", showBlocked));
    showVerified.addEventListener("change", () => onToggle("showVerified", showVerified));
    showDownloaded.addEventListener("change", () => onToggle("showDownloaded", showDownloaded));
    showBlockedSeries.addEventListener("change", () => onToggle("showBlockedSeries", showBlockedSeries));
    showBlockedActressSeries.addEventListener("change", () =>
      onToggle("showBlockedActressSeries", showBlockedActressSeries)
    );
    showBlockedTitleKeywords.addEventListener("change", () =>
      onToggle("showBlockedTitleKeywords", showBlockedTitleKeywords)
    );
    blockSeriesBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      openSeriesModal();
    });
    blockTitleKeywordBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      openTitleKeywordModal();
    });
    removeTitleKeywordBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      openTitleKeywordRemoveModal();
    });

    const shortcutSaveBtn = shortcutsBlock.querySelector("#jm-shortcut-save-btn");
    shortcutSaveBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      saveShortcutSettingsFromUi();
    });

    const syncActressesBtn = toolsBlock.querySelector("#jm-sync-actresses-btn");
    syncActressesBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (syncActressesBtn.disabled) return;
      syncActressesBtn.disabled = true;
      setActressStatusText("正在后台同步收藏女优…");
      void sendRuntimeMessage({ type: "sync_actresses", force: true }).then((result) => {
        syncActressesBtn.disabled = false;
        if (result?.invalidated) {
          setActressStatusText("扩展已更新，请刷新页面后重试。");
          return;
        }
        if (result?.ok) {
          setActressStatusText(
            `同步完成，共 ${result.count || 0} 位${result.syncedAt ? `（${result.syncedAt}）` : ""}`
          );
        } else if (!result?.alertShown) {
          setActressStatusText(result?.message || result?.error || "同步失败");
        }
        updateActressSyncStatus();
      });
    });

    toolsBlock.querySelector("#jm-verified-history-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      openVerifiedHistoryModal();
    });
    toolsBlock.querySelector("#jm-check-new-works-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      openNewWorksCheckModal();
    });

    backupBlock.querySelector("#jm-backup-local-btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      void sendRuntimeMessage({ type: "backup_db_local" }).then((res) => {
        const el = document.getElementById("jm-backup-status");
        if (!el) return;
        if (res?.invalidated) {
          el.textContent = "扩展已更新，请刷新页面后重试。";
          return;
        }
        el.textContent = res?.ok
          ? `本地备份已创建：${res.path || "成功"}`
          : res?.message || "备份失败（请确认桌面端已运行）";
      });
    });

    syncSettingsInputs();
    renderShortcutSettingsUI();
    renderBlockedSeriesList();
    updateActressSyncStatus();
  }

  function setActressStatusText(text) {
    const el = document.getElementById("jm-actress-sync-status");
    if (el) el.textContent = text;
  }

  function updateActressSyncStatus() {
    void sendRuntimeMessage({ type: "get_actress_sync_status" }).then((response) => {
      if (response?.invalidated || !response?.ok) return;
      if (response.running) {
        setActressStatusText("正在同步收藏女优…");
        return;
      }
      if (response.syncedAt) {
        setActressStatusText(
          `上次同步：${response.syncedAt}，共 ${response.count || 0} 位${response.lastDate ? `（${response.lastDate}）` : ""}`
        );
      } else {
        setActressStatusText("尚未同步");
      }
    });
  }

  function mergeStickerCodeMap(targetKey, rows, { replace = false } = {}) {
    if (!rows) return;
    const base = replace ? {} : { ...(stickerData[targetKey] || {}) };
    if (Array.isArray(rows)) {
      for (const row of rows) {
        if (!row?.code) continue;
        const code = normalizeCode(row.code);
        base[code] = { ...row, code };
      }
    } else if (typeof rows === "object") {
      for (const [code, row] of Object.entries(rows)) {
        const normalized = normalizeCode(code);
        if (!normalized) continue;
        base[normalized] = { ...(row || {}), code: normalized };
      }
    }
    stickerData[targetKey] = base;
  }

  function mergeVideoStatusMap(targetKey, rows, { replace = false } = {}) {
    if (!rows) return;
    const base = replace ? {} : { ...(stickerData[targetKey] || {}) };
    const ingest = (row) => {
      if (!row?.code) return;
      const code = normalizeCode(row.code);
      base[code] = {
        ...row,
        code,
        has_subtitle: Boolean(row.has_subtitle),
        is_4k: Boolean(row.is_4k),
        has_subtitle_file: Boolean(row.has_subtitle_file),
        has_uncensored_file: Boolean(row.has_uncensored_file),
      };
    };
    if (Array.isArray(rows)) {
      rows.forEach(ingest);
    } else if (typeof rows === "object") {
      Object.values(rows).forEach(ingest);
    }
    stickerData[targetKey] = base;
  }

  function mergeSyncPayload(payload) {
    if (!payload || typeof payload !== "object") return;

    for (const key of ["blocked", "verified", "downloaded", "marked"]) {
      const rows = payload[key];
      if (rows === undefined) continue;
      mergeStickerCodeMap(key, rows, { replace: true });
    }

    if (payload.videoDownloadedVideos) {
      mergeVideoStatusMap("videoDownloadedVideos", payload.videoDownloadedVideos);
    }
    if (payload.magnetSavedVideos) {
      mergeVideoStatusMap("magnetSavedVideos", payload.magnetSavedVideos);
    }
    if (payload.videoCrackedVideos) {
      mergeVideoStatusMap("videoCrackedVideos", payload.videoCrackedVideos);
    }

    const seriesRows = payload.blocked_series;
    if (Array.isArray(seriesRows)) {
      const map = {};
      for (const row of seriesRows) {
        if (row?.series) map[row.series.toUpperCase()] = row;
      }
      stickerData.blockedSeries = map;
    }

    const keywordRows = payload.blocked_title_keywords;
    if (Array.isArray(keywordRows)) {
      const map = {};
      for (const row of keywordRows) {
        if (row?.keyword) map[row.keyword] = row;
      }
      stickerData.blockedTitleKeywords = map;
    }

    if (Array.isArray(payload.blocked_actresses)) {
      const map = {};
      for (const row of payload.blocked_actresses) {
        if (row?.javdb_id) map[row.javdb_id] = row;
      }
      stickerData.blockedActresses = map;
    }

    if (Array.isArray(payload.blocked_actress_series)) {
      const map = {};
      for (const row of payload.blocked_actress_series) {
        if (row?.series) map[row.series.toUpperCase()] = row;
      }
      stickerData.blockedActressSeries = map;
    }

    if (Array.isArray(payload.mediocre_actresses)) {
      const map = {};
      for (const row of payload.mediocre_actresses) {
        if (row?.javdb_id) map[row.javdb_id] = row;
      }
      stickerData.mediocreActresses = map;
    }

    if (Array.isArray(payload.magnet_saved_videos)) {
      mergeVideoStatusMap("magnetSavedVideos", payload.magnet_saved_videos, { replace: true });
    } else if (payload.magnet_saved_videos === null) {
      stickerData.magnetSavedVideos = {};
    }

    if (Array.isArray(payload.video_downloaded_videos)) {
      mergeVideoStatusMap("videoDownloadedVideos", payload.video_downloaded_videos, { replace: true });
    } else if (payload.video_downloaded_videos === null) {
      stickerData.videoDownloadedVideos = {};
    }

    if (Array.isArray(payload.video_cracked_videos)) {
      mergeVideoStatusMap("videoCrackedVideos", payload.video_cracked_videos, { replace: true });
    } else if (payload.video_cracked_videos === null) {
      stickerData.videoCrackedVideos = {};
    }

    if (Array.isArray(payload.collected_actresses)) {
      const map = {};
      for (const row of payload.collected_actresses) {
        const id = String(row?.javdb_id || row?.starId || row?.id || "").trim();
        if (id) map[id] = row;
        else if (row?.name) map[`name:${normalizeActressName(row.name)}`] = row;
      }
      stickerData.collectedActresses = map;
    }
  }

  async function requestDesktopSync() {
    const response = await sendRuntimeMessage({ type: "sticker_sync_request" });
    if (response?.invalidated || !response?.ok) {
      scheduleVisibilityPass();
      return false;
    }
    mergeSyncPayload(response.data);
    reconcileDownloadedHideState();
    await saveLocalState();
    scheduleVisibilityPass();
    return true;
  }

  function refresh() {
    if (!isJavdbHost()) return;
    if (isListPage()) {
      decorateItems();
      injectListPageToolbar();
      scheduleVisibilityPass();
    } else {
      document.getElementById("jm-list-toolbar")?.remove();
    }
    if (isDetailPage()) {
      injectDetailPageActionBar();
      updateDetailMagnetSavedTags();
      updateDetailVideoDownloadedTags();
      updateDetailVideoCrackedTags();
    }
    appendStickerSettings();
  }

  function scheduleRefresh(records) {
    if (Array.isArray(records) && records.length && !shouldRefreshForMutations(records)) {
      return;
    }
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refresh, 150);
  }

  function startObserver() {
    if (observer) observer.disconnect();
    observer = new MutationObserver((records) => scheduleRefresh(records));
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  async function init() {
    if (!isJavdbHost()) return;

    await loadLocalState();
    ensureShortcutListener();
    setupListItemNavigation();

    if (document.readyState === "loading") {
      await new Promise((resolve) => document.addEventListener("DOMContentLoaded", resolve, { once: true }));
    }

    refresh();
    scheduleVisibilityPass();
    await requestDesktopSync();
    startObserver();
    setInterval(() => {
      if (!isListPage()) return;
      queueMissingActresses(findVideoItems());
    }, 15000);

    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== "local") return;
      if (changes[DATA_KEY]) {
        stickerData = {
          blocked: {},
          verified: {},
          downloaded: {},
          marked: {},
          blockedSeries: {},
          blockedTitleKeywords: {},
          blockedActresses: {},
          blockedActressSeries: {},
          mediocreActresses: {},
          collectedActresses: {},
          actressByCode: {},
          magnetSavedVideos: {},
          videoDownloadedVideos: {},
          videoCrackedVideos: {},
          ...changes[DATA_KEY].newValue,
        };
        stickerData.blocked = normalizeStickerListMap(stickerData.blocked);
        stickerData.verified = normalizeStickerListMap(stickerData.verified);
        stickerData.downloaded = normalizeStickerListMap(stickerData.downloaded);
        stickerData.marked = normalizeStickerListMap(stickerData.marked);
        reconcileDownloadedHideState();
        renderBlockedSeriesList();
        document.querySelectorAll(".jm-sticker-item[data-jm-code]").forEach((itemEl) => {
          updateMarkUi(itemEl.dataset.jmCode, Boolean(stickerData.marked[itemEl.dataset.jmCode]));
        });
        if (isListPage()) decorateItems();
        scheduleVisibilityPass();
        updateDetailMagnetSavedTags();
        updateDetailVideoDownloadedTags();
        updateDetailVideoCrackedTags();
      }
      if (changes[SETTINGS_KEY]) {
        stickerSettings = { ...DEFAULT_SETTINGS, ...changes[SETTINGS_KEY].newValue };
        for (const key of Object.keys(DEFAULT_SETTINGS)) {
          stickerSettings[key] = stickerSettings[key] === true;
        }
        scheduleVisibilityPass();
        syncSettingsInputs();
      }
      if (changes[SHORTCUTS_KEY]) {
        stickerShortcuts = normalizeShortcuts(changes[SHORTCUTS_KEY].newValue);
        refreshDetailActionBarShortcutLabels();
        renderShortcutSettingsUI();
      }
    });

    chrome.runtime.onMessage.addListener((msg) => {
      if (msg?.type === "sticker_sync_push" && msg.data) {
        mergeSyncPayload(msg.data);
        reconcileDownloadedHideState();
        void saveLocalState();
        renderBlockedSeriesList();
        document.querySelectorAll(".jm-sticker-item[data-jm-code]").forEach((itemEl) => {
          const code = itemEl.dataset.jmCode;
          updateMarkUi(code, Boolean(stickerData.marked[code]));
          updateStickerStatusTag(code, itemEl);
        });
        if (isDetailPage()) {
          detailPageMeta = parseDetailPageMeta();
          updateStickerStatusTag(detailPageMeta?.code, null, findDetailTitleEl());
        }
        if (isListPage()) decorateItems();
        scheduleVisibilityPass();
        updateDetailMagnetSavedTags();
        updateDetailVideoDownloadedTags();
        updateDetailVideoCrackedTags();
      }
      if (msg?.type === "actress_sync_status") {
        if (msg.showAlert && msg.message) {
          alert(msg.success ? `同步完成：${msg.message}` : `同步失败：${msg.message}`);
        }
        if (msg.status === "running") {
          setActressStatusText(msg.message || "正在后台同步收藏女优…");
        } else if (msg.status === "done") {
          setActressStatusText(
            `同步完成，共 ${msg.count || 0} 位${msg.syncedAt ? `（${msg.syncedAt}）` : ""}`
          );
        } else if (msg.status === "skipped") {
          setActressStatusText(msg.message || "今日已同步");
        } else if (msg.status === "error") {
          setActressStatusText(msg.message || "同步失败");
        }
        if (msg.status === "done" || msg.status === "error" || msg.status === "idle") {
          updateActressSyncStatus();
        }
      }
    });
  }

  init();
})();
