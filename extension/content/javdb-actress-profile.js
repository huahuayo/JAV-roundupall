/**
 * JavDB 女优作品页 / 详情页：屏蔽女优、中庸女优
 */

(function () {
  "use strict";

  if (window.__JM_JAVDB_ACTRESS_PROFILE__) return;
  window.__JM_JAVDB_ACTRESS_PROFILE__ = true;

  const DATA_KEY = "javdbStickerData";
  const CODE_PATTERNS = [
    /FC2-PPV-\d{6,7}/i,
    /HEYZO-\d{4}/i,
    /[A-Z]{2,10}-\d{2,5}[A-Z]?/i,
    /[A-Z]{2,10}\d{2,5}[A-Z]?/i,
  ];

  let profileData = {
    blockedActresses: {},
    blockedActressSeries: {},
    mediocreActresses: {},
    pendingDownloadActresses: {},
    magnetSavedActresses: {},
    videoDownloadedActresses: {},
    videoCrackedActresses: {},
  };

  let blockModal = null;
  let mediocreModal = null;
  let pendingBlockActress = null;

  function isJavdbHost() {
    return /javdb/i.test(location.hostname);
  }

  function isActressPage() {
    return /^\/(actors|stars)\/[^/?#]+\/?$/i.test(location.pathname);
  }

  function isDetailPage() {
    if (/^\/v\/[a-zA-Z0-9]+\/?$/.test(location.pathname)) return true;
    if (document.querySelector(".video-detail, .column-video-cover, .movie-panel-info")) return true;
    return false;
  }

  function getActressIdFromUrl() {
    const m = location.pathname.match(/\/(actors|stars)\/([^/?#]+)/i);
    return m ? m[2] : null;
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

  function findVideoItems() {
    const movieList = document.querySelector(
      ".movie-list:not(.movie-list-related):not(.related-movies)"
    );
    if (movieList) {
      return Array.from(movieList.children).filter((el) =>
        el.matches(".item, .column, .grid-item")
      );
    }
    const videos = document.getElementById("videos");
    if (!videos) return [];
    const grid = videos.querySelector(".grid.columns, .columns") || videos;
    return Array.from(grid.querySelectorAll(".grid-item, .column, .item"));
  }

  function parseItemCode(itemEl) {
    const titleEl = itemEl.querySelector(".video-title, .video-title a, a[title]");
    const title = (titleEl?.textContent || titleEl?.getAttribute("title") || "").trim();
    return { code: extractCode(title), title };
  }

  function collectPageSeries() {
    const seriesSet = new Set();
    for (const item of findVideoItems()) {
      const { code } = parseItemCode(item);
      if (!code) continue;
      const series = extractSeries(code);
      if (series) seriesSet.add(series);
    }
    return Array.from(seriesSet);
  }

  function sanitizeActressDisplayName(raw) {
    let name = String(raw || "").replace(/\r/g, "").trim();
    if (!name) return "";
    if (name.includes("\n")) {
      name = name.split("\n")[0].trim();
    }
    name = name.replace(/\s*\d+\s*部影片\s*$/i, "").trim();
    name = name.replace(/[（(]\s*\d+\s*部\s*[）)]\s*$/, "").trim();
    return name.replace(/\s+/g, " ").trim();
  }

  function getActressProfileInfo() {
    const nameEl =
      document.querySelector(".actor-section h2.title strong") ||
      document.querySelector(".actor-section h2.title") ||
      document.querySelector(".section-title strong") ||
      document.querySelector(".section-title") ||
      document.querySelector("h2.title") ||
      document.querySelector(".actor-name");
    const rawName = nameEl?.textContent?.trim() || document.title.split("|")[0]?.trim() || "";
    const name = sanitizeActressDisplayName(rawName);
    const aliasEl = document.querySelector(".actor-section .alias, .section-meta, .actor-meta");
    const aliases = aliasEl?.textContent?.replace(/\s+/g, " ").trim() || "";
    return { name, aliases };
  }

  async function loadProfileData() {
    try {
      const stored = await chrome.storage.local.get(DATA_KEY);
      const data = stored[DATA_KEY] || {};
      profileData = {
        blockedActresses: {},
        blockedActressSeries: {},
        mediocreActresses: {},
        pendingDownloadActresses: {},
        magnetSavedActresses: {},
        videoDownloadedActresses: {},
        videoCrackedActresses: {},
        ...data,
      };
    } catch (_) {
      profileData = {
        blockedActresses: {},
        blockedActressSeries: {},
        mediocreActresses: {},
        pendingDownloadActresses: {},
        magnetSavedActresses: {},
        videoDownloadedActresses: {},
        videoCrackedActresses: {},
      };
    }
  }

  async function saveProfileData() {
    try {
      const stored = await chrome.storage.local.get(DATA_KEY);
      const merged = { ...(stored[DATA_KEY] || {}), ...profileData };
      await chrome.storage.local.set({ [DATA_KEY]: merged });
    } catch (_) {
      /* ignore */
    }
  }

  function nowString() {
    const d = new Date();
    const pad = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
  }

  function sendAction(action, payload) {
    return new Promise((resolve) => {
      chrome.runtime.sendMessage({ type: "sticker_action", action, ...payload }, (response) => {
        if (chrome.runtime.lastError) {
          resolve({ ok: false, offline: true });
          return;
        }
        resolve(response || { ok: false });
      });
    });
  }

  function hideActressWorks() {
    findVideoItems().forEach((el) => el.classList.add("jm-sticker-hidden"));
  }

  async function applyBlockedActressPage() {
    if (!isActressPage()) return;
    const id = getActressIdFromUrl();
    if (!id) return;
    const btn = document.querySelector(".jm-block-actress");
    if (profileData.blockedActresses[id]) {
      hideActressWorks();
      if (btn) {
        btn.classList.add("jm-active");
        btn.textContent = "已屏蔽女优";
      }
    } else {
      findVideoItems().forEach((el) => el.classList.remove("jm-sticker-hidden"));
      if (btn) {
        btn.classList.remove("jm-active");
        btn.textContent = "屏蔽女优";
      }
    }
  }

  function updateMediocreNote() {
    if (!isActressPage()) return;
    const id = getActressIdFromUrl();
    const note = document.querySelector(".jm-mediocre-note");
    const btn = document.querySelector(".jm-mediocre-actress");
    if (!note || !btn || !id) return;
    const rec = profileData.mediocreActresses[id];
    if (rec?.complaints) {
      note.textContent = `槽点：${rec.complaints}`;
      btn.classList.add("jm-active");
    } else {
      note.textContent = "";
      btn.classList.remove("jm-active");
    }
  }

  function findCollectionAnchorButton() {
    for (const el of document.querySelectorAll("a.button, button.button, .button, a.tag")) {
      const text = String(el.textContent || "").replace(/\s+/g, "").trim();
      if (/取消收藏|已收藏|收藏女优|^收藏$/.test(text)) {
        return el;
      }
    }

    const panel = document.querySelector(".panel-block, .actor-section, .section.actor");
    return panel?.querySelector("a.button, button.button, a.tag.is-danger, a.tag");
  }

  function findFavoriteButton() {
    return findCollectionAnchorButton();
  }

  function ensurePendingDownloadTag(anchor) {
    const host = anchor?.parentElement || document.body;
    let tag = host.querySelector(".jm-pending-download-tag");
    if (!tag) {
      tag = document.createElement("span");
      tag.className = "jm-pending-download-tag";
      if (anchor) {
        anchor.insertAdjacentElement("afterend", tag);
      } else {
        host.appendChild(tag);
      }
    }
    tag.textContent = "待下载";
    return tag;
  }

  function updatePendingDownloadTag() {
    if (isActressPage()) {
      const id = getActressIdFromUrl();
      const bar = document.getElementById("jm-actress-actions");
      if (!bar || !id) return;
      if (profileData.pendingDownloadActresses[id]) {
        let tag = bar.querySelector(".jm-pending-download-tag");
        if (!tag) {
          tag = document.createElement("span");
          tag.className = "jm-pending-download-tag";
          bar.appendChild(tag);
        }
        tag.textContent = "待下载";
      } else {
        bar.querySelector(".jm-pending-download-tag")?.remove();
      }
      updateMagnetSavedTag();
      updateVideoDownloadedTag();
      updateVideoCrackedTag();
      return;
    }
  }

  function updateVideoDownloadedTag() {
    if (!isActressPage()) return;
    const id = getActressIdFromUrl();
    const bar = document.getElementById("jm-actress-actions");
    if (!bar || !id) return;

    const rec = profileData.videoDownloadedActresses[id];
    bar.querySelector(".jm-video-downloaded-tag")?.remove();
    if (!rec) return;

    const tag = document.createElement("span");
    tag.className = "jm-video-downloaded-tag";
    tag.textContent = "已下载";
    bar.appendChild(tag);
  }

  async function markVideoDownloadedActress(payload) {
    const javdbId = String(payload?.javdb_id || getActressIdFromUrl() || "").trim();
    if (!javdbId) {
      return { ok: false, message: "无法识别女优 ID" };
    }

    const { name } = getActressProfileInfo();
    const record = {
      javdb_id: javdbId,
      name: String(payload?.name || name || ""),
      folder_name: String(payload?.folder_name || ""),
      profile_url: String(payload?.profile_url || location.href),
      recorded_at: nowString(),
    };

    const desktop = await sendAction("video_downloaded_actress", record);
    if (!desktop?.offline && !desktop?.ok) {
      return { ok: false, message: desktop?.message || "桌面数据库保存失败" };
    }

    profileData.videoDownloadedActresses[javdbId] = record;
    await saveProfileData();
    injectActressPageButtons();
    updateVideoDownloadedTag();
    return { ok: true };
  }

  function updateVideoCrackedTag() {
    if (!isActressPage()) return;
    const id = getActressIdFromUrl();
    const bar = document.getElementById("jm-actress-actions");
    if (!bar || !id) return;

    const rec = profileData.videoCrackedActresses[id];
    bar.querySelector(".jm-video-cracked-tag")?.remove();
    if (!rec) return;

    const tag = document.createElement("span");
    tag.className = "jm-video-cracked-tag";
    tag.textContent = "已破解";
    bar.appendChild(tag);
  }

  async function markVideoCrackedActress(payload) {
    const javdbId = String(payload?.javdb_id || getActressIdFromUrl() || "").trim();
    if (!javdbId) {
      return { ok: false, message: "无法识别女优 ID" };
    }

    const { name } = getActressProfileInfo();
    const record = {
      javdb_id: javdbId,
      name: String(payload?.name || name || ""),
      folder_name: String(payload?.folder_name || ""),
      profile_url: String(payload?.profile_url || location.href),
      recorded_at: nowString(),
    };

    const desktop = await sendAction("video_cracked_actress", record);
    if (!desktop?.offline && !desktop?.ok) {
      return { ok: false, message: desktop?.message || "桌面数据库保存失败" };
    }

    profileData.videoCrackedActresses[javdbId] = record;
    await saveProfileData();
    injectActressPageButtons();
    updateVideoCrackedTag();
    return { ok: true };
  }

  function getMagnetSavedTagText(storageType) {
    return storageType === "115" ? "已保存到115" : "已保存磁链到本地";
  }

  function updateMagnetSavedTag() {
    if (!isActressPage()) return;
    const id = getActressIdFromUrl();
    const bar = document.getElementById("jm-actress-actions");
    if (!bar || !id) return;

    const rec = profileData.magnetSavedActresses[id];
    bar.querySelector(".jm-magnet-saved-tag")?.remove();
    if (!rec) return;

    const tag = document.createElement("span");
    tag.className = "jm-magnet-saved-tag";
    tag.textContent = getMagnetSavedTagText(rec.storage_type);
    bar.appendChild(tag);
  }

  async function markMagnetSavedActress(payload) {
    const javdbId = String(payload?.javdb_id || getActressIdFromUrl() || "").trim();
    if (!javdbId) {
      return { ok: false, message: "无法识别女优 ID" };
    }

    const storageType = String(payload?.storage_type || "local_magnet").trim() === "115" ? "115" : "local_magnet";
    const { name } = getActressProfileInfo();
    const record = {
      javdb_id: javdbId,
      name: String(payload?.name || name || ""),
      folder_name: String(payload?.folder_name || ""),
      profile_url: String(payload?.profile_url || location.href),
      storage_type: storageType,
      recorded_at: nowString(),
    };

    const desktop = await sendAction("magnet_saved_actress", record);
    if (!desktop?.offline && !desktop?.ok) {
      return { ok: false, message: desktop?.message || "桌面数据库保存失败" };
    }

    profileData.magnetSavedActresses[javdbId] = record;
    await saveProfileData();

    injectActressPageButtons();
    updateMagnetSavedTag();
    return { ok: true };
  }

  async function markPendingDownloadActress(payload) {
    const javdbId = String(payload?.javdb_id || getActressIdFromUrl() || "").trim();
    if (!javdbId) {
      return { ok: false, message: "无法识别女优 ID" };
    }

    const { name } = getActressProfileInfo();
    const record = {
      javdb_id: javdbId,
      name: String(payload?.name || name || ""),
      folder_name: String(payload?.folder_name || ""),
      profile_url: String(payload?.profile_url || location.href),
      recorded_at: nowString(),
    };

    profileData.pendingDownloadActresses[javdbId] = record;
    const desktop = await sendAction("pending_download_actress", record);
    if (!desktop?.offline && !desktop?.ok) {
      return { ok: false, message: desktop?.message || "桌面数据库保存失败" };
    }
    await saveProfileData();

    injectActressPageButtons();
    if (!document.querySelector(".jm-pending-download-tag")) {
      const anchor = findCollectionAnchorButton();
      if (anchor) ensurePendingDownloadTag(anchor);
    }
    updatePendingDownloadTag();
    return { ok: true };
  }

  async function blockCurrentActress(reason) {
    const javdbId = getActressIdFromUrl();
    if (!javdbId) return;

    if (profileData.blockedActresses[javdbId]) {
      const existing = profileData.blockedActresses[javdbId];
      delete profileData.blockedActresses[javdbId];
      const seriesList = Array.isArray(existing.series) ? existing.series : [];
      for (const series of seriesList) {
        delete profileData.blockedActressSeries[String(series).toUpperCase()];
      }
      await saveProfileData();
      sendAction("unblock_actress", { javdb_id: javdbId });
      applyBlockedActressPage();
      return;
    }

    const { name, aliases } = getActressProfileInfo();
    const seriesList = collectPageSeries();
    const recorded_at = nowString();

    const record = {
      javdb_id: javdbId,
      name,
      aliases,
      reason,
      page_url: location.href,
      page_title: document.title,
      series: seriesList,
      recorded_at,
    };

    profileData.blockedActresses[javdbId] = record;
    for (const series of seriesList) {
      profileData.blockedActressSeries[series.toUpperCase()] = {
        series: series.toUpperCase(),
        actress_javdb_id: javdbId,
        actress_name: name,
        reason,
        recorded_at,
      };
    }

    await saveProfileData();
    sendAction("block_actress", record);
    hideActressWorks();
    applyBlockedActressPage();
  }

  async function saveMediocreActress(complaints) {
    const javdbId = getActressIdFromUrl();
    if (!javdbId) return;
    const { name } = getActressProfileInfo();
    const record = {
      javdb_id: javdbId,
      name,
      complaints,
      page_url: location.href,
      recorded_at: nowString(),
    };
    profileData.mediocreActresses[javdbId] = record;
    await saveProfileData();
    sendAction("mediocre_actress", record);
    updateMediocreNote();
    decorateDetailPage();
  }

  function ensureBlockActressModal() {
    if (blockModal) return blockModal;
    blockModal = document.createElement("div");
    blockModal.id = "jm-block-actress-modal";
    blockModal.innerHTML = `
      <div class="jm-block-dialog" role="dialog">
        <h4>屏蔽女优</h4>
        <p class="jm-block-actress-name"></p>
        <textarea id="jm-block-actress-reason" rows="4" placeholder="请输入屏蔽原因（可选）"></textarea>
        <div class="jm-block-buttons">
          <button type="button" id="jm-block-actress-cancel">取消</button>
          <button type="button" id="jm-block-actress-confirm">确认屏蔽</button>
        </div>
      </div>
    `;
    document.body.appendChild(blockModal);

    blockModal.querySelector("#jm-block-actress-cancel").addEventListener("click", () => {
      blockModal.classList.remove("jm-visible");
      pendingBlockActress = null;
    });
    blockModal.querySelector("#jm-block-actress-confirm").addEventListener("click", async () => {
      const reason = blockModal.querySelector("#jm-block-actress-reason").value.trim();
      blockModal.classList.remove("jm-visible");
      await blockCurrentActress(reason);
      pendingBlockActress = null;
    });
    blockModal.addEventListener("click", (e) => {
      if (e.target === blockModal) blockModal.classList.remove("jm-visible");
    });
    return blockModal;
  }

  function openBlockActressModal() {
    const modal = ensureBlockActressModal();
    const { name } = getActressProfileInfo();
    modal.querySelector(".jm-block-actress-name").textContent = name || getActressIdFromUrl();
    modal.querySelector("#jm-block-actress-reason").value = "";
    modal.classList.add("jm-visible");
    modal.querySelector("#jm-block-actress-reason").focus();
  }

  function ensureMediocreModal() {
    if (mediocreModal) return mediocreModal;
    mediocreModal = document.createElement("div");
    mediocreModal.id = "jm-mediocre-modal";
    mediocreModal.innerHTML = `
      <div class="jm-block-dialog" role="dialog">
        <h4>中庸女优 — 填写槽点</h4>
        <p class="jm-mediocre-actress-name"></p>
        <textarea id="jm-mediocre-input" rows="4" placeholder="请输入槽点"></textarea>
        <div class="jm-block-buttons">
          <button type="button" id="jm-mediocre-cancel">取消</button>
          <button type="button" id="jm-mediocre-confirm">保存</button>
        </div>
      </div>
    `;
    document.body.appendChild(mediocreModal);

    mediocreModal.querySelector("#jm-mediocre-cancel").addEventListener("click", () => {
      mediocreModal.classList.remove("jm-visible");
    });
    mediocreModal.querySelector("#jm-mediocre-confirm").addEventListener("click", async () => {
      const complaints = mediocreModal.querySelector("#jm-mediocre-input").value.trim();
      if (!complaints) {
        alert("请填写槽点");
        return;
      }
      mediocreModal.classList.remove("jm-visible");
      await saveMediocreActress(complaints);
    });
    mediocreModal.addEventListener("click", (e) => {
      if (e.target === mediocreModal) mediocreModal.classList.remove("jm-visible");
    });
    return mediocreModal;
  }

  function openMediocreModal() {
    const modal = ensureMediocreModal();
    const { name } = getActressProfileInfo();
    const id = getActressIdFromUrl();
    modal.querySelector(".jm-mediocre-actress-name").textContent = name || id || "";
    modal.querySelector("#jm-mediocre-input").value =
      profileData.mediocreActresses[id]?.complaints || "";
    modal.classList.add("jm-visible");
    modal.querySelector("#jm-mediocre-input").focus();
  }

  function injectActressPageButtons() {
    if (!isActressPage()) return;

    const anchor = findFavoriteButton();
    if (!anchor) return;

    let bar = document.getElementById("jm-actress-actions");
    if (!bar) {
      bar = document.createElement("div");
      bar.id = "jm-actress-actions";
      bar.className = "jm-actress-actions";
      bar.innerHTML = `
        <button type="button" class="jm-actress-btn jm-block-actress">屏蔽女优</button>
        <button type="button" class="jm-actress-btn jm-mediocre-actress">中庸女优</button>
        <span class="jm-mediocre-note"></span>
      `;
      anchor.insertAdjacentElement("afterend", bar);

      bar.querySelector(".jm-block-actress").addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        openBlockActressModal();
      });
      bar.querySelector(".jm-mediocre-actress").addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        openMediocreModal();
      });
    }

    ensureBatchMagnetButtons(bar);
    ensureActressFolderPath(bar);
    applyBlockedActressPage();
    updateMediocreNote();
    updatePendingDownloadTag();
  }

  function ensureActressFolderPath(bar) {
    let row = document.getElementById("jm-actress-folder-path");
    if (!row) {
      row = document.createElement("div");
      row.id = "jm-actress-folder-path";
      row.className = "jm-actress-folder-path";
      bar.insertAdjacentElement("afterend", row);
    }
    void refreshActressFolderPath(false);
  }

  let actressFolderLookupKey = "";
  let actressFolderLookupResult = null;
  let actressFolderLookupInflightKey = "";

  function getActressFolderLookupKey(name, javdbId) {
    return `${String(name || "").trim()}\0${String(javdbId || "").trim()}`;
  }

  function renderActressFolderPathRow(row, name, res) {
    if (res?.invalidated) {
      row.textContent = "扩展已更新，请刷新页面后重试。";
      return;
    }
    if (res?.offline) {
      row.textContent = "桌面未连接：启动 JAV Manager 后可显示本地女优文件夹路径。";
      return;
    }
    if (!res?.ok) {
      row.textContent = res?.message || "无法查询本地女优文件夹。";
      return;
    }
    if (res.found && res.folder_path) {
      const source = res.source === "database" ? "（数据库）" : res.source === "scan" ? "（扫描）" : "";
      row.textContent = `本地女优文件夹${source}：${res.folder_path}`;
      row.title = res.folder_path;
      return;
    }
    row.textContent = `未在库目录中找到「${name}」的文件夹；一键生成将保存到待下载/磁链已保存等目录中已同步的对应女优文件夹。`;
  }

  async function refreshActressFolderPath(force = false) {
    const row = document.getElementById("jm-actress-folder-path");
    if (!row) return;
    const { name } = getActressProfileInfo();
    const javdbId = getActressIdFromUrl();
    const lookupKey = getActressFolderLookupKey(name, javdbId);
    if (!name) {
      row.textContent = "";
      actressFolderLookupKey = "";
      actressFolderLookupResult = null;
      actressFolderLookupInflightKey = "";
      return;
    }

    if (!force && lookupKey === actressFolderLookupKey && actressFolderLookupResult) {
      renderActressFolderPathRow(row, name, actressFolderLookupResult);
      return;
    }
    if (!force && lookupKey === actressFolderLookupInflightKey) {
      return;
    }

    actressFolderLookupInflightKey = lookupKey;
    if (!force && !(lookupKey === actressFolderLookupKey && actressFolderLookupResult)) {
      row.textContent = `正在查询「${name}」的本地文件夹…`;
    }

    const res = await sendRuntimeMessage({
      type: "lookup_actress_folder",
      actressName: name,
      javdbId,
    });

    if (lookupKey !== getActressFolderLookupKey(getActressProfileInfo().name, getActressIdFromUrl())) {
      return;
    }

    actressFolderLookupInflightKey = "";
    actressFolderLookupKey = lookupKey;
    actressFolderLookupResult = res;
    renderActressFolderPathRow(row, name, res);
  }

  function sendRuntimeMessage(payload) {
    return new Promise((resolve) => {
      try {
        if (!chrome?.runtime?.id) {
          resolve({ ok: false, message: "Extension context invalidated.", invalidated: true });
          return;
        }
        chrome.runtime.sendMessage(payload, (response) => {
          if (chrome.runtime.lastError) {
            resolve({ ok: false, message: chrome.runtime.lastError.message || "runtime_error" });
            return;
          }
          resolve(response || { ok: false });
        });
      } catch (err) {
        resolve({ ok: false, message: String(err.message || err) });
      }
    });
  }

  function startBatchGenerateViaPort(payload) {
    return new Promise((resolve) => {
      let settled = false;
      const finish = (result) => {
        if (settled) return;
        settled = true;
        resolve(result || { ok: false });
      };
      try {
        if (!chrome?.runtime?.id) {
          finish({ ok: false, message: "Extension context invalidated.", invalidated: true });
          return;
        }
        const port = chrome.runtime.connect({ name: "jm_batch_generate" });
        port.onMessage.addListener((response) => finish(response));
        port.onDisconnect.addListener(() => {
          if (settled) return;
          const err = chrome.runtime.lastError;
          finish({
            ok: false,
            message: err?.message || "扩展连接已断开，请重新加载扩展后重试。",
          });
        });
        port.postMessage(payload);
      } catch (err) {
        finish({ ok: false, message: String(err.message || err) });
      }
    });
  }

  function actressProfileUrl() {
    return location.href.split("#")[0].replace(/([?&])page=\d+/gi, "").replace(/[?&]$/, "");
  }

  async function startBatchGenerateAll() {
    const { name } = getActressProfileInfo();
    if (!name) {
      alert("无法识别当前女优名称。");
      return;
    }
    const payload = {
      type: "batch_generate_magnet_txt_start",
      actressName: name,
      actressJavdbId: getActressIdFromUrl(),
      profileUrl: actressProfileUrl(),
    };
    let res = await startBatchGenerateViaPort(payload);
    if (!res?.ok && /message port closed|receiving end does not exist|connection/i.test(String(res?.message || ""))) {
      res = await sendRuntimeMessage(payload);
    }
    if (res?.ok && res.started) {
      alert(`${name}：已开始批量生成，完成后将通过通知提示。`);
      return;
    }
    alert(res?.message || "无法启动批量生成任务。");
  }

  function escapeHtml(text) {
    return String(text || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function escapeHtmlAttr(text) {
    return escapeHtml(text).replace(/"/g, "&quot;");
  }

  function renderManualSubtitleTable(container, rows, videoMap) {
    if (!rows.length) {
      container.innerHTML = `<p class="jm-verified-empty">总结.txt 中没有需要手动匹配字幕的番号。</p>`;
      return;
    }
    container.innerHTML = `
      <table class="jm-verified-table">
        <thead>
          <tr>
            <th>番号</th>
            <th>分类</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${rows
            .map((row) => {
              const code = String(row.code || "").toUpperCase();
              const detailUrl = videoMap[code] || `https://javdb.com/search?q=${encodeURIComponent(code)}`;
              return `
            <tr>
              <td>${escapeHtml(code)}</td>
              <td>${escapeHtml(row.category || "-")}</td>
              <td><a href="${escapeHtmlAttr(detailUrl)}" target="_blank" rel="noopener">打开详情</a></td>
            </tr>`;
            })
            .join("")}
        </tbody>
      </table>
    `;
  }

  async function openManualSubtitleMatchModal() {
    const { name } = getActressProfileInfo();
    if (!name) {
      alert("无法识别当前女优名称。");
      return;
    }

    const summary = await sendRuntimeMessage({
      type: "read_magnet_summary",
      actressName: name,
      pending_download: Boolean(profileData.pendingDownloadActresses[getActressIdFromUrl()]),
    });
    if (!summary?.ok) {
      alert(
        summary?.message ||
          (summary?.offline
            ? "桌面未连接，或找不到总结.txt / 无字幕番号.txt。"
            : "读取失败，请确认总结.txt 或 无字幕番号.txt 是否存在。")
      );
      return;
    }

    const mapRes = await sendRuntimeMessage({
      type: "fetch_actress_video_map",
      profileUrl: actressProfileUrl(),
    });
    const videoMap = mapRes?.ok ? mapRes.map || {} : {};

    let modal = document.getElementById("jm-manual-subtitle-modal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "jm-manual-subtitle-modal";
      modal.className = "jm-modal-overlay";
      modal.innerHTML = `
        <div class="jm-modal-dialog" role="dialog">
          <div class="jm-modal-header">
            <h4>批量手动匹配字幕</h4>
            <button type="button" class="jm-modal-close" aria-label="关闭">×</button>
          </div>
          <div class="jm-manual-subtitle-body" id="jm-manual-subtitle-body"></div>
        </div>
      `;
      document.body.appendChild(modal);
      modal.querySelector(".jm-modal-close").addEventListener("click", () => modal.classList.remove("jm-visible"));
      modal.addEventListener("click", (e) => {
        if (e.target === modal) modal.classList.remove("jm-visible");
      });
    }

    modal.querySelector("h4").textContent = `批量手动匹配字幕 — ${name}`;
    renderManualSubtitleTable(
      modal.querySelector("#jm-manual-subtitle-body"),
      summary.manual_match || [],
      videoMap
    );
    modal.classList.add("jm-visible");
  }

  function ensureBatchMagnetButtons(bar) {
    if (bar.querySelector(".jm-batch-gentxt")) return;

    const genBtn = document.createElement("button");
    genBtn.type = "button";
    genBtn.className = "jm-actress-btn jm-batch-gentxt";
    genBtn.textContent = "一键生成所有";
    genBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      void startBatchGenerateAll();
    });

    const manualBtn = document.createElement("button");
    manualBtn.type = "button";
    manualBtn.className = "jm-actress-btn jm-batch-manual-sub";
    manualBtn.textContent = "批量手动匹配字幕";
    manualBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      void openManualSubtitleMatchModal();
    });

    bar.appendChild(genBtn);
    bar.appendChild(manualBtn);
  }

  function decorateDetailPage() {
    if (!isDetailPage()) return;

    document.querySelectorAll('a[href*="/actors/"], a[href*="/stars/"]').forEach((link) => {
      const m = (link.getAttribute("href") || "").match(/\/(actors|stars)\/([^/?#]+)/i);
      if (!m) return;
      const id = m[2];
      const rec = profileData.mediocreActresses[id];
      if (!rec?.complaints) return;

      const parent = link.parentElement;
      if (!parent || parent.querySelector(`.jm-mediocre-tag[data-actress-id="${CSS.escape(id)}"]`)) return;

      const tag = document.createElement("span");
      tag.className = "jm-mediocre-tag";
      tag.dataset.actressId = id;
      tag.textContent = `槽点：${rec.complaints}`;
      link.insertAdjacentElement("afterend", tag);
    });
  }

  function mergeProfilePayload(payload) {
    if (!payload) return;
    if (Array.isArray(payload.blocked_actresses)) {
      const map = {};
      for (const row of payload.blocked_actresses) {
        if (row?.javdb_id) map[row.javdb_id] = row;
      }
      profileData.blockedActresses = map;
    }
    if (Array.isArray(payload.blocked_actress_series)) {
      const map = {};
      for (const row of payload.blocked_actress_series) {
        if (row?.series) map[row.series.toUpperCase()] = row;
      }
      profileData.blockedActressSeries = map;
    }
    if (Array.isArray(payload.mediocre_actresses)) {
      const map = {};
      for (const row of payload.mediocre_actresses) {
        if (row?.javdb_id) map[row.javdb_id] = row;
      }
      profileData.mediocreActresses = map;
    }
    if (Array.isArray(payload.pending_download_actresses)) {
      const map = {};
      for (const row of payload.pending_download_actresses) {
        if (row?.javdb_id) map[row.javdb_id] = row;
      }
      profileData.pendingDownloadActresses = map;
    }
    if (Array.isArray(payload.magnet_saved_actresses)) {
      const map = {};
      for (const row of payload.magnet_saved_actresses) {
        if (row?.javdb_id) map[row.javdb_id] = row;
      }
      profileData.magnetSavedActresses = map;
    }
    if (Array.isArray(payload.video_downloaded_actresses)) {
      const map = {};
      for (const row of payload.video_downloaded_actresses) {
        if (row?.javdb_id) map[row.javdb_id] = row;
      }
      profileData.videoDownloadedActresses = map;
    }
    if (Array.isArray(payload.video_cracked_actresses)) {
      const map = {};
      for (const row of payload.video_cracked_actresses) {
        if (row?.javdb_id) map[row.javdb_id] = row;
      }
      profileData.videoCrackedActresses = map;
    }
  }

  function refresh() {
    if (!isJavdbHost()) return;
    if (isActressPage()) {
      injectActressPageButtons();
      applyBlockedActressPage();
      updateMediocreNote();
      updatePendingDownloadTag();
      updateMagnetSavedTag();
      updateVideoDownloadedTag();
      updateVideoCrackedTag();
    }
    if (isDetailPage()) {
      decorateDetailPage();
    }
  }

  async function handlePendingDownloadMessage(msg) {
    if (msg?.type === "ping") {
      return { ok: true, ready: true };
    }
    if (msg?.type === "mark_pending_download") {
      return markPendingDownloadActress(msg.actress || msg);
    }
    if (msg?.type === "mark_magnet_saved_actress") {
      return markMagnetSavedActress(msg.actress || msg);
    }
    if (msg?.type === "mark_video_downloaded_actress") {
      return markVideoDownloadedActress(msg.actress || msg);
    }
    if (msg?.type === "mark_video_cracked_actress") {
      return markVideoCrackedActress(msg.actress || msg);
    }
    if (msg?.type === "sticker_sync_push" && msg.data) {
      mergeProfilePayload(msg.data);
      await saveProfileData();
      refresh();
      return { ok: true };
    }
    return null;
  }

  window.__JM_handlePendingDownloadMark = handlePendingDownloadMessage;

  chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
    const handledTypes = new Set([
      "ping",
      "mark_pending_download",
      "mark_magnet_saved_actress",
      "mark_video_downloaded_actress",
      "mark_video_cracked_actress",
      "sticker_sync_push",
    ]);
    if (!handledTypes.has(msg?.type)) return false;

    handlePendingDownloadMessage(msg)
      .then((result) => {
        if (result !== null) sendResponse(result);
      })
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  });

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
        "#jm-actress-actions, #jm-actress-folder-path, .jm-actress-btn, .jm-mediocre-tag"
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

  let profileRefreshTimer = null;
  function scheduleProfileRefresh(records) {
    if (Array.isArray(records) && records.length && !shouldRefreshForMutations(records)) {
      return;
    }
    if (profileRefreshTimer) clearTimeout(profileRefreshTimer);
    profileRefreshTimer = setTimeout(refresh, 200);
  }

  async function init() {
    if (!isJavdbHost()) return;
    await loadProfileData();

    if (document.readyState === "loading") {
      await new Promise((r) => document.addEventListener("DOMContentLoaded", r, { once: true }));
    }

    refresh();
    const observer = new MutationObserver((records) => scheduleProfileRefresh(records));
    observer.observe(document.documentElement, { childList: true, subtree: true });

    chrome.storage.onChanged.addListener((changes, area) => {
      if (area === "local" && changes[DATA_KEY]) {
        profileData = {
          blockedActresses: {},
          blockedActressSeries: {},
          mediocreActresses: {},
          pendingDownloadActresses: {},
          magnetSavedActresses: {},
          videoDownloadedActresses: {},
        videoCrackedActresses: {},
          ...changes[DATA_KEY].newValue,
        };
        refresh();
      }
    });
  }

  init();
})();
