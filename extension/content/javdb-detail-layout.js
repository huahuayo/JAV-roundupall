/**
 * JavDB 详情页：隐藏多余元素 + 扩展操作栏排布
 */
(function () {
  "use strict";

  if (window.__JM_DETAIL_LAYOUT__) return;
  window.__JM_DETAIL_LAYOUT__ = true;

  const RELATED_HEADING =
    /TA\s*[(\（]?\s*[們们]\s*[)\）]?\s*還出演過|TA\s*[(\（]?\s*[們们]\s*[)\）]?\s*还出演过|還出演過|还出演过|你可能也喜歡|你可能也喜欢|猜你喜歡|猜你喜欢/i;

  function isJavdbHost() {
    return /javdb/i.test(location.hostname);
  }

  function isDetailPage() {
    if (/^\/v\/[a-zA-Z0-9]+\/?$/i.test(location.pathname)) return true;
    return Boolean(document.querySelector(".video-detail, .column-video-cover, .movie-panel-info"));
  }

  function isExtensionNode(el) {
    return Boolean(
      el?.closest?.(
        ".jm-sticker-actions, #jm-detail-sticker-actions, #jm-site-buttons, #jm-detail-actions-row, #jm-detail-toolbar, #jm-compact-shell, #jm-javdb-settings-panel, .jm-modal-dialog"
      )
    );
  }

  function containsCoverMetadata(node) {
    return !!node?.querySelector(".column-video-cover, .movie-panel-info, .columns.is-desktop");
  }

  function canMoveNode(parent, child) {
    if (!parent || !child || parent === child) return false;
    if (parent.contains(child) || child.contains(parent)) return false;
    return true;
  }

  function safeAppendChild(parent, child) {
    if (!canMoveNode(parent, child)) return false;
    parent.appendChild(child);
    return true;
  }

  function findPreviewSection(root) {
    const images = root.querySelector(".preview-images, .tile-images");
    if (images) {
      for (const selector of [
        ".movie-gallery",
        "#preview-tabs",
        ".video-preview",
        ".panel-block",
        ".panel",
      ]) {
        const candidate = images.closest(selector);
        if (candidate && !containsCoverMetadata(candidate)) return candidate;
      }

      let node = images.parentElement;
      while (node && node !== root) {
        if (!containsCoverMetadata(node)) return node;
        node = node.parentElement;
      }
    }

    for (const selector of [".movie-gallery", "#preview-tabs", ".video-preview"]) {
      const candidate = root.querySelector(selector);
      if (candidate && !containsCoverMetadata(candidate)) return candidate;
    }
    return null;
  }

  function findMagnetsSection(root) {
    const content = document.getElementById("magnets-content");
    if (!content) return null;

    for (const selector of [
      '[data-controller="movie-tab"]',
      ".magnet-links",
      ".panel.magnet",
      ".tab-content",
    ]) {
      const candidate = content.closest(selector);
      if (candidate && !containsCoverMetadata(candidate)) return candidate;
    }

    const parent = content.parentElement;
    return parent && !containsCoverMetadata(parent) ? parent : content;
  }

  function layoutCompactDetailShell() {
    const videoDetail = document.querySelector(".video-detail");
    if (!videoDetail) return;

    const columns = findCoverMetadataColumns(videoDetail);
    if (!columns) return;

    let shell = document.getElementById("jm-compact-shell");
    if (!shell) {
      shell = document.createElement("div");
      shell.id = "jm-compact-shell";
      shell.className = "jm-compact-shell";

      const leftCol = document.createElement("div");
      leftCol.id = "jm-compact-left";
      leftCol.className = "jm-compact-left";

      const rightCol = document.createElement("div");
      rightCol.id = "jm-compact-magnets";
      rightCol.className = "jm-compact-magnets";

      shell.appendChild(leftCol);
      shell.appendChild(rightCol);

      const title = videoDetail.querySelector("h2.title, .current-title, h1.title");
      if (title) title.insertAdjacentElement("afterend", shell);
      else videoDetail.prepend(shell);
    }

    const leftCol = document.getElementById("jm-compact-left");
    const rightCol = document.getElementById("jm-compact-magnets");
    if (!leftCol || !rightCol) return;

    safeAppendChild(leftCol, columns);

    const preview = findPreviewSection(videoDetail);
    if (preview?.parentElement !== leftCol) safeAppendChild(leftCol, preview);

    const magnets = findMagnetsSection(videoDetail);
    if (magnets?.parentElement !== rightCol) safeAppendChild(rightCol, magnets);

    videoDetail.classList.add("jm-compact-detail");
  }

  function findCoverMetadataColumns(videoDetail) {
    if (!videoDetail) return null;
    const direct = videoDetail.querySelector(".columns.is-desktop");
    if (direct?.querySelector(".column-video-cover, .movie-panel-info")) return direct;
    for (const columns of videoDetail.querySelectorAll(".columns")) {
      if (columns.querySelector(".column-video-cover, .movie-panel-info")) return columns;
    }
    return videoDetail.querySelector(".columns");
  }

  function ensureDetailActionsRow(videoDetail) {
    const columns = findCoverMetadataColumns(videoDetail);
    if (!columns) return null;

    let row = document.getElementById("jm-detail-actions-row");
    if (!row) {
      row = document.createElement("div");
      row.id = "jm-detail-actions-row";
      row.className = "jm-detail-actions-row";
      columns.appendChild(row);
    } else if (row.parentElement !== columns) {
      columns.appendChild(row);
    }
    return row;
  }

  function relocateDetailActionBar() {
    const bar = document.getElementById("jm-detail-sticker-actions");
    const actionsRow = document.getElementById("jm-detail-actions-row");
    if (bar && actionsRow && bar.parentElement !== actionsRow) {
      actionsRow.appendChild(bar);
    }
  }

  function layoutDetailActionBar() {
    const videoDetail = document.querySelector(".video-detail");
    if (!videoDetail) return;
    layoutCompactDetailShell();
    ensureDetailActionsRow(videoDetail);
    relocateDetailActionBar();
  }

  window.__JM_layoutDetailActionBar = layoutDetailActionBar;
  window.__JM_layoutCompactDetailShell = layoutCompactDetailShell;
  window.__JM_ensureDetailActionsRow = ensureDetailActionsRow;
  window.__JM_relocateDetailActionBar = relocateDetailActionBar;

  function hideNativeJavdbControls() {
    const root = document.querySelector(".video-detail");
    if (!root) return;

    const hidePatterns = [
      /想看|想睇|want to see/i,
      /存入清[單单]|save to list|add to list/i,
      /下[載载]|download/i,
    ];
    const keepPatterns = [/看過|看过|watched|已看/i, /訂正|订正|correct|編修|编修/i];

    root.querySelectorAll("a, button").forEach((el) => {
      if (el.closest(".jm-sticker-actions, #jm-detail-sticker-actions, #jm-site-buttons, #jm-detail-toolbar, #jm-detail-actions-row")) {
        return;
      }
      const text = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (!text || text.length > 24) return;
      if (keepPatterns.some((p) => p.test(text))) {
        el.classList.add("jm-native-keep");
        return;
      }
      if (hidePatterns.some((p) => p.test(text))) {
        el.classList.add("jm-native-hidden");
      }
    });

    root.querySelectorAll("span, p, small, div").forEach((el) => {
      if (el.children.length > 0) return;
      const text = (el.textContent || "").trim();
      if (/人想看|人看過|人看过|want to see/i.test(text)) {
        el.classList.add("jm-native-hidden");
      }
    });
  }

  function hideBottomAds() {
    const adPatterns = [/官方App下载|内置磁链搜索引擎|在线播放体验更佳|app download/i];
    document.querySelectorAll(
      ".app-desktop-banner, .fixed-bottom-bar, .app-banner, [class*='desktop-banner'], footer, #footer"
    ).forEach((el) => {
      el.classList.add("jm-native-hidden");
    });
    document.querySelectorAll("div, section, aside, a").forEach((el) => {
      if (el.closest(".jm-sticker-actions, #jm-javdb-settings-panel, .jm-modal-dialog")) return;
      const text = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (!text || text.length > 120) return;
      if (!adPatterns.some((p) => p.test(text))) return;
      const rect = el.getBoundingClientRect();
      if (rect.top < window.innerHeight * 0.55) return;
      el.classList.add("jm-native-hidden");
    });
  }

  function hideBlockFrom(el) {
    if (!el) return;
    el.classList.add("jm-related-hidden");
    const parent = el.parentElement;
    if (parent && parent !== document.querySelector(".video-detail")) {
      parent.classList.add("jm-related-hidden");
    }
    let sib = parent?.nextElementSibling;
    for (let i = 0; i < 5 && sib; i++) {
      sib.classList.add("jm-related-hidden");
      sib = sib.nextElementSibling;
    }
  }

  function hideRelatedSections() {
    document.querySelectorAll(
      ".movie-list-related, #recommend-container, .recommend-container, .recommended-videos, .related-movies"
    ).forEach((el) => {
      el.classList.add("jm-related-hidden");
    });

    const root = document.querySelector(".video-detail");
    if (root) {
      root.querySelectorAll(".movie-list, .movie-list.h, .movie-list.v").forEach((list) => {
        if (list.closest("#preview-tabs, .preview-images, .movie-gallery, .tile-images, #jm-compact-left")) return;
        list.classList.add("jm-related-hidden");
        let scan = list.previousElementSibling;
        for (let i = 0; i < 4 && scan; i++) {
          scan.classList.add("jm-related-hidden");
          scan = scan.previousElementSibling;
        }
        list.parentElement?.classList.add("jm-related-hidden");
      });

      root.querySelectorAll("h2, h3, h4, h5, strong, span, p, div, section").forEach((el) => {
        if (isExtensionNode(el)) return;
        if (el.closest(".jm-related-hidden, #jm-compact-left")) return;
        const text = (el.textContent || "").replace(/\s+/g, " ").trim();
        if (text.length > 40 || text.length < 4) return;
        if (!RELATED_HEADING.test(text)) return;
        hideBlockFrom(el);
      });
    }

    document.querySelectorAll("h2, h3, h4, .title, .section-title, .main-title").forEach((el) => {
      const text = (el.textContent || "").replace(/\s+/g, " ").trim();
      if (!RELATED_HEADING.test(text)) return;
      hideBlockFrom(el);
    });
  }

  function applyDetailLayout() {
    if (!isJavdbHost()) {
      document.documentElement.classList.remove("jm-detail-layout-active");
      document.body.classList.remove("jm-detail-layout-active");
      return;
    }

    hideBottomAds();

    if (!isDetailPage()) {
      document.documentElement.classList.remove("jm-detail-layout-active");
      document.body.classList.remove("jm-detail-layout-active");
      return;
    }

    hideRelatedSections();
    hideNativeJavdbControls();
    layoutDetailActionBar();
    document.documentElement.classList.add("jm-detail-layout-active");
    document.body.classList.add("jm-detail-layout-active");
  }

  let timer = null;
  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(applyDetailLayout, 150);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", schedule);
  } else {
    schedule();
  }
  new MutationObserver(schedule).observe(document.documentElement, { childList: true, subtree: true });
})();
