/**
 * JavDB 详情页增强：长缩略图、外链按钮、磁链工具、字幕(迅雷)
 */
(function () {
  "use strict";

  if (window.__JM_DETAIL_ENHANCE__) return;
  window.__JM_DETAIL_ENHANCE__ = true;

  const CODE_PATTERNS = [
    /FC2-PPV-\d{6,7}/i,
    /HEYZO-\d{4}/i,
    /[A-Z]{2,10}-\d{2,5}[A-Z]?/i,
    /[A-Z]{2,10}\d{2,5}[A-Z]?/i,
  ];

  function isDetailPage() {
    return (
      /^\/v\/[a-zA-Z0-9]+\/?$/i.test(location.pathname) ||
      Boolean(document.querySelector(".video-detail, .column-video-cover, .movie-panel-info, .video-meta-panel"))
    );
  }

  function extractCode(text) {
    const cleaned = String(text || "")
      .replace(/[\[\(（【].*?[\]\)）】]/g, " ")
      .replace(/[_\.\s]+/g, " ")
      .trim();
    for (const pattern of CODE_PATTERNS) {
      const match = cleaned.match(pattern);
      if (match) return match[0].toUpperCase().replace(/^([A-Z]+)(\d)/, "$1-$2");
    }
    return "";
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

  function getPageCode() {
    const titleEl =
      document.querySelector(".movie-panel-info h2.title") ||
      document.querySelector(".video-detail h2.title") ||
      document.querySelector(".current-title") ||
      document.querySelector("h1.title") ||
      document.querySelector("h2.title");
    let code = extractCode(titleEl?.textContent || "");
    if (!code) code = extractCodeFromPanel();
    if (!code) {
      for (const el of document.querySelectorAll(".movie-panel-info .value, .panel-block .value")) {
        code = extractCode(el.textContent || "");
        if (code) break;
      }
    }
    return code;
  }

  function sendBg(type, payload = {}) {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type, ...payload }, (response) => {
          if (chrome.runtime.lastError) {
            resolve({ ok: false, message: chrome.runtime.lastError.message });
            return;
          }
          resolve(response || { ok: false });
        });
      } catch (err) {
        resolve({ ok: false, message: String(err.message || err) });
      }
    });
  }

  function toast(text, kind = "info") {
    if (typeof window.showJmToast === "function") {
      window.showJmToast(text, kind === "error" ? "error" : kind === "ok" ? "done" : "running");
      return;
    }
    alert(text);
  }

  function escapeHtmlAttr(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  function getPageZoomScale() {
    return window.visualViewport?.scale ?? 1;
  }

  function applyPageZoomCompensation(el) {
    if (!el) return;
    const scale = getPageZoomScale();
    el.style.setProperty("--jm-page-zoom", String(scale));
    if (Math.abs(scale - 1) < 0.001) {
      el.style.zoom = "";
      return;
    }
    el.style.zoom = String(1 / scale);
  }

  function normalizeThumbnailUrl(url) {
    if (!url) return "";
    let normalized = String(url).trim();
    const httpsIndex = normalized.indexOf("https://");
    if (httpsIndex > 0) normalized = normalized.slice(httpsIndex);
    normalized = normalized.replace(/\.th(?=\.(jpe?g|png|webp|gif)(?:[?#]|$))/i, "");
    return normalized;
  }

  function resolveFullImageUrl(url) {
    const base = normalizeThumbnailUrl(url);
    if (!base) return "";
    let full = base.replace(/_s\.(jpe?g|png|webp|gif)(?=(?:[?#]|$))/i, ".$1");
    full = full.replace(/([?&])(?:w|width|h|height|resize|size)=[^&]*/gi, "$1");
    full = full.replace(/[?&]$/, "");
    return full || base;
  }

  function getTileFullImageUrl(tile, img) {
    const anchor = tile.matches("a[href]") ? tile : tile.querySelector("a[href]");
    const href = anchor?.href || "";
    if (/\.(jpe?g|png|webp|gif)(\?|#|$)/i.test(href)) return href;
    return (
      img.dataset.original ||
      img.dataset.src ||
      img.getAttribute("data-original") ||
      img.currentSrc ||
      img.src ||
      ""
    );
  }

  function showJmImageViewer(imgUrl, altText = "", fallbackUrl = "") {
    const existing = document.getElementById("jm-image-viewer");
    existing?.remove();

    const primaryUrl = resolveFullImageUrl(imgUrl) || normalizeThumbnailUrl(imgUrl);
    const backupUrl = normalizeThumbnailUrl(fallbackUrl || imgUrl);
    const safeAlt = escapeHtmlAttr(altText || "预览图");

    const overlay = document.createElement("div");
    overlay.id = "jm-image-viewer";
    overlay.className = "jm-image-viewer";
    overlay.innerHTML = `
      <button type="button" class="jm-image-viewer-close" aria-label="关闭">×</button>
      <div class="jm-image-viewer-stage">
        <img src="${escapeHtmlAttr(primaryUrl)}" alt="${safeAlt}" data-jm-fallback="${escapeHtmlAttr(backupUrl)}" />
      </div>
    `;
    applyPageZoomCompensation(overlay);

    const img = overlay.querySelector("img");
    img?.addEventListener(
      "error",
      () => {
        const fallback = img.dataset.jmFallback || "";
        if (fallback && img.src !== fallback) img.src = fallback;
      },
      { once: true }
    );

    const prevOverflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = "hidden";

    const close = () => {
      overlay.remove();
      document.documentElement.style.overflow = prevOverflow;
    };

    overlay.querySelector(".jm-image-viewer-close")?.addEventListener("click", (e) => {
      e.stopPropagation();
      close();
    });
    overlay.addEventListener("click", (e) => {
      if (e.target === overlay) close();
    });
    document.addEventListener(
      "keydown",
      function onKey(e) {
        if (e.key === "Escape") {
          close();
          document.removeEventListener("keydown", onKey);
        }
      },
      { once: true }
    );
    document.body.appendChild(overlay);
  }

  function findPreviewGallery() {
    return (
      document.querySelector(".preview-images") ||
      document.querySelector(".movie-gallery .image-list") ||
      document.querySelector(".tile-images, .video-preview, #preview-tabs .tile-images")
    );
  }

  function ensureGalleryTileSizing() {
    const gallery = findPreviewGallery();
    if (!gallery) return;
    if (!gallery.dataset.jmTileSized) {
      gallery.dataset.jmTileSized = "1";
      gallery.classList.add("jm-preview-gallery", "jm-source-size-tiles");
    }
    applyPageZoomCompensation(gallery);
  }

  function applyPreviewTileSourceSize(img) {
    if (!img || img.dataset.jmSourceSized) return;
    const apply = () => {
      if (!img.naturalWidth || !img.naturalHeight) return;
      img.dataset.jmSourceSized = "1";
      const tile = img.closest(".tile-item");
      if (!tile || tile.classList.contains("jm-long-thumb")) return;
      tile.style.width = `${img.naturalWidth}px`;
      tile.style.height = `${img.naturalHeight}px`;
      tile.style.flex = `0 0 ${img.naturalWidth}px`;
      img.style.width = `${img.naturalWidth}px`;
      img.style.height = `${img.naturalHeight}px`;
    };
    if (img.complete) apply();
    else img.addEventListener("load", apply, { once: true });
  }

  function bindPreviewTileSourceSizing() {
    const gallery = findPreviewGallery();
    if (!gallery || gallery.dataset.jmSourceSizeBound) return;
    gallery.dataset.jmSourceSizeBound = "1";
    gallery.querySelectorAll(".tile-item:not(.jm-long-thumb) img").forEach(applyPreviewTileSourceSize);
    const obs = new MutationObserver(() => {
      gallery.querySelectorAll(".tile-item:not(.jm-long-thumb) img").forEach(applyPreviewTileSourceSize);
    });
    obs.observe(gallery, { childList: true, subtree: true });
  }

  function bindPreviewGalleryViewer() {
    const gallery = findPreviewGallery();
    if (!gallery || gallery.dataset.jmViewerBound) return;
    gallery.dataset.jmViewerBound = "1";
    gallery.addEventListener(
      "click",
      (event) => {
        const tile = event.target.closest(".tile-item:not(.jm-long-thumb)");
        if (!tile || !gallery.contains(tile)) return;
        const img = tile.querySelector("img");
        if (!img) return;
        const fullUrl = resolveFullImageUrl(getTileFullImageUrl(tile, img));
        if (!fullUrl) return;
        event.preventDefault();
        event.stopPropagation();
        showJmImageViewer(fullUrl, img.alt || "预览图", getTileFullImageUrl(tile, img));
      },
      true
    );
  }

  let magnetDisplayRulesCache = null;
  let magnetDisplayRulesLoadedAt = 0;

  async function getMagnetDisplayRules() {
    if (magnetDisplayRulesCache && Date.now() - magnetDisplayRulesLoadedAt < 60000) {
      return magnetDisplayRulesCache;
    }
    if (window.JM_magnetDisplayRules?.loadMagnetDisplayRules) {
      magnetDisplayRulesCache = await window.JM_magnetDisplayRules.loadMagnetDisplayRules();
      magnetDisplayRulesLoadedAt = Date.now();
      return magnetDisplayRulesCache;
    }
    return { reject_keywords: [], display_hide_keywords: [], display_highlight_rules: [] };
  }

  async function applyNativeMagnetDisplayRules() {
    const root = document.querySelector("#magnets-content");
    const dr = window.JM_magnetDisplayRules;
    if (!root || !dr) return;
    const rules = await getMagnetDisplayRules();
    const code = getPageCode();
    if (code && dr.sortNativeMagnetElements) {
      dr.sortNativeMagnetElements(root, code, rules);
    }
    root.querySelectorAll(".item.columns.is-desktop, .item.columns, #magnets-content > .item").forEach((rowEl) => {
      const nameEl = rowEl.querySelector(".magnet-name .name, .name");
      const title = nameEl?.textContent?.replace(/\s+/g, " ").trim() || "";
      const previewEl = rowEl.querySelector(".jm-magnet-file-preview");
      const preview = previewEl?.textContent || "";
      if (dr.shouldHideMagnetEntry(title, preview, rules)) {
        rowEl.classList.add("jm-magnet-hidden");
        rowEl.style.display = "none";
        return;
      }
      rowEl.classList.remove("jm-magnet-hidden");
      rowEl.style.display = "";
      if (nameEl) {
        nameEl.style.color = "";
        nameEl.style.fontWeight = "";
      }
      const style = dr.getMagnetHighlightStyle(title, preview, rules);
      if (nameEl && style) {
        nameEl.style.color = style.color;
        nameEl.style.fontWeight = style.fontWeight || "700";
      }
    });
  }

  function prefetch18magSearch(code) {
    sendBg("detail_search_18mag", { code }).catch(() => {});
  }

  function ensureLongThumbnailSlot() {
    const preview = findPreviewGallery();
    if (!preview) return null;
    let slot = preview.querySelector(".jm-long-thumb, .screen-container");
    if (slot) return slot;

    slot = document.createElement("a");
    slot.className = "tile-item jm-long-thumb screen-container";
    slot.href = "#";
    slot.innerHTML = `<div class="jm-long-thumb-loading">正在加载长缩略图…</div>`;
    const first = preview.querySelector(".tile-item:not(.jm-long-thumb)");
    if (first) first.before(slot);
    else preview.prepend(slot);
    return slot;
  }

  async function loadLongThumbnail(code) {
    const slot = ensureLongThumbnailSlot();
    if (!slot) return;
    if (slot.dataset.jmLongThumbLoaded === "1") return;
    if (slot.dataset.jmLongThumbLoading === "1") return;
    slot.dataset.jmLongThumbLoading = "1";

    const res = await sendBg("detail_get_long_thumb", { code });
    slot.dataset.jmLongThumbLoading = "";

    if (!res.ok || !res.url) {
      slot.dataset.jmLongThumbLoaded = "";
      slot.innerHTML = `<div class="jm-long-thumb-error">${res.message || "加载失败"}</div>`;
      slot.removeAttribute("href");
      return;
    }

    const thumbUrl = normalizeThumbnailUrl(res.url);
    const fullUrl = normalizeThumbnailUrl(res.fullUrl) || resolveFullImageUrl(thumbUrl) || thumbUrl;
    slot.href = "#";
    slot.title = "点击查看长缩略图（原始尺寸）";
    slot.innerHTML = `<img src="${escapeHtmlAttr(thumbUrl)}" alt="长缩略图" loading="lazy" />`;
    slot.dataset.jmLongThumbLoaded = "1";
    slot.dataset.jmLongThumbUrl = fullUrl;
    slot.dataset.jmLongThumbFallback = thumbUrl;

    const img = slot.querySelector("img");
    img?.addEventListener(
      "error",
      () => {
        slot.dataset.jmLongThumbLoaded = "";
        slot.innerHTML = `<div class="jm-long-thumb-error">缩略图加载失败<br><a href="#" class="jm-long-thumb-retry">点击重试</a></div>`;
        slot.querySelector(".jm-long-thumb-retry")?.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          slot.dataset.jmLongThumbLoaded = "";
          slot.innerHTML = `<div class="jm-long-thumb-loading">正在加载长缩略图…</div>`;
          loadLongThumbnail(code);
        });
      },
      { once: true }
    );

    slot.onclick = (event) => {
      event.preventDefault();
      event.stopPropagation();
      showJmImageViewer(
        slot.dataset.jmLongThumbUrl || fullUrl,
        "长缩略图",
        slot.dataset.jmLongThumbFallback || thumbUrl
      );
    };
  }

  function ensureSiteButtons(code) {
    const panel =
      document.querySelector(".movie-panel-info") ||
      document.querySelector(".video-meta-panel");
    if (!panel) return;

    let row = document.getElementById("jm-site-buttons");
    if (row) {
      if (row.parentElement !== panel) {
        panel.appendChild(row);
      }
      return;
    }

    row = document.createElement("div");
    row.id = "jm-site-buttons";
    row.className = "jm-site-buttons panel-block";
    row.innerHTML = `
      <strong>外链：</strong>
      <div class="jm-site-btn-wrap">
        <a class="jm-site-btn jm-site-pending" id="jm-missav-btn" target="_blank" rel="noopener">MissAV</a>
        <a class="jm-site-btn jm-site-pending" id="jm-javbus-btn" target="_blank" rel="noopener">JavBus</a>
      </div>
    `;
    const stickerBar = document.getElementById("jm-detail-sticker-actions");
    if (stickerBar && stickerBar.parentElement === panel) {
      stickerBar.insertAdjacentElement("beforebegin", row);
    } else {
      panel.appendChild(row);
    }

    const missavUrl = `https://missav.live/${encodeURIComponent(code.toLowerCase())}`;
    const javbusUrl = `https://www.javbus.com/${encodeURIComponent(code.toUpperCase())}`;
    row.querySelector("#jm-missav-btn").href = missavUrl;
    row.querySelector("#jm-javbus-btn").href = javbusUrl;

    sendBg("detail_check_sites", { code }).then((res) => {
      if (!res.ok) return;
      for (const item of res.results || []) {
        const btn = document.getElementById(item.site === "missav" ? "jm-missav-btn" : "jm-javbus-btn");
        if (!btn) continue;
        btn.classList.remove("jm-site-pending", "jm-site-ok", "jm-site-miss");
        btn.classList.add(item.available ? "jm-site-ok" : "jm-site-miss");
        btn.title = item.available ? "检测到对应页面" : "可能不存在，点击仍可在该站搜索";
        if (item.url) btn.href = item.url;
      }
    });
  }

  function compactMagnetItemLayout(rowEl) {
    if (!rowEl.dataset.jmMagnetCompact) {
      rowEl.dataset.jmMagnetCompact = "1";
      rowEl.classList.add("jm-magnet-compact-item");

      rowEl.querySelector(".buttons.column")?.classList.add("jm-native-hidden");
      rowEl.querySelectorAll(".copy-to-clipboard, button.copy-to-clipboard").forEach((btn) => {
        if (btn.closest(".jm-magnet-actions")) return;
        btn.classList.add("jm-native-hidden");
      });
    }

    const nameCol = rowEl.matches(".magnet-name") ? rowEl : rowEl.querySelector(".magnet-name");
    if (!nameCol) return;

    let head = nameCol.querySelector(".jm-magnet-head");
    if (!head) {
      head = document.createElement("div");
      head.className = "jm-magnet-head";
      const link = nameCol.querySelector(":scope > a");
      if (link) head.appendChild(link);
      nameCol.prepend(head);
    }

    const dateCol = rowEl.querySelector(".date.column, .date");
    if (dateCol) {
      let dateEl = head.querySelector(".jm-magnet-date");
      if (!dateEl) {
        dateEl = document.createElement("span");
        dateEl.className = "jm-magnet-date";
        dateEl.innerHTML = dateCol.innerHTML;
        head.appendChild(dateEl);
      } else {
        dateEl.innerHTML = dateCol.innerHTML;
      }
      dateCol.classList.add("jm-native-hidden");
    }

    let toolbar = nameCol.querySelector(".jm-magnet-toolbar");
    if (!toolbar) {
      toolbar = document.createElement("div");
      toolbar.className = "jm-magnet-toolbar";
      nameCol.appendChild(toolbar);
    }

    const tags = nameCol.querySelector(".tags");
    const actions = rowEl.querySelector(".jm-magnet-actions");
    if (tags && tags.parentElement !== toolbar) toolbar.appendChild(tags);
    if (actions && actions.parentElement !== toolbar) toolbar.appendChild(actions);

    const preview = rowEl.querySelector(".jm-magnet-file-preview");
    if (preview) {
      if (preview.parentElement !== nameCol) nameCol.appendChild(preview);
      if (preview.previousElementSibling !== toolbar) toolbar.insertAdjacentElement("afterend", preview);
    }
  }

  function compactMagnetsLayout() {
    const root = document.querySelector("#magnets-content");
    if (!root) return;
    root.classList.add("jm-magnets-compact-list");
    root.querySelectorAll(".item.columns.is-desktop, .item.columns, #magnets-content > .item").forEach(compactMagnetItemLayout);
  }

  function enhanceJavdbMagnets() {
    const roots = document.querySelectorAll("#magnets-content, .magnet-links, .magnet-table, .panel.magnet");
    roots.forEach((root) => {
      root.querySelectorAll("[data-clipboard-text*='magnet:'], a[href^='magnet:']").forEach((el) => {
        const magnet = el.getAttribute("data-clipboard-text") || el.getAttribute("href") || "";
        if (!magnet.startsWith("magnet:")) return;
        const row =
          el.closest(".item, .magnet-item, tr") ||
          el.closest(".item.columns, .item.columns.is-desktop") ||
          el.parentElement?.closest?.(".item");
        if (!row || row.querySelector(".jm-magnet-actions")) return;
        const actions = document.createElement("span");
        actions.className = "jm-magnet-actions";
        actions.innerHTML = `
          <button type="button" class="jm-mini-btn jm-copy-magnet">复制</button>
          <button type="button" class="jm-mini-btn jm-115-magnet">115离线</button>
        `;
        actions.querySelector(".jm-copy-magnet").addEventListener("click", async (e) => {
          e.preventDefault();
          e.stopPropagation();
          try {
            await navigator.clipboard.writeText(magnet);
            toast("磁链已复制", "ok");
          } catch (_) {
            toast("复制失败", "error");
          }
        });
        actions.querySelector(".jm-115-magnet").addEventListener("click", async (e) => {
          e.preventDefault();
          e.stopPropagation();
          const res = await sendBg("detail_115_offline", { magnet });
          toast(res.ok ? "已提交 115 离线下载" : res.message || "115 提交失败", res.ok ? "ok" : "error");
        });
        row.appendChild(actions);
      });
    });
    compactMagnetsLayout();
  }

  function appendMagnetPreview(rowEl, previewText) {
    const text = String(previewText || "").trim();
    if (!text) return;
    let preview = rowEl.querySelector(".jm-magnet-file-preview");
    if (preview) {
      if (preview.textContent === text) return;
      preview.textContent = text;
      return;
    }
    preview = document.createElement("pre");
    preview.className = "jm-magnet-file-preview";
    preview.textContent = text;
    const anchor = rowEl.querySelector(".magnet-name, .name")?.closest(".magnet-name") || rowEl.querySelector(".magnet-name, .name")?.parentElement || rowEl;
    anchor.appendChild(preview);
  }

  function extractMagnetHash(magnet) {
    const match = String(magnet || "").match(/btih:([a-f0-9]{40}|[a-f0-9]{32})/i);
    return match ? match[1].toLowerCase() : "";
  }

  function normalizeMagnetTitle(title) {
    return String(title || "")
      .toUpperCase()
      .replace(/\s+/g, " ")
      .replace(/[._-]+/g, " ")
      .trim();
  }

  function titleMatchScore(left, right) {
    const a = normalizeMagnetTitle(left);
    const b = normalizeMagnetTitle(right);
    if (!a || !b) return 0;
    if (a === b) return 1;
    if (a.includes(b) || b.includes(a)) {
      const ratio = Math.min(a.length, b.length) / Math.max(a.length, b.length);
      return 0.7 + ratio * 0.25;
    }
    const tokensA = new Set(a.split(" ").filter(Boolean));
    const tokensB = b.split(" ").filter(Boolean);
    if (!tokensB.length) return 0;
    let hits = 0;
    for (const token of tokensB) {
      if (tokensA.has(token)) hits += 1;
    }
    return hits / tokensB.length;
  }

  function pickMagnetPreviewRow(rows, title, magnetUri, usedKeys) {
    if (!rows?.length) return null;
    const hash = extractMagnetHash(magnetUri);
    if (hash) {
      const byHash = rows.find((row) => {
        const key = row.url || row.magnet;
        if (!key || usedKeys.has(key)) return false;
        return extractMagnetHash(row.magnet) === hash;
      });
      if (byHash) return byHash;
    }

    let best = null;
    let bestScore = 0;
    for (const row of rows) {
      const key = row.url || row.magnet;
      if (!key || usedKeys.has(key)) continue;
      const score = titleMatchScore(title, row.title);
      if (score > bestScore) {
        bestScore = score;
        best = row;
      }
    }
    return bestScore >= 0.65 ? best : null;
  }

  async function enrichMagnetPreviews(code) {
    const root = document.querySelector("#magnets-content");
    if (!root) return;
    if (root.dataset.jmPreviewEnriched === code) {
      compactMagnetsLayout();
      await applyNativeMagnetDisplayRules();
      return;
    }
    const rowEls = root.querySelectorAll(".item.columns.is-desktop, .item.columns, #magnets-content > .item");
    if (!rowEls.length) return;

    const res = await sendBg("detail_search_18mag", { code });
    if (!res.ok || !Array.isArray(res.rows) || !res.rows.length) return;

    const usedKeys = new Set();
    rowEls.forEach((rowEl) => {
      const nameEl = rowEl.querySelector(".magnet-name .name, .name");
      const title = nameEl?.textContent?.replace(/\s+/g, " ").trim() || "";
      if (!title) return;
      const magnetEl = rowEl.querySelector("[data-clipboard-text*='magnet:'], a[href^='magnet:']");
      const magnetUri = magnetEl?.getAttribute("data-clipboard-text") || magnetEl?.getAttribute("href") || "";
      const match = pickMagnetPreviewRow(res.rows, title, magnetUri, usedKeys);
      if (!match?.preview) return;
      const key = match.url || match.magnet;
      if (key) usedKeys.add(key);
      appendMagnetPreview(rowEl, match.preview);
    });
    compactMagnetsLayout();
    await applyNativeMagnetDisplayRules();
    root.dataset.jmPreviewEnriched = code;
  }

  function waitForMagnetsThenEnhance(code) {
    let attempts = 0;
    const tick = async () => {
      const root = document.querySelector("#magnets-content");
      const ready = root && root.querySelector(".name, [data-clipboard-text*='magnet:'], a[href^='magnet:']");
      if (ready) {
        enhanceJavdbMagnets();
        await applyNativeMagnetDisplayRules();
        enrichMagnetPreviews(code);
        return true;
      }
      return false;
    };
    tick();
    const timer = setInterval(() => {
      tick().then((done) => {
        if (done || ++attempts >= 50) clearInterval(timer);
      });
    }, 150);
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  async function renderMagnetRows(container, rows, code) {
    container.innerHTML = "";
    const rules = await getMagnetDisplayRules();
    const dr = window.JM_magnetDisplayRules;
    const pageCode = String(code || getPageCode() || "").trim();
    const sortedRows = dr?.sortMagnetRows ? dr.sortMagnetRows(rows, pageCode, rules) : rows || [];
    const visibleRows = dr ? dr.filterMagnetRows(sortedRows, rules) : sortedRows || [];
    if (!visibleRows.length) {
      container.innerHTML = `<div class="jm-magnet-empty">无结果</div>`;
      return;
    }
    for (const row of visibleRows) {
      const style = dr?.getMagnetHighlightStyle(row.title, row.preview || row.magnet, rules);
      const titleStyle = style
        ? ` style="color:${escapeHtml(style.color)};font-weight:${escapeHtml(style.fontWeight || "700")}"`
        : "";
      const item = document.createElement("div");
      item.className = "jm-magnet-result";
      item.innerHTML = `
        <div class="jm-magnet-result-title"${titleStyle}>${escapeHtml(row.title || "-")}</div>
        <div class="jm-magnet-result-meta">${escapeHtml([row.size, row.date].filter(Boolean).join(" · "))}</div>
        <pre class="jm-magnet-result-preview">${escapeHtml(row.preview || row.magnet || "")}</pre>
        <div class="jm-magnet-result-actions">
          <button type="button" class="jm-mini-btn jm-copy-row">复制磁链</button>
          <button type="button" class="jm-mini-btn jm-115-row">115离线</button>
        </div>
      `;
      item.querySelector(".jm-copy-row").addEventListener("click", async () => {
        if (!row.magnet) {
          toast("无磁链可复制", "error");
          return;
        }
        await navigator.clipboard.writeText(row.magnet);
        toast("已复制", "ok");
      });
      item.querySelector(".jm-115-row").addEventListener("click", async () => {
        if (!row.magnet) {
          toast("无磁链", "error");
          return;
        }
        const res = await sendBg("detail_115_offline", { magnet: row.magnet });
        toast(res.ok ? "已提交 115" : res.message || "失败", res.ok ? "ok" : "error");
      });
      container.appendChild(item);
    }
  }

  function openMagnetSearchModal(code) {
    let modal = document.getElementById("jm-magnet-search-modal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "jm-magnet-search-modal";
      modal.innerHTML = `
        <div class="jm-modal-dialog jm-magnet-modal" role="dialog">
          <div class="jm-modal-header">
            <h4>磁力搜索</h4>
            <button type="button" class="jm-modal-close" aria-label="关闭">×</button>
          </div>
          <div class="jm-magnet-split">
            <section class="jm-magnet-pane">
              <h5>18mag.net</h5>
              <div id="jm-magnet-18mag" class="jm-magnet-pane-body">加载中…</div>
            </section>
            <section class="jm-magnet-pane">
              <h5>Sukebei</h5>
              <div id="jm-magnet-sukebei" class="jm-magnet-pane-body">加载中…</div>
            </section>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
      modal.querySelector(".jm-modal-close").addEventListener("click", () => modal.classList.remove("jm-visible"));
      modal.addEventListener("click", (e) => {
        if (e.target === modal) modal.classList.remove("jm-visible");
      });
    }
    modal.classList.add("jm-visible");
    modal.querySelector("h4").textContent = `磁力搜索 — ${code}`;
    const pane18 = modal.querySelector("#jm-magnet-18mag");
    const paneSukebei = modal.querySelector("#jm-magnet-sukebei");
    pane18.textContent = "加载中…";
    paneSukebei.textContent = "加载中…";
    sendBg("detail_search_magnets", { code }).then((res) => {
      if (!res.ok) {
        pane18.textContent = res.message || "搜索失败";
        paneSukebei.textContent = res.message || "搜索失败";
        return;
      }
      if (res.errors?.mag18) {
        pane18.insertAdjacentHTML("afterbegin", `<div class="jm-magnet-error">${escapeHtml(res.errors.mag18)}</div>`);
      }
      if (res.errors?.sukebei) {
        paneSukebei.insertAdjacentHTML(
          "afterbegin",
          `<div class="jm-magnet-error">${escapeHtml(res.errors.sukebei)}</div>`
        );
      }
      renderMagnetRows(pane18, res.mag18 || [], code);
      renderMagnetRows(paneSukebei, res.sukebei || [], code);
    });
  }

  function openWjMagnetModal(code) {
    let modal = document.getElementById("jm-wj-magnet-modal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "jm-wj-magnet-modal";
      modal.innerHTML = `
        <div class="jm-modal-dialog jm-magnet-modal" role="dialog">
          <div class="jm-modal-header">
            <h4>wj磁链 — 18mag.net</h4>
            <button type="button" class="jm-modal-close" aria-label="关闭">×</button>
          </div>
          <div id="jm-wj-magnet-body" class="jm-magnet-pane-body">加载中…</div>
          <div class="jm-modal-footer jm-wj-magnet-footer">
            <a class="jm-wj-open-site" href="#" target="_blank" rel="noopener">在 18mag.net 打开完整搜索</a>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
      modal.querySelector(".jm-modal-close").addEventListener("click", () => modal.classList.remove("jm-visible"));
      modal.addEventListener("click", (e) => {
        if (e.target === modal) modal.classList.remove("jm-visible");
      });
    }
    modal.classList.add("jm-visible");
    const searchUrl = `https://18mag.net/search?q=${encodeURIComponent(code)}`;
    modal.querySelector("h4").textContent = `wj磁链 — ${code}`;
    modal.querySelector(".jm-wj-open-site")?.setAttribute("href", searchUrl);
    const body = modal.querySelector("#jm-wj-magnet-body");
    body.textContent = "加载中…";
    sendBg("detail_search_18mag", { code, maxResults: 30 }).then((res) => {
      if (!res.ok) {
        body.textContent = res.message || "搜索失败";
        return;
      }
      const rows = res.rows || [];
      modal.querySelector("h4").textContent = `wj磁链 — ${code}（${rows.length} 条）`;
      renderMagnetRows(body, rows, code);
    });
  }

  function openSubtitleModal(code) {
    let modal = document.getElementById("jm-subtitle-modal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "jm-subtitle-modal";
      modal.innerHTML = `
        <div class="jm-modal-dialog" role="dialog">
          <div class="jm-modal-header">
            <h4>字幕(迅雷)</h4>
            <button type="button" class="jm-modal-close" aria-label="关闭">×</button>
          </div>
          <div id="jm-subtitle-list" class="jm-subtitle-list"></div>
          <pre id="jm-subtitle-preview" class="jm-subtitle-preview" hidden></pre>
        </div>
      `;
      document.body.appendChild(modal);
      modal.querySelector(".jm-modal-close").addEventListener("click", () => modal.classList.remove("jm-visible"));
      modal.addEventListener("click", (e) => {
        if (e.target === modal) modal.classList.remove("jm-visible");
      });
    }
    modal.classList.add("jm-visible");
    const list = modal.querySelector("#jm-subtitle-list");
    const preview = modal.querySelector("#jm-subtitle-preview");
    list.textContent = "加载中…";
    preview.hidden = true;
    sendBg("detail_search_subtitles", { code }).then((res) => {
      list.innerHTML = "";
      if (!res.ok || !res.items?.length) {
        list.textContent = res.message || "未找到字幕";
        return;
      }
      for (const item of res.items) {
        const row = document.createElement("div");
        row.className = "jm-subtitle-row";
        row.innerHTML = `
          <span>${escapeHtml(item.name || "-")}</span>
          <span class="jm-sub-ext">${escapeHtml(item.ext || "")}</span>
          <button type="button" class="jm-mini-btn jm-sub-preview">预览</button>
          <button type="button" class="jm-mini-btn jm-sub-download">下载</button>
        `;
        row.querySelector(".jm-sub-preview").addEventListener("click", async () => {
          const r = await sendBg("detail_fetch_subtitle", { url: item.url });
          preview.hidden = false;
          preview.textContent = r.ok ? r.content.slice(0, 8000) : r.message || "预览失败";
        });
        row.querySelector(".jm-sub-download").addEventListener("click", async () => {
          const r = await sendBg("detail_download_subtitle", { url: item.url, code, ext: item.ext || "srt" });
          toast(r.ok ? `已下载为 ${code}.${item.ext || "srt"}` : r.message || "下载失败", r.ok ? "ok" : "error");
        });
        list.appendChild(row);
      }
    });
  }

  function removeRedundantToolbar() {
    document.getElementById("jm-detail-toolbar")?.remove();
  }

  async function highlightDetailActresses() {
    const panel = document.querySelector(".movie-panel-info, .video-meta-panel");
    if (!panel) return;
    let data = {};
    try {
      const stored = await chrome.storage.local.get("javdbStickerData");
      data = stored.javdbStickerData || {};
    } catch (_) {
      return;
    }
    const collectedById = data.collectedActresses || {};
    const collectedByName = new Map();
    for (const row of Object.values(collectedById)) {
      if (row?.name) collectedByName.set(String(row.name).trim().toLowerCase(), row);
    }
    const mediocreById = data.mediocreActresses || {};
    panel.querySelectorAll('a[href*="/actors/"], a[href*="/stars/"]').forEach((anchor) => {
      const href = anchor.getAttribute("href") || "";
      const match = href.match(/\/(actors|stars)\/([^/?#]+)/i);
      const javdbId = match ? match[2] : "";
      const name = (anchor.textContent || "").trim();
      anchor.classList.remove("jm-actress-collected", "jm-actress-mediocre");
      let cls = "";
      let reason = "";
      if ((javdbId && collectedById[javdbId]) || collectedByName.has(name.toLowerCase())) {
        cls = "jm-actress-collected";
      } else if (javdbId && mediocreById[javdbId]) {
        cls = "jm-actress-mediocre";
        reason = String(mediocreById[javdbId].complaints || mediocreById[javdbId].reason || "").trim();
      } else {
        for (const row of Object.values(mediocreById)) {
          if (String(row.name || "").trim().toLowerCase() === name.toLowerCase()) {
            cls = "jm-actress-mediocre";
            reason = String(row.complaints || row.reason || "").trim();
            break;
          }
        }
      }
      if (!cls) return;
      anchor.classList.add(cls);
      if (reason) anchor.title = reason;
    });
  }

  function refreshDetailEnhance(forcedCode) {
    if (!isDetailPage()) return;
    const code = String(forcedCode || getPageCode() || "").trim();
    if (!code) return;
    prefetch18magSearch(code);
    if (typeof window.__JM_layoutDetailActionBar === "function") {
      window.__JM_layoutDetailActionBar();
    }
    ensureGalleryTileSizing();
    bindPreviewTileSourceSizing();
    bindPreviewGalleryViewer();
    ensureSiteButtons(code);
    removeRedundantToolbar();
    waitForMagnetsThenEnhance(code);
    loadLongThumbnail(code);
    highlightDetailActresses();
  }

  window.__JM_refreshDetailEnhance = refreshDetailEnhance;
  window.__JM_openMagnetSearch = openMagnetSearchModal;
  window.__JM_openWjMagnetModal = openWjMagnetModal;
  window.__JM_openSubtitleSearch = openSubtitleModal;

  let timer = null;
  function scheduleRefresh() {
    clearTimeout(timer);
    timer = setTimeout(() => refreshDetailEnhance(), 200);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scheduleRefresh);
  } else {
    scheduleRefresh();
  }

  try {
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== "local" || !changes.magnetFilterRules) return;
      magnetDisplayRulesCache = null;
      applyNativeMagnetDisplayRules();
    });
  } catch (_) {
    /* ignore */
  }

  const obs = new MutationObserver(scheduleRefresh);
  obs.observe(document.documentElement, { childList: true, subtree: true });

  window.visualViewport?.addEventListener("resize", () => {
    applyPageZoomCompensation(findPreviewGallery());
    const viewer = document.getElementById("jm-image-viewer");
    if (viewer) applyPageZoomCompensation(viewer);
  });
})();
