/**
 * JavDB 列表页：满屏网格 + 可配置每行贴纸数量
 * 支持新版 .movie-list 与旧版 #videos 结构
 */

(function () {
  "use strict";

  if (window.__JM_JAVDB_LAYOUT__) return;
  window.__JM_JAVDB_LAYOUT__ = true;

  const STORAGE_KEY = "javdbLayoutSettings";
  const DEFAULTS = { fullWidth: true, columnsPerRow: 6 };
  const MIN_COLUMNS = 2;
  const MAX_COLUMNS = 12;

  let settings = { ...DEFAULTS };
  let uiBuilt = false;
  let observer = null;
  let refreshTimer = null;

  function isJavdbHost() {
    return /javdb/i.test(location.hostname);
  }

  function isDetailPage() {
    if (/^\/v\/[a-zA-Z0-9]+\/?$/.test(location.pathname)) return true;
    if (document.querySelector(".video-detail, .column-video-cover, .movie-panel-info")) return true;
    return false;
  }

  function findVideoGrid() {
    const movieList = document.querySelector(
      ".movie-list:not(.movie-list-related):not(.related-movies)"
    );
    if (movieList) {
      const items = Array.from(movieList.children).filter((el) =>
        el.matches(".item, .column, .grid-item")
      );
      if (items.length > 0) {
        return { grid: movieList, items, kind: "movie-list" };
      }
    }

    const videos = document.getElementById("videos");
    if (!videos) return null;

    const grid =
      videos.querySelector(".grid.columns") ||
      (videos.classList.contains("columns") ? videos : null) ||
      videos.querySelector(".columns");

    if (!grid) return null;

    const items = grid.querySelectorAll(".grid-item.column, .column.grid-item, .grid-item");
    if (items.length === 0) return null;

    return { grid, items, kind: "videos" };
  }

  function isListPage() {
    if (!isJavdbHost() || isDetailPage()) return false;
    return Boolean(findVideoGrid());
  }

  async function loadSettings() {
    try {
      const stored = await chrome.storage.local.get(STORAGE_KEY);
      settings = { ...DEFAULTS, ...(stored[STORAGE_KEY] || {}) };
    } catch (_) {
      settings = { ...DEFAULTS };
    }
    settings.columnsPerRow = clampColumns(settings.columnsPerRow);
  }

  async function saveSettings() {
    try {
      await chrome.storage.local.set({ [STORAGE_KEY]: settings });
    } catch (_) {
      /* ignore */
    }
  }

  function clampColumns(value) {
    const n = Number(value);
    if (Number.isNaN(n)) return DEFAULTS.columnsPerRow;
    return Math.min(MAX_COLUMNS, Math.max(MIN_COLUMNS, Math.round(n)));
  }

  function removeLayout() {
    document.documentElement.classList.remove("jm-javdb-layout-active", "jm-javdb-fullwidth");
    document.body.classList.remove("jm-javdb-layout-active", "jm-javdb-fullwidth");
    document.documentElement.style.removeProperty("--jm-javdb-columns");
  }

  function applyLayout() {
    if (!settings.fullWidth || !findVideoGrid()) {
      removeLayout();
      return;
    }

    document.documentElement.classList.add("jm-javdb-layout-active", "jm-javdb-fullwidth");
    document.body.classList.add("jm-javdb-layout-active", "jm-javdb-fullwidth");
    document.documentElement.style.setProperty("--jm-javdb-columns", String(settings.columnsPerRow));

    const info = findVideoGrid();
    if (info?.kind === "movie-list") {
      const cols = String(settings.columnsPerRow);
      if (info.grid.dataset.jmLayoutCols === cols && info.grid.dataset.jmLayoutApplied === "1") {
        return;
      }
      info.grid.dataset.jmLayoutCols = cols;
      info.grid.dataset.jmLayoutApplied = "1";
      info.grid.style.setProperty("display", "grid", "important");
      info.grid.style.setProperty(
        "grid-template-columns",
        `repeat(${settings.columnsPerRow}, minmax(0, 1fr))`,
        "important"
      );
    }
  }

  function buildSettingsUi() {
    if (uiBuilt) return;
    uiBuilt = true;

    const btn = document.createElement("button");
    btn.id = "jm-javdb-settings-btn";
    btn.type = "button";
    btn.title = "JAV Manager 布局设置";
    btn.textContent = "⚙";
    btn.setAttribute("aria-label", "布局设置");

    const panel = document.createElement("div");
    panel.id = "jm-javdb-settings-panel";
    panel.innerHTML = `
      <div id="jm-settings-grid-root" class="jm-settings-grid">
        <section class="jm-settings-block">
          <h3>预览贴纸布局</h3>
          <p class="jm-hint">仅列表页生效。</p>
          <div class="jm-row">
            <label for="jm-fullwidth">满屏显示</label>
            <label class="jm-switch">
              <input type="checkbox" id="jm-fullwidth" />
              <span class="jm-switch-slider"></span>
            </label>
          </div>
          <div class="jm-row">
            <label for="jm-columns">每行贴纸数</label>
            <input type="number" id="jm-columns" min="${MIN_COLUMNS}" max="${MAX_COLUMNS}" />
          </div>
          <input type="range" id="jm-columns-range" min="${MIN_COLUMNS}" max="${MAX_COLUMNS}" step="1" />
        </section>
      </div>
    `;

    document.body.appendChild(btn);
    document.body.appendChild(panel);

    const fullWidthInput = panel.querySelector("#jm-fullwidth");
    const columnsInput = panel.querySelector("#jm-columns");
    const columnsRange = panel.querySelector("#jm-columns-range");

    function syncInputs() {
      fullWidthInput.checked = settings.fullWidth;
      columnsInput.value = String(settings.columnsPerRow);
      columnsRange.value = String(settings.columnsPerRow);
      const disabled = !settings.fullWidth;
      columnsInput.disabled = disabled;
      columnsRange.disabled = disabled;
      columnsInput.style.opacity = disabled ? "0.45" : "1";
      columnsRange.style.opacity = disabled ? "0.45" : "1";
    }

    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const open = panel.classList.toggle("jm-visible");
      btn.classList.toggle("jm-open", open);
      if (open) syncInputs();
    });

    document.addEventListener("click", (e) => {
      if (!panel.contains(e.target) && e.target !== btn) {
        panel.classList.remove("jm-visible");
        btn.classList.remove("jm-open");
      }
    });

    fullWidthInput.addEventListener("change", async () => {
      settings.fullWidth = fullWidthInput.checked;
      await saveSettings();
      syncInputs();
      applyLayout();
    });

    function onColumnsChange(value) {
      settings.columnsPerRow = clampColumns(value);
      columnsInput.value = String(settings.columnsPerRow);
      columnsRange.value = String(settings.columnsPerRow);
      saveSettings();
      applyLayout();
    }

    columnsInput.addEventListener("change", () => onColumnsChange(columnsInput.value));
    columnsRange.addEventListener("input", () => onColumnsChange(columnsRange.value));

    syncInputs();
  }

  function teardownSettingsUi() {
    document.getElementById("jm-javdb-settings-btn")?.remove();
    document.getElementById("jm-javdb-settings-panel")?.remove();
    uiBuilt = false;
  }

  function refresh() {
    if (!isJavdbHost()) {
      removeLayout();
      teardownSettingsUi();
      return;
    }

    if (isDetailPage()) {
      removeLayout();
      buildSettingsUi();
      return;
    }

    buildSettingsUi();
    applyLayout();
  }

  function isExtensionOwnedNode(node) {
    if (!node) return false;
    if (node.nodeType === Node.TEXT_NODE) {
      const parent = node.parentElement;
      return parent ? isExtensionOwnedNode(parent) : false;
    }
    if (!(node instanceof Element)) return false;
    if (node.id?.startsWith("jm-")) return true;
    if ([...node.classList].some((cls) => cls.startsWith("jm-"))) return true;
    return Boolean(
      node.closest(
        ".jm-sticker-actions, .jm-list-meta-row, #jm-header-tools, #jm-javdb-settings-panel"
      )
    );
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

  function scheduleRefresh(records) {
    if (Array.isArray(records) && records.length && !shouldRefreshForMutations(records)) {
      return;
    }
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refresh, 200);
  }

  function startObserver() {
    if (observer) observer.disconnect();
    observer = new MutationObserver((records) => scheduleRefresh(records));
    observer.observe(document.documentElement, { childList: true, subtree: true });
  }

  async function init() {
    if (!isJavdbHost()) return;

    await loadSettings();

    if (document.readyState === "loading") {
      await new Promise((resolve) => document.addEventListener("DOMContentLoaded", resolve, { once: true }));
    }

    refresh();
    startObserver();

    window.addEventListener("popstate", refresh);

    const origPushState = history.pushState;
    const origReplaceState = history.replaceState;
    history.pushState = function (...args) {
      origPushState.apply(this, args);
      scheduleRefresh();
    };
    history.replaceState = function (...args) {
      origReplaceState.apply(this, args);
      scheduleRefresh();
    };

    chrome.storage.onChanged.addListener((changes, area) => {
      if (area === "local" && changes[STORAGE_KEY]) {
        settings = { ...DEFAULTS, ...changes[STORAGE_KEY].newValue };
        settings.columnsPerRow = clampColumns(settings.columnsPerRow);
        applyLayout();
      }
    });
  }

  init();
})();
