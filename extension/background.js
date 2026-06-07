importScripts(
  "lib/magnet-pattern-match-sw.js",
  "lib/magnet-keyword-match-sw.js",
  "lib/magnet-txt-core.js",
  "lib/name-match.js",
  "lib/pending-download-collections.js",
  "lib/magnet-saved-sync.js",
  "lib/metadata-sync.js",
  "lib/metadata-javbus.js",
  "lib/detail-tools-sw.js"
);

function scheduleBatchGenerateMagnetTxtJob(payload) {
  void runBatchGenerateMagnetTxtJob(payload);
}

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== "jm_batch_generate") return;
  const connectTabId = port.sender?.tab?.id;
  port.onMessage.addListener((message) => {
    const reply = (payload) => {
      try {
        port.postMessage(payload);
      } catch (_) {
        /* ignore */
      }
      try {
        port.disconnect();
      } catch (_) {
        /* ignore */
      }
    };
    if (message?.type !== "batch_generate_magnet_txt_start") {
      reply({ ok: false, message: "unknown_type" });
      return;
    }
    const tabId = connectTabId || port.sender?.tab?.id;
    if (!tabId) {
      reply({ ok: false, message: "missing_tab" });
      return;
    }
    reply({ ok: true, started: true });
    scheduleBatchGenerateMagnetTxtJob({
      actressName: message.actressName,
      actressJavdbId: message.actressJavdbId,
      profileUrl: message.profileUrl,
      tabId,
    });
  });
});

const DEFAULT_PORT = 17892;
const RECONNECT_BASE_MS = 1500;
const RECONNECT_MAX_MS = 30000;

let socket = null;
let connectGeneration = 0;
let reconnectTimer = null;
let reconnectDelay = RECONNECT_BASE_MS;
let settings = { port: DEFAULT_PORT, token: "" };
let lastSentKey = "";
let pendingStickerSync = null;
let pendingActressSync = null;
let pendingMagnetTxt = null;
let pendingMagnetTxtBatch = null;
let pendingMagnetSummary = null;
let pendingMagnetSummaries = new Map();
let magnetSummarySerial = 0;
let singleMagnetTxtRunning = false;
let pendingActressFolderLookups = new Map();
let actressFolderLookupCache = new Map();
let batchGenerateMagnetTxtRunning = false;
let newWorksCheckCancelled = false;
let pendingMetadataAsset = null;
let pendingSyncFolderExport = null;

const SYNC_FOLDER_ACK_TYPES = new Set([
  "magnet_saved_sync_folder_ack",
  "video_downloaded_sync_folder_ack",
  "video_cracked_sync_folder_ack",
  "pending_download_sync_folder_ack",
  "video_metadata_folder_ack",
  "loose_video_sync_folder_ack",
]);
let magnetFilterRulesWaiters = [];
let actressSyncRunning = false;
let pendingDownloadSyncRunning = false;
let pendingDownloadMarkTabId = null;
let magnetSavedSyncRunning = false;
let magnetSavedMarkTabId = null;
let magnetSavedWorkerWindowId = null;
let videoDownloadedSyncRunning = false;
let videoDownloadedMarkTabId = null;
let videoDownloadedWorkerWindowId = null;
let videoCrackedSyncRunning = false;
let videoCrackedMarkTabId = null;
let videoCrackedWorkerWindowId = null;
let videoMetadataSyncRunning = false;
let videoMetadataMarkTabId = null;
let videoMetadataWorkerWindowId = null;
let looseVideoSyncRunning = false;
let magnetTxtJobSerial = 0;
let stickerActionSerial = 0;
let wsRequestSerial = 0;
const pendingStickerActions = new Map();

const APP_DISPLAY_NAME = "JAV一网打尽";
const ACTRESS_COLLECTION_PATH = "/users/collection_actors";
const SKIP_ACTOR_IDS = new Set(["favorite", "collection", "collections", "search"]);

function detectBrowser() {
  const ua = navigator.userAgent || "";
  if (/115Browser|115\/|115browser/i.test(ua)) return "115";
  if (/Edg\//i.test(ua)) return "edge";
  return "edge";
}

const BROWSER_NAME = detectBrowser();

async function loadSettings() {
  const stored = await chrome.storage.local.get(["bridgePort", "bridgeToken"]);
  settings = {
    port: stored.bridgePort || DEFAULT_PORT,
    token: stored.bridgeToken || "",
  };
}

function wsUrl() {
  return `ws://127.0.0.1:${settings.port}`;
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(async () => {
    reconnectTimer = null;
    await connect();
    reconnectDelay = Math.min(reconnectDelay * 1.5, RECONNECT_MAX_MS);
  }, reconnectDelay);
}

function clearReconnect() {
  if (reconnectTimer) {
    clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }
}

async function sendTabSnapshot(tab) {
  if (!socket || socket.readyState !== WebSocket.OPEN || !tab?.url) return;

  const payload = {
    type: "tab_update",
    browser: BROWSER_NAME,
    tabId: tab.id,
    windowId: tab.windowId,
    url: tab.url,
    title: tab.title || "",
    timestamp: Date.now(),
  };

  const key = `${payload.url}|${payload.title}`;
  if (key === lastSentKey) return;
  lastSentKey = key;

  socket.send(JSON.stringify(payload));
}

async function queryActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
  return tabs[0] || null;
}

async function pushActiveTab() {
  const tab = await queryActiveTab();
  if (tab) await sendTabSnapshot(tab);
}

async function connect() {
  await loadSettings();

  if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) {
    return;
  }

  if (socket) {
    try {
      socket.close();
    } catch (_) {
      /* ignore */
    }
    socket = null;
  }

  const generation = ++connectGeneration;
  let ws;
  try {
    ws = new WebSocket(wsUrl());
  } catch (err) {
    console.warn("[JAV一网打尽 Bridge] WebSocket create failed", err);
    scheduleReconnect();
    return;
  }

  socket = ws;
  const isActive = () => socket === ws && connectGeneration === generation;

  ws.addEventListener("open", () => {
    if (!isActive() || ws.readyState !== WebSocket.OPEN) return;
    clearReconnect();
    reconnectDelay = RECONNECT_BASE_MS;
    try {
      ws.send(
        JSON.stringify({
          type: "hello",
          browser: BROWSER_NAME,
          version: chrome.runtime.getManifest().version,
          token: settings.token || "",
        })
      );
      void pushActiveTab();
    } catch (err) {
      console.warn("[JAV一网打尽 Bridge] hello send failed", err);
      scheduleReconnect();
    }
  });

  ws.addEventListener("message", (event) => {
    if (!isActive()) return;
    try {
      const msg = JSON.parse(event.data);
      if (msg.type === "ping") {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "pong" }));
        return;
      }
      if (msg.type === "auth_pending") {
        chrome.notifications?.create?.("jm-auth-pending", {
          type: "basic",
          iconUrl: "icons/icon128.png",
          title: "JAV一网打尽",
          message: "请在桌面程序弹窗中点「是」允许扩展连接。",
        });
        return;
      }
      if (msg.type === "auth_rejected") {
        settings.token = "";
        void chrome.storage.local.remove("bridgeToken").catch(() => {});
        try {
          chrome.notifications?.create?.(`jm-auth-rejected-${Date.now()}`, {
            type: "basic",
            iconUrl: "icons/icon128.png",
            title: "JAV一网打尽",
            message: "桌面程序拒绝了扩展连接。请打开桌面程序，在弹窗中点「是」；或到扩展设置里点「重置配对」。",
          });
        } catch (_) {
          /* ignore */
        }
        try {
          socket?.close();
        } catch (_) {
          /* ignore */
        }
        scheduleReconnect();
        return;
      }
      if (msg.type === "hello_ack") {
        if (msg.token) {
          settings.token = msg.token;
          chrome.storage.local.set({ bridgeToken: msg.token, bridgePort: settings.port }).catch(() => {});
        }
        if (msg.magnet_filter_rules) {
          storeMagnetFilterRules(msg.magnet_filter_rules);
        } else {
          requestMagnetFilterRulesFromDesktop();
        }
        requestStickerSyncFromDesktop();
        requestActressSyncInfo();
        return;
      }
      if (msg.type === "state_db_cleared") {
        void applyStateDbCleared(msg);
        return;
      }
      if (msg.type === "magnet_filter_rules") {
        storeMagnetFilterRules(msg.rules);
        resolveMagnetFilterRulesWaiters(msg.rules);
        broadcastMagnetFilterRules(msg.rules);
        return;
      }
      if (msg.type === "sticker_sync" || msg.type === "sticker_bulk_ack") {
        if (pendingStickerSync) {
          if (pendingStickerSync.timer) clearTimeout(pendingStickerSync.timer);
          pendingStickerSync.resolve(msg);
          pendingStickerSync = null;
        }
        broadcastStickerSync(msg);
        return;
      }
      if (msg.type === "actress_sync_request") {
        runActressSync({ force: Boolean(msg.force), reason: msg.reason || "auto" });
        return;
      }
      if (msg.type === "pending_download_sync_request") {
        runPendingDownloadSync(msg);
        return;
      }
      if (msg.type === "magnet_saved_sync_request") {
        runMagnetSavedSync(msg);
        return;
      }
      if (msg.type === "video_downloaded_sync_request") {
        void runVideoDownloadedSync(msg).catch((err) => {
          console.warn("[JAV一网打尽] video_downloaded_sync failed", err);
        });
        return;
      }
      if (msg.type === "video_cracked_sync_request") {
        void runVideoCrackedSync(msg).catch((err) => {
          console.warn("[JAV一网打尽] video_cracked_sync failed", err);
        });
        return;
      }
      if (msg.type === "video_metadata_sync_request") {
        void runVideoMetadataSync(msg).catch((err) => {
          console.warn("[JAV一网打尽] video_metadata_sync failed", err);
        });
        return;
      }
      if (msg.type === "loose_video_sync_request") {
        runLooseVideoSync(msg);
        return;
      }
      if (msg.type === "actress_sync_ack") {
        if (pendingActressSync) {
          if (msg.ok) pendingActressSync.resolve(msg);
          else pendingActressSync.reject(new Error(msg.message || "桌面程序保存失败"));
          pendingActressSync = null;
        }
        if (msg.ok) {
          markActressSyncedLocal(msg.last_sync_date, msg.count ?? msg.last_count, msg.last_sync_at);
        }
        broadcastActressSyncStatus({
          status: msg.ok ? "done" : "error",
          count: msg.count || msg.last_count || 0,
          syncedAt: msg.last_sync_at || "",
          message: msg.message || "",
          success: Boolean(msg.ok),
        });
        return;
      }
      if (msg.type === "actress_sync_info") {
        markActressSyncedLocal(msg.last_sync_date, msg.last_count, msg.last_sync_at);
        broadcastActressSyncStatus({
          status: "idle",
          count: msg.last_count || 0,
          syncedAt: msg.last_sync_at || "",
        });
        return;
      }
      if (msg.type === "magnet_txt_ack") {
        if (pendingMagnetTxt) {
          if (msg.ok) pendingMagnetTxt.resolve(msg);
          else pendingMagnetTxt.reject(new Error(msg.message || "保存失败"));
          pendingMagnetTxt = null;
        }
        return;
      }
      if (msg.type === "magnet_txt_batch_ack") {
        if (pendingMagnetTxtBatch) {
          if (msg.ok) pendingMagnetTxtBatch.resolve(msg);
          else pendingMagnetTxtBatch.reject(new Error(msg.message || "批量保存失败"));
          pendingMagnetTxtBatch = null;
        }
        return;
      }
      if (msg.type === "magnet_summary_ack") {
        const serial = msg.serial;
        if (serial != null && pendingMagnetSummaries.has(serial)) {
          const pending = pendingMagnetSummaries.get(serial);
          pendingMagnetSummaries.delete(serial);
          pending.resolve(msg);
          return;
        }
        if (pendingMagnetSummary) {
          pendingMagnetSummary.resolve(msg);
          pendingMagnetSummary = null;
        }
        return;
      }
      if (msg.type === "actress_folder_lookup_ack") {
        const serial = msg.serial;
        if (serial != null && pendingActressFolderLookups.has(serial)) {
          const pending = pendingActressFolderLookups.get(serial);
          pendingActressFolderLookups.delete(serial);
          pending.resolve(msg);
        }
        return;
      }
      if (msg.type === "metadata_asset_ack") {
        if (pendingMetadataAsset) {
          if (msg.ok) pendingMetadataAsset.resolve(msg);
          else pendingMetadataAsset.reject(new Error(msg.message || "保存失败"));
          pendingMetadataAsset = null;
        }
        return;
      }
      if (SYNC_FOLDER_ACK_TYPES.has(msg.type)) {
        if (pendingSyncFolderExport) {
          pendingSyncFolderExport.resolve(msg);
          pendingSyncFolderExport = null;
        }
        return;
      }
      if (msg.type === "sticker_action_ack") {
        const serial = msg.serial;
        if (serial != null && pendingStickerActions.has(serial)) {
          const pending = pendingStickerActions.get(serial);
          clearTimeout(pending.timer);
          pendingStickerActions.delete(serial);
          if (msg.ok) pending.resolve(msg);
          else pending.reject(new Error(msg.message || "桌面保存失败"));
        }
        return;
      }
      if (msg.type === "backup_db_local_ack") {
        const serial = msg.serial;
        if (serial != null && pendingStickerActions.has(serial)) {
          const pending = pendingStickerActions.get(serial);
          clearTimeout(pending.timer);
          pendingStickerActions.delete(serial);
          if (msg.ok) pending.resolve({ ok: true, path: msg.path, status: msg.status });
          else pending.reject(new Error(msg.message || "备份失败"));
        }
        return;
      }
    } catch (_) {
      /* ignore */
    }
  });

  ws.addEventListener("close", () => {
    if (socket === ws) socket = null;
    lastSentKey = "";
    if (connectGeneration === generation) scheduleReconnect();
  });

  ws.addEventListener("error", () => {
    if (!isActive()) return;
    try {
      ws.close();
    } catch (_) {
      /* ignore */
    }
  });
}

chrome.runtime.onInstalled.addListener(() => {
  connect();
});

chrome.runtime.onStartup.addListener(() => {
  connect();
});

chrome.tabs.onActivated.addListener(async () => {
  await pushActiveTab();
});

chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (!tab.active) return;
  if (changeInfo.url || changeInfo.title || changeInfo.status === "complete") {
    await sendTabSnapshot(tab);
  }
});

chrome.windows.onFocusChanged.addListener(async (windowId) => {
  if (windowId === chrome.windows.WINDOW_ID_NONE) return;
  await pushActiveTab();
});

chrome.storage.onChanged.addListener((changes, area) => {
  if (area !== "local") return;
  if (changes.bridgePort || changes.bridgeToken) {
    if (socket) socket.close();
    connect();
  }
});

chrome.alarms.create("keepalive", { periodInMinutes: 1 });
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name !== "keepalive") return;
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    connect();
    return;
  }
  socket.send(JSON.stringify({ type: "ping" }));
});

connect();

function isJavdbUrl(url) {
  try {
    return /javdb/i.test(new URL(url).hostname);
  } catch (_) {
    return false;
  }
}

async function injectJavdbLayout(tabId) {
  for (const file of [
    "content/javdb-layout.js",
    "content/javdb-stickers.js",
    "content/javdb-actress-profile.js",
  ]) {
    try {
      await chrome.scripting.executeScript({
        target: { tabId },
        files: [file],
      });
    } catch (_) {
      /* already injected or restricted tab */
    }
  }
  for (const file of [
    "content/javdb-layout.css",
    "content/javdb-stickers.css",
    "content/javdb-actress-profile.css",
  ]) {
    try {
      await chrome.scripting.insertCSS({
        target: { tabId },
        files: [file],
      });
    } catch (_) {
      /* ignore */
    }
  }
}

chrome.tabs.onUpdated.addListener((tabId, changeInfo, tab) => {
  if (changeInfo.status === "complete" && tab.url && isJavdbUrl(tab.url)) {
    injectJavdbLayout(tabId);
  }
});

const MAGNET_FILTER_RULES_KEY = "magnetFilterRules";

function storeMagnetFilterRules(rules) {
  if (!rules || typeof rules !== "object") return;
  chrome.storage.local.set({ [MAGNET_FILTER_RULES_KEY]: rules }).catch(() => {});
}

function resolveMagnetFilterRulesWaiters(rules) {
  const waiters = magnetFilterRulesWaiters.splice(0);
  for (const resolve of waiters) {
    resolve(rules && typeof rules === "object" ? rules : null);
  }
}

function fetchMagnetFilterRulesFromDesktopAsync() {
  return new Promise((resolve) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      chrome.storage.local.get(MAGNET_FILTER_RULES_KEY, (stored) => {
        resolve(stored[MAGNET_FILTER_RULES_KEY] || null);
      });
      return;
    }

    magnetFilterRulesWaiters.push(resolve);
    if (magnetFilterRulesWaiters.length !== 1) return;

    socket.send(JSON.stringify({ type: "magnet_filter_rules_request" }));
    setTimeout(() => {
      if (magnetFilterRulesWaiters.length === 0) return;
      chrome.storage.local.get(MAGNET_FILTER_RULES_KEY, (stored) => {
        resolveMagnetFilterRulesWaiters(stored[MAGNET_FILTER_RULES_KEY] || null);
      });
    }, 8000);
  });
}

function requestMagnetFilterRulesFromDesktop() {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  fetchMagnetFilterRulesFromDesktopAsync().then((rules) => {
    if (rules) storeMagnetFilterRules(rules);
  });
}

function broadcastMagnetFilterRules(rules) {
  if (!rules) return;
  chrome.tabs.query({ url: ["https://javdb.com/*", "https://*.javdb.com/*"] }, (tabs) => {
    for (const tab of tabs) {
      chrome.tabs
        .sendMessage(tab.id, { type: "magnet_filter_rules_push", rules })
        .catch(() => {});
    }
  });
}

function broadcastStickerSync(data) {
  chrome.tabs.query({ url: ["https://javdb.com/*", "https://*.javdb.com/*"] }, (tabs) => {
    for (const tab of tabs) {
      chrome.tabs.sendMessage(tab.id, { type: "sticker_sync_push", data }).catch(() => {});
    }
  });
}

async function applyStateDbCleared(payload) {
  const empty = {
    blocked: {},
    verified: {},
    downloaded: {},
    marked: {},
    blockedSeries: {},
    blockedTitleKeywords: {},
    blockedActresses: {},
    blockedActressSeries: {},
    mediocreActresses: {},
    pendingDownloadActresses: {},
    magnetSavedVideos: {},
    videoDownloadedVideos: {},
    videoCrackedVideos: {},
    collectedActresses: {},
    actressByCode: {},
  };
  await chrome.storage.local.set({ javdbStickerData: empty });
  await chrome.storage.local.remove([
    "actressSyncLastDate",
    "actressSyncLastCount",
    "actressSyncLastAt",
    "actressAutoAttemptDate",
  ]);
  broadcastStickerSync(payload || {});
}

function requestStickerSyncFromDesktop() {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "sticker_sync_request" }));
}

async function pushLocalStickersToDesktop() {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  try {
    const stored = await chrome.storage.local.get("javdbStickerData");
    const data = stored.javdbStickerData;
    if (!data || typeof data !== "object") return;
    const hasData =
      Object.keys(data.blocked || {}).length > 0 ||
      Object.keys(data.verified || {}).length > 0 ||
      Object.keys(data.downloaded || {}).length > 0 ||
      Object.keys(data.marked || {}).length > 0 ||
      Object.keys(data.blockedSeries || {}).length > 0 ||
      Object.keys(data.blockedTitleKeywords || {}).length > 0 ||
      Object.keys(data.pendingDownloadActresses || {}).length > 0 ||
      Object.keys(data.blockedActresses || {}).length > 0 ||
      Object.keys(data.blockedActressSeries || {}).length > 0 ||
      Object.keys(data.mediocreActresses || {}).length > 0;
    if (!hasData) return;
    socket.send(JSON.stringify({ type: "sticker_bulk_upload", data }));
  } catch (_) {
    /* ignore */
  }
}

function getTodayKey() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

async function actressSyncedToday() {
  const stored = await chrome.storage.local.get("actressSyncLastDate");
  return stored.actressSyncLastDate === getTodayKey();
}

async function markActressSyncedLocal(lastDate, count, syncedAt) {
  await chrome.storage.local.set({
    actressSyncLastDate: lastDate || getTodayKey(),
    actressSyncLastCount: count || 0,
    actressSyncLastAt: syncedAt || "",
  });
}

function requestActressSyncInfo() {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "actress_sync_info_request" }));
}

function broadcastActressSyncStatus(payload) {
  chrome.tabs.query({ url: ["https://javdb.com/*", "https://*.javdb.com/*"] }, (tabs) => {
    for (const tab of tabs) {
      chrome.tabs.sendMessage(tab.id, { type: "actress_sync_status", ...payload }).catch(() => {});
    }
  });
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function getJavdbBaseUrl() {
  const tabs = await chrome.tabs.query({ url: ["https://javdb.com/*", "https://*.javdb.com/*"] });
  for (const tab of tabs) {
    if (!tab.url) continue;
    try {
      const parsed = new URL(tab.url);
      const localeMatch = parsed.pathname.match(/^\/(cn|en|ja)(?=\/|$)/i);
      const prefix = localeMatch ? `/${localeMatch[1].toLowerCase()}` : "";
      return `${parsed.origin}${prefix}`;
    } catch (_) {
      /* ignore */
    }
  }
  return "https://javdb.com";
}

async function getJavdbTabId() {
  const tabs = await chrome.tabs.query({ url: ["https://javdb.com/*", "https://*.javdb.com/*"] });
  for (const tab of tabs) {
    if (tab.id) return tab.id;
  }
  return null;
}

async function ensureJavdbTabForSync() {
  const baseUrl = await getJavdbBaseUrl();
  let tabId = await getJavdbTabId();
  if (tabId) {
    try {
      const tab = await chrome.tabs.get(tabId);
      const url = tab.url || "";
      if (/https?:\/\/([^/]+\.)?javdb\.com/i.test(url)) {
        return { tabId, baseUrl: new URL(url).origin };
      }
    } catch (_) {
      tabId = null;
    }
  }

  const collectionUrl = `${baseUrl}${ACTRESS_COLLECTION_PATH}`;
  const created = await chrome.tabs.create({ url: collectionUrl, active: false });
  if (!created.id) {
    throw new Error("无法打开 JavDB 收藏页，请手动打开 javdb.com 并登录后再同步");
  }
  await waitForTabComplete(created.id);
  return { tabId: created.id, baseUrl };
}

async function fetchCollectionPage(baseUrl, page) {
  const collections = globalThis.JM_pendingDownloadCollections;
  if (!collections?.fetchCollectionPage) {
    throw new Error("扩展模块未就绪，请在 chrome://extensions 重新加载扩展");
  }

  const { tabId, baseUrl: origin } = await ensureJavdbTabForSync();
  let pageData;
  try {
    pageData = await collections.fetchCollectionPage(tabId, origin || baseUrl, page);
  } catch (err) {
    throw new Error(`读取收藏女优页面失败：${err.message || err}`);
  }
  if (!pageData || typeof pageData !== "object") {
    throw new Error("无法解析 JavDB 收藏女优页面，请确认已登录 JavDB 且收藏列表可访问");
  }

  const actresses = (pageData.entries || []).map((entry) => ({
    javdb_id: entry.javdb_id,
    name: entry.name,
    profile_url: entry.profile_url,
    avatar_url: entry.avatar_url || "",
  }));

  return {
    actresses,
    maxPage: pageData.maxPage || 1,
    loginRequired: !!pageData.loginRequired,
  };
}

async function persistCollectedActressesLocal(actresses) {
  const map = {};
  for (const row of actresses || []) {
    const id = String(row.javdb_id || row.starId || row.id || "").trim();
    if (!id) continue;
    map[id] = {
      javdb_id: id,
      name: String(row.name || "").trim(),
      profile_url: String(row.profile_url || row.url || "").trim(),
      avatar_url: String(row.avatar_url || row.avatar || "").trim(),
    };
  }
  const stored = await chrome.storage.local.get("javdbStickerData");
  const data = { ...(stored.javdbStickerData || {}), collectedActresses: map };
  await chrome.storage.local.set({ javdbStickerData: data });
}

async function fetchAllActressesQuietly() {
  const baseUrl = await getJavdbBaseUrl();
  const all = new Map();
  let maxPage = 1;
  let loginRequired = false;

  for (let page = 1; page <= maxPage; page++) {
    const pageData = await fetchCollectionPage(baseUrl, page);
    if (!pageData || typeof pageData !== "object") {
      throw new Error("无法读取收藏女优页面数据");
    }
    if (pageData.loginRequired) {
      loginRequired = true;
      break;
    }
    maxPage = Math.max(maxPage, pageData.maxPage || 1);
    for (const actress of pageData.actresses || []) {
      all.set(actress.javdb_id, actress);
    }
    if (page < maxPage) await sleep(350);
  }

  return {
    loginRequired,
    actresses: Array.from(all.values()),
  };
}

function sendActressSyncToDesktop(payload) {
  return new Promise((resolve, reject) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      reject(new Error(`桌面程序未连接，请先运行 ${APP_DISPLAY_NAME}`));
      return;
    }
    if (pendingActressSync) {
      reject(new Error("上一次同步仍在等待桌面程序响应"));
      return;
    }
    pendingActressSync = { resolve, reject };
    socket.send(JSON.stringify({ type: "actress_sync", ...payload }));
    setTimeout(() => {
      if (pendingActressSync) {
        pendingActressSync.reject(new Error(`等待桌面程序响应超时，请确认 ${APP_DISPLAY_NAME} 正在运行`));
        pendingActressSync = null;
      }
    }, 20000);
  });
}

function broadcastMagnetTxtStatus(payload) {
  chrome.tabs.query({ url: ["https://javdb.com/*", "https://*.javdb.com/*"] }, (tabs) => {
    for (const tab of tabs) {
      chrome.tabs.sendMessage(tab.id, { type: "magnet_txt_status", ...payload }).catch(() => {});
    }
  });
}

function showMagnetTxtNotification(success, message, code, actionKey = "") {
  broadcastMagnetTxtStatus({
    status: success ? "done" : "error",
    code: code || "",
    message,
    actionKey: String(actionKey || ""),
  });
  try {
    chrome.notifications.create(`jm-magnet-txt-${Date.now()}`, {
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: success ? `${APP_DISPLAY_NAME} — 生成 TXT 完成` : `${APP_DISPLAY_NAME} — 生成 TXT 失败`,
      message: String(message || "").slice(0, 220),
      priority: 2,
    });
  } catch (_) {
    /* ignore */
  }
}

async function runGenerateMagnetTxtJob(payload) {
  const core = globalThis.JM_magnetTxtCore;
  if (!core) {
    showMagnetTxtNotification(false, "磁链后台模块未加载，请重新加载扩展。", payload?.code || "", "gentxt");
    return { ok: false };
  }
  if (singleMagnetTxtRunning) {
    return { ok: false, busy: true, message: "magnet_txt_busy" };
  }

  const code = String(payload?.code || payload || "").trim();
  const detailUrl = String(payload?.detailUrl || "").trim();
  const javdbMagnets = Array.isArray(payload?.javdbMagnets) ? payload.javdbMagnets : null;
  const actressHint = String(payload?.actress || "").trim();

  const jobId = ++magnetTxtJobSerial;
  const normalized = core.normalizeCode(code);
  singleMagnetTxtRunning = true;
  broadcastMagnetTxtStatus({
    status: "running",
    code: normalized,
    jobId,
    actionKey: "gentxt",
    message: `${normalized}：正在执行 4K / 字幕 / 高清磁链筛查…`,
  });

  try {
    const rules = await core.loadFilterRules(fetchMagnetFilterRulesFromDesktopAsync);
    const picked = await core.pickMagnetForTxt({
      code,
      detailUrl,
      javdbMagnets,
      actressHint,
      rulesConfig: rules,
    });
    const desktop = await writeMagnetTxtToDesktop({
      filename: picked.filename,
      content: picked.magnet,
      code: normalized,
      allowEmpty: Boolean(picked.empty),
    });

    if (!desktop.ok) {
      const hint = desktop.offline
        ? `桌面未连接，无法写入指定目录。请启动 ${APP_DISPLAY_NAME} 并保持扩展已配对。`
        : desktop.message || "桌面保存失败";
      throw new Error(hint);
    }

    const detail = picked.empty
      ? "无合适资源"
      : `${picked.stageLabel}${picked.priority ? ` · 优先级 ${picked.priority}` : ""}${picked.source ? ` · ${picked.source}` : ""}`;
    const msg = `已保存：${desktop.path || picked.filename}（${detail}）`;
    showMagnetTxtNotification(true, msg, normalized, "gentxt");
    await markDownloadedAfterBatchMatch({
      code: normalized,
      title: String(payload?.title || ""),
      detail_url: detailUrl,
      has_subtitle: picked.stage === "subtitle",
      is_4k: picked.stage === "4k",
      folder_name: actressHint,
    });
    return { ok: true, filename: picked.filename, path: desktop.path, stage: picked.stage };
  } catch (err) {
    const message = String(err.message || err);
    showMagnetTxtNotification(false, message, normalized, "gentxt");
    return { ok: false, message };
  } finally {
    singleMagnetTxtRunning = false;
  }
}

async function runSave115FilteredJob(payload) {
  const core = globalThis.JM_magnetTxtCore;
  if (!core) {
    showMagnetTxtNotification(false, "磁链后台模块未加载，请重新加载扩展。", payload?.code || "", "save115");
    return { ok: false };
  }
  if (singleMagnetTxtRunning) {
    return { ok: false, busy: true, message: "magnet_txt_busy" };
  }

  const code = String(payload?.code || "").trim();
  const detailUrl = String(payload?.detailUrl || "").trim();
  const javdbMagnets = Array.isArray(payload?.javdbMagnets) ? payload.javdbMagnets : null;
  const actressHint = String(payload?.actress || "").trim();
  const normalized = core.normalizeCode(code);
  singleMagnetTxtRunning = true;
  broadcastMagnetTxtStatus({
    status: "running",
    code: normalized,
    actionKey: "save115",
    message: `${normalized}：正在筛选磁链并提交 115…`,
  });

  try {
    const rules = await core.loadFilterRules(fetchMagnetFilterRulesFromDesktopAsync);
    const picked = await core.pickMagnetForTxt({
      code,
      detailUrl,
      javdbMagnets,
      actressHint,
      rulesConfig: rules,
    });

    if (picked.empty || !picked.magnet?.startsWith("magnet:")) {
      throw new Error("无合适资源");
    }

    await globalThis.JM_detailTools.add115OfflineTask(picked.magnet);

    const detail = picked.empty
      ? "无合适资源"
      : `${picked.stageLabel}${picked.priority ? ` · 优先级 ${picked.priority}` : ""}${picked.source ? ` · ${picked.source}` : ""}`;
    showMagnetTxtNotification(true, `已提交 115 离线下载（${detail}）`, normalized, "save115");
    await markDownloadedAfterBatchMatch({
      code: normalized,
      title: String(payload?.title || ""),
      detail_url: detailUrl,
      has_subtitle: picked.stage === "subtitle",
      is_4k: picked.stage === "4k",
      folder_name: actressHint,
    });
    return { ok: true, stage: picked.stage };
  } catch (err) {
    const message = String(err.message || err);
    showMagnetTxtNotification(false, message, normalized, "save115");
    return { ok: false, message };
  } finally {
    singleMagnetTxtRunning = false;
  }
}

function broadcastListVisibilityRefresh() {
  chrome.tabs.query({ url: ["https://javdb.com/*", "https://*.javdb.com/*"] }, (tabs) => {
    for (const tab of tabs) {
      chrome.tabs.sendMessage(tab.id, { type: "refresh_list_visibility" }).catch(() => {});
    }
  });
}

function showActressResultAlert(success, message) {
  broadcastActressSyncStatus({
    status: success ? "done" : "error",
    message,
    showAlert: true,
    success,
  });
  try {
    chrome.notifications.create(`jm-actress-${Date.now()}`, {
      type: "basic",
      iconUrl: "icons/icon128.png",
      title: success ? `${APP_DISPLAY_NAME} — 收藏女优同步完成` : `${APP_DISPLAY_NAME} — 收藏女优同步失败`,
      message: message.slice(0, 220),
      priority: 2,
    });
  } catch (_) {
    /* ignore */
  }
}

async function runActressSync({ force = false, reason = "manual" } = {}) {
  if (actressSyncRunning) {
    return { ok: false, busy: true, message: "同步正在进行中" };
  }
  if (!force && (await actressSyncedToday())) {
    const message = "今日已同步过收藏女优";
    return { ok: false, skipped: true, message };
  }

  if (!force) {
    const stored = await chrome.storage.local.get("actressAutoAttemptDate");
    if (stored.actressAutoAttemptDate === getTodayKey()) {
      return { ok: false, skipped: true };
    }
    await chrome.storage.local.set({ actressAutoAttemptDate: getTodayKey() });
  }

  actressSyncRunning = true;
  broadcastActressSyncStatus({ status: "running", message: "正在后台同步收藏女优…" });

  try {
    const { loginRequired, actresses } = await fetchAllActressesQuietly();

    if (loginRequired) {
      const message = "请先登录 JavDB 后再同步";
      showActressResultAlert(false, message);
      return { ok: false, loginRequired: true, message, alertShown: true };
    }

    if (!actresses.length) {
      const message = "未找到收藏女优，请确认已登录 JavDB 且收藏列表不为空";
      showActressResultAlert(false, message);
      return { ok: false, message, alertShown: true };
    }

    await persistCollectedActressesLocal(actresses);

    const syncedAt = new Date().toISOString().replace("T", " ").slice(0, 19);
    const ack = await sendActressSyncToDesktop({
      actresses,
      synced_at: syncedAt,
      forced: force,
      reason,
    });

    await markActressSyncedLocal(ack.last_sync_date, ack.count ?? ack.last_count, ack.last_sync_at);
    requestStickerSyncFromDesktop();
    const message = `已成功同步 ${ack.count ?? ack.last_count ?? actresses.length} 位女优`;
    showActressResultAlert(true, message);
    return {
      ok: true,
      count: ack.count ?? ack.last_count ?? actresses.length,
      syncedAt: ack.last_sync_at || syncedAt,
      message,
      alertShown: true,
    };
  } catch (err) {
    const message = String(err.message || err);
    showActressResultAlert(false, message);
    return { ok: false, message, alertShown: true };
  } finally {
    actressSyncRunning = false;
  }
}

function sendPendingDownloadProgress(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "pending_download_sync_progress", ...payload }));
}

function sendPendingDownloadDone(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "pending_download_sync_done", ...payload }));
}

function waitForTabComplete(tabId, timeoutMs = 45000) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = (fn) => {
      if (settled) return;
      settled = true;
      chrome.tabs.onUpdated.removeListener(onUpdated);
      fn();
    };

    function onUpdated(updatedTabId, changeInfo) {
      if (updatedTabId !== tabId) return;
      if (changeInfo.status === "complete") {
        finish(resolve);
      }
    }

    chrome.tabs.onUpdated.addListener(onUpdated);
    chrome.tabs
      .get(tabId)
      .then((tab) => {
        if (tab.status === "complete") {
          finish(resolve);
        }
      })
      .catch((err) => {
        finish(() => reject(err));
      });

    setTimeout(() => {
      finish(() => reject(new Error("页面加载超时")));
    }, timeoutMs);
  });
}

function isFrameRemovedError(err) {
  return /frame with id 0 was removed/i.test(String(err?.message || err || ""));
}

async function resolveTabIdFromWindow(win, readyUrl = "") {
  let tabId = win?.tabs?.[0]?.id;
  if (!tabId && win?.id != null) {
    for (let attempt = 0; attempt < 24; attempt += 1) {
      const tabs = await chrome.tabs.query({ windowId: win.id });
      tabId = tabs[0]?.id;
      if (tabId) break;
      await sleep(150);
    }
  }
  if (!tabId) {
    throw new Error("无法创建后台同步窗口");
  }
  await waitForTabStable(tabId, readyUrl);
  return tabId;
}

async function waitForTabStable(tabId, readyUrl = "", ensureHiddenFn = async () => {}) {
  await waitForTabComplete(tabId);
  await ensureHiddenFn();
  let url = String(readyUrl || "").trim();
  for (let attempt = 0; attempt < 8; attempt += 1) {
    const tab = await chrome.tabs.get(tabId);
    const currentUrl = String(tab.url || "");
    if (/^https?:\/\//i.test(currentUrl) && tab.status === "complete") {
      return currentUrl;
    }
    if (!url) {
      await sleep(400);
      continue;
    }
    await chrome.tabs.update(tabId, { url, active: false });
    await waitForTabComplete(tabId);
    await ensureHiddenFn();
    await sleep(500 + attempt * 150);
  }
  const tab = await chrome.tabs.get(tabId);
  const currentUrl = String(tab.url || "");
  if (!/^https?:\/\//i.test(currentUrl)) {
    throw new Error(`后台标签页未就绪（当前: ${currentUrl || "空白"}）`);
  }
  return currentUrl;
}

async function navigateWorkerTab(tabId, url, ensureHiddenFn = async () => {}) {
  const target = String(url || "").trim();
  if (!/^https?:\/\//i.test(target)) {
    throw new Error("无效导航地址");
  }
  await ensureHiddenFn();
  await chrome.tabs.update(tabId, { url: target, active: false });
  await waitForTabStable(tabId, target, ensureHiddenFn);
}

async function getPendingDownloadMarkTab(baseUrl) {
  if (pendingDownloadMarkTabId) {
    try {
      await chrome.tabs.get(pendingDownloadMarkTabId);
      return pendingDownloadMarkTabId;
    } catch (_) {
      pendingDownloadMarkTabId = null;
    }
  }

  const tab = await chrome.tabs.create({ url: baseUrl, active: false });
  pendingDownloadMarkTabId = tab.id;
  await waitForTabComplete(tab.id);
  return tab.id;
}

async function invokePendingDownloadMark(tabId, message) {
  try {
    const response = await chrome.tabs.sendMessage(tabId, message);
    if (response?.ok) return response;
    return { ok: false, message: response?.message || "标记失败" };
  } catch (_) {
    /* fall through to executeScript */
  }

  const maxAttempts = 4;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      const injection = await chrome.scripting.executeScript({
        target: { tabId },
        func: async (msg) => {
          if (typeof window.__JM_handlePendingDownloadMark === "function") {
            return await window.__JM_handlePendingDownloadMark(msg);
          }
          return { ok: false, message: "content script not ready" };
        },
        args: [message],
      });
      const frame = injection?.[0];
      if (frame?.error) {
        throw new Error(frame.error.message || String(frame.error));
      }
      const result = frame?.result;
      if (result?.ok) return result;
      return { ok: false, message: result?.message || "content script not ready" };
    } catch (err) {
      if (isFrameRemovedError(err) && attempt < maxAttempts - 1) {
        await sleep(500 + attempt * 300);
        await waitForTabComplete(tabId, 15000).catch(() => {});
        continue;
      }
      return { ok: false, message: String(err.message || err) };
    }
  }
  return { ok: false, message: "content script not ready" };
}

async function markPendingDownloadOnTab(tabId, message) {
  await injectJavdbLayout(tabId);

  let lastError = "无法注入待下载标记";
  for (let attempt = 0; attempt < 12; attempt++) {
    await sleep(attempt === 0 ? 1200 : 650);
    const ping = await invokePendingDownloadMark(tabId, { type: "ping" });
    if (!ping?.ok) {
      lastError = ping?.message || lastError;
      continue;
    }
    const result = await invokePendingDownloadMark(tabId, message);
    if (result?.ok) return result;
    lastError = result?.message || lastError;
  }
  throw new Error(lastError);
}

async function markActressPendingDownloadInBackground(item, baseUrl) {
  const actress = item.actress;
  if (!actress?.profile_url) {
    throw new Error("缺少女优主页地址");
  }

  const tabId = await getPendingDownloadMarkTab(baseUrl);
  await chrome.tabs.update(tabId, { url: actress.profile_url, active: false });
  await waitForTabComplete(tabId);
  return markPendingDownloadOnTab(tabId, {
    type: "mark_pending_download",
    actress: {
      javdb_id: actress.javdb_id,
      name: actress.name,
      folder_name: item.folder_name,
      profile_url: actress.profile_url,
    },
  });
}

async function resolveFolderMatch(folderName, actresses) {
  const collections = globalThis.JM_pendingDownloadCollections;
  const actress = collections.matchFolderInActresses(folderName, actresses);
  if (!actress) {
    return null;
  }
  return { actress, match_source: "collection_actors" };
}

async function runPendingDownloadSync(request) {
  if (pendingDownloadSyncRunning) {
    sendPendingDownloadDone({
      session_id: request.session_id || "",
      results: [],
      error: "待下载同步正在进行中",
      log_roots: request.log_roots || [],
      folder_names: request.folder_names || [],
    });
    return;
  }

  const folders = Array.isArray(request.folders)
    ? request.folders
    : (request.folder_names || []).map((folder_name) => ({ folder_name, folder_path: "", root: "" }));
  const logRoots = Array.isArray(request.log_roots) ? request.log_roots : [];
  const sessionId = request.session_id || "";
  const collections = globalThis.JM_pendingDownloadCollections;

  if (!folders.length) {
    sendPendingDownloadDone({
      session_id: sessionId,
      results: [],
      error: "待下载目录下没有女优文件夹",
      log_roots: logRoots,
      folder_names: [],
    });
    return;
  }

  pendingDownloadSyncRunning = true;
  const results = [];

  try {
    const baseUrl = await getJavdbBaseUrl();
    let fetchTabId = await getJavdbTabId();
    if (!fetchTabId) {
      fetchTabId = await getPendingDownloadMarkTab(baseUrl);
    }

    sendPendingDownloadProgress({
      phase: "collection",
      message: "后台抓取收藏女优列表（含翻页）…",
      current: 0,
      total: folders.length,
    });

    const actressResult = await collections.fetchAllCollectionEntries(
      fetchTabId,
      baseUrl,
      collections.ACTRESS_COLLECTION_PATH,
      "actors",
      sleep
    );
    if (actressResult.loginRequired) {
      sendPendingDownloadDone({
        session_id: sessionId,
        results: folders.map((folder) => ({
          folder_name: folder.folder_name,
          folder_path: folder.folder_path || "",
          ok: false,
          error: "请先登录 JavDB",
        })),
        error: "请先登录 JavDB",
        log_roots: logRoots,
        folder_names: folders.map((f) => f.folder_name),
      });
      return;
    }

    const actresses = actressResult.entries || [];
    const pendingFolders = [];

    sendPendingDownloadProgress({
      phase: "matching",
      message: "正在对照文件夹名称与收藏女优（简繁/英文模糊匹配）…",
      current: 0,
      total: folders.length,
    });

    for (const folder of folders) {
      const folderName = folder.folder_name;
      let resolved = await resolveFolderMatch(folderName, actresses);
      if (!resolved) {
        try {
          const searchTabId = fetchTabId || (await getPendingDownloadMarkTab(baseUrl));
          const actress = await resolveActressProfileFromSearch(searchTabId, folderName, baseUrl);
          if (actress) {
            resolved = { actress, match_source: "javdb_search" };
          }
        } catch (_) {
          /* fall through to unmatched */
        }
      }
      if (!resolved) {
        const unmatchedItem = {
          folder_name: folderName,
          folder_path: folder.folder_path || "",
          ok: false,
          error: "收藏女优与 JavDB 搜索均未找到",
        };
        results.push(unmatchedItem);
        sendPendingDownloadProgress({
          phase: "export",
          message: `正在写入：${folderName}`,
          current: results.length,
          total: folders.length,
        });
        await applySyncFolderExport(
          "pending_download_sync_folder_done",
          {
            session_id: sessionId,
            log_roots: logRoots,
            folder_result: unmatchedItem,
          },
          unmatchedItem
        );
        continue;
      }
      pendingFolders.push({
        folder_name: folderName,
        folder_path: folder.folder_path || "",
        root: folder.root || "",
        actress: resolved.actress,
        match_source: resolved.match_source,
        ok: true,
      });
    }

    for (let index = 0; index < pendingFolders.length; index++) {
      const item = pendingFolders[index];
      sendPendingDownloadProgress({
        phase: "marking",
        message: `后台标记：${item.folder_name}`,
        current: index + 1,
        total: pendingFolders.length,
      });
      let folderResult;
      try {
        await markActressPendingDownloadInBackground(item, baseUrl);
        folderResult = {
          folder_name: item.folder_name,
          folder_path: item.folder_path,
          actress: item.actress,
          match_source: item.match_source,
          ok: true,
          marked: true,
        };
      } catch (err) {
        folderResult = {
          folder_name: item.folder_name,
          folder_path: item.folder_path,
          actress: item.actress,
          match_source: item.match_source,
          ok: false,
          marked: false,
          error: String(err.message || err),
        };
      }
      results.push(folderResult);
      sendPendingDownloadProgress({
        phase: "export",
        message: `正在写入：${folderResult.folder_name}`,
        current: index + 1,
        total: pendingFolders.length,
      });
      await applySyncFolderExport(
        "pending_download_sync_folder_done",
        {
          session_id: sessionId,
          log_roots: logRoots,
          folder_result: folderResult,
        },
        folderResult
      );
      await sleep(350);
    }

    sendPendingDownloadDone({
      session_id: sessionId,
      results,
      error: "",
      log_roots: logRoots,
      folder_names: folders.map((f) => f.folder_name),
    });
  } catch (err) {
    sendPendingDownloadDone({
      session_id: sessionId,
      results,
      error: String(err.message || err),
      log_roots: logRoots,
      folder_names: folders.map((f) => f.folder_name),
    });
  } finally {
    pendingDownloadSyncRunning = false;
  }
}

function sendMagnetSavedProgress(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "magnet_saved_sync_progress", ...payload }));
}

function sendMagnetSavedDone(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "magnet_saved_sync_done", ...payload }));
}

async function releaseMagnetSavedWorker() {
  magnetSavedMarkTabId = null;
  if (magnetSavedWorkerWindowId == null) return;
  try {
    await chrome.windows.remove(magnetSavedWorkerWindowId);
  } catch (_) {
    /* window may already be closed */
  }
  magnetSavedWorkerWindowId = null;
}

async function ensureMagnetSavedWorkerHidden() {
  if (magnetSavedWorkerWindowId == null) return;
  try {
    await chrome.windows.update(magnetSavedWorkerWindowId, {
      focused: false,
      state: "minimized",
    });
  } catch (_) {
    /* ignore */
  }
}

async function getMagnetSavedMarkTab(baseUrl) {
  if (magnetSavedMarkTabId) {
    try {
      await chrome.tabs.get(magnetSavedMarkTabId);
      await ensureMagnetSavedWorkerHidden();
      return magnetSavedMarkTabId;
    } catch (_) {
      await releaseMagnetSavedWorker();
    }
  }

  const win = await chrome.windows.create({
    url: baseUrl,
    state: "minimized",
    focused: false,
  });
  magnetSavedWorkerWindowId = win.id;
  magnetSavedMarkTabId = win.tabs?.[0]?.id;
  if (!magnetSavedMarkTabId) {
    await releaseMagnetSavedWorker();
    throw new Error("无法创建后台同步窗口");
  }
  await waitForTabComplete(magnetSavedMarkTabId);
  await ensureMagnetSavedWorkerHidden();
  return magnetSavedMarkTabId;
}

async function invokeStickerAction(tabId, message) {
  try {
    const response = await chrome.tabs.sendMessage(tabId, message);
    if (response?.ok) return response;
    return { ok: false, message: response?.message || "操作失败" };
  } catch (_) {
    /* fall through */
  }

  const maxAttempts = 4;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      const injection = await chrome.scripting.executeScript({
        target: { tabId },
        func: async (msg) => {
          if (typeof window.__JM_handleStickerMessage === "function") {
            return await window.__JM_handleStickerMessage(msg);
          }
          return { ok: false, message: "content script not ready" };
        },
        args: [message],
      });
      const frame = injection?.[0];
      if (frame?.error) {
        throw new Error(frame.error.message || String(frame.error));
      }
      const result = frame?.result;
      if (result?.ok) return result;
      return { ok: false, message: result?.message || "content script not ready" };
    } catch (err) {
      if (isFrameRemovedError(err) && attempt < maxAttempts - 1) {
        await sleep(500 + attempt * 300);
        await waitForTabComplete(tabId, 15000).catch(() => {});
        continue;
      }
      return { ok: false, message: String(err.message || err) };
    }
  }
  return { ok: false, message: "content script not ready" };
}

async function applyDownloadedStickerOnTab(tabId, code, extra = {}) {
  await injectJavdbLayout(tabId);
  const message = {
    type: "apply_sticker_action",
    action: "downloaded",
    code: String(code || "").trim(),
    ...extra,
  };

  let lastError = "无法标记已下载";
  for (let attempt = 0; attempt < 12; attempt++) {
    await sleep(attempt === 0 ? 1200 : 650);
    const ping = await invokeStickerAction(tabId, { type: "ping" });
    if (!ping?.ok) {
      lastError = ping?.message || lastError;
      continue;
    }
    const result = await invokeStickerAction(tabId, message);
    if (result?.ok) return result;
    lastError = result?.message || lastError;
  }
  throw new Error(lastError);
}

async function refreshActressListVisibility(tabId, profileUrl, ensureHiddenFn = async () => {}) {
  const url = String(profileUrl || "").trim();
  if (!url) return;
  try {
    await ensureHiddenFn();
    await chrome.tabs.update(tabId, { url, active: false });
    await waitForTabComplete(tabId);
    await ensureHiddenFn();
    await injectJavdbLayout(tabId);
    await invokeStickerAction(tabId, { type: "refresh_list_visibility" });
  } catch (_) {
    /* non-fatal */
  }
}

async function applyMagnetSavedVideoMarkOnTab(tabId, payload) {
  await injectJavdbLayout(tabId);
  const message = {
    type: "mark_magnet_saved_video",
    video: payload,
  };

  let lastError = "无法在详情页标记磁链已保存";
  for (let attempt = 0; attempt < 12; attempt++) {
    await sleep(attempt === 0 ? 1200 : 650);
    const ping = await invokeStickerAction(tabId, { type: "ping" });
    if (!ping?.ok) {
      lastError = ping?.message || lastError;
      continue;
    }
    const result = await invokeStickerAction(tabId, message);
    if (result?.ok) return result;
    lastError = result?.message || lastError;
  }
  throw new Error(lastError);
}

async function markMagnetSavedActressOnTab(tabId, message) {
  await injectJavdbLayout(tabId);

  let lastError = "无法注入磁链已保存标记";
  for (let attempt = 0; attempt < 12; attempt++) {
    await sleep(attempt === 0 ? 1200 : 650);
    const ping = await invokePendingDownloadMark(tabId, { type: "ping" });
    if (!ping?.ok) {
      lastError = ping?.message || lastError;
      continue;
    }
    const result = await invokePendingDownloadMark(tabId, message);
    if (result?.ok) return result;
    lastError = result?.message || lastError;
  }
  throw new Error(lastError);
}

function copyMagnetMediaFlags(item) {
  return {
    has_subtitle: Boolean(item?.has_subtitle),
    is_4k: Boolean(item?.is_4k),
    has_subtitle_file: Boolean(item?.has_subtitle_file),
    has_subtitle_magnet: Boolean(item?.has_subtitle_magnet),
    four_k_has_subtitle: Boolean(item?.four_k_has_subtitle),
    four_k_has_subtitle_file: Boolean(item?.four_k_has_subtitle_file),
    four_k_has_subtitle_via_ch: Boolean(item?.four_k_has_subtitle_via_ch),
    subtitle_extract_for_4k: Boolean(item?.subtitle_extract_for_4k),
  };
}

function buildMagnetCodeResult(item, extra = {}) {
  return {
    code: item.code,
    source_file: item.source_file || "",
    source_line: item.source_line || 0,
    ...copyMagnetMediaFlags(item),
    ...extra,
  };
}

async function runMagnetSavedSync(request) {
  if (magnetSavedSyncRunning) {
    sendMagnetSavedDone({
      session_id: request.session_id || "",
      folder_results: [],
      error: "磁链已保存同步正在进行中",
      log_roots: request.log_roots || [],
    });
    return;
  }

  const folders = Array.isArray(request.folders) ? request.folders : [];
  const logRoots = Array.isArray(request.log_roots) ? request.log_roots : [];
  const sessionId = request.session_id || "";
  const collections = globalThis.JM_pendingDownloadCollections;
  const magnetSync = globalThis.JM_magnetSavedSync;

  if (!folders.length) {
    sendMagnetSavedDone({
      session_id: sessionId,
      folder_results: [],
      error: "磁链已保存目录下没有可处理的女优文件夹",
      log_roots: logRoots,
    });
    return;
  }

  magnetSavedSyncRunning = true;
  const folderResults = [];

  try {
    const baseUrl = await getJavdbBaseUrl();
    const tabId = await getMagnetSavedMarkTab(baseUrl);

    sendMagnetSavedProgress({
      phase: "collection",
      message: "后台抓取收藏女优列表（含翻页）…",
      current: 0,
      total: folders.length,
    });

    const actressResult = await collections.fetchAllCollectionEntries(
      tabId,
      baseUrl,
      collections.ACTRESS_COLLECTION_PATH,
      "actors",
      sleep
    );
    if (actressResult.loginRequired) {
      sendMagnetSavedDone({
        session_id: sessionId,
        folder_results: folders.map((folder) => ({
          folder_name: folder.folder_name,
          folder_path: folder.folder_path || "",
          ok: false,
          error: "请先登录 JavDB",
          code_results: [],
          total_codes: (folder.codes || []).length,
          success_codes: 0,
          fail_codes: (folder.codes || []).length,
        })),
        error: "请先登录 JavDB",
        log_roots: logRoots,
      });
      return;
    }

    const actresses = actressResult.entries || [];

    for (let index = 0; index < folders.length; index++) {
      const folder = folders[index];
      const codes = Array.isArray(folder.codes) ? folder.codes : [];
      sendMagnetSavedProgress({
        phase: "marking",
        message: `正在处理：${folder.folder_name}`,
        current: index + 1,
        total: folders.length,
      });

      const matchName = String(folder.actress_match_name || folder.folder_name || "").trim();
      const actress = collections.matchFolderInActresses(matchName, actresses);

      const codeResults = [];
      let actressMarked = false;
      let videoMap = {};
      try {
        if (actress) {
          await ensureMagnetSavedWorkerHidden();
          await chrome.tabs.update(tabId, { url: actress.profile_url, active: false });
          await waitForTabComplete(tabId);
          await ensureMagnetSavedWorkerHidden();

          try {
            await markMagnetSavedActressOnTab(tabId, {
              type: "mark_magnet_saved_actress",
              actress: {
                javdb_id: actress.javdb_id,
                name: actress.name,
                folder_name: folder.folder_name,
                profile_url: actress.profile_url,
                storage_type: folder.storage_type || "local_magnet",
              },
            });
            actressMarked = true;
          } catch (markErr) {
            codeResults.push({
              code: "-",
              ok: false,
              error: `女优页标记失败: ${String(markErr.message || markErr)}`,
              has_subtitle: false,
            });
          }

          videoMap = await magnetSync.fetchActressVideoMap(tabId, actress.profile_url, baseUrl, sleep);
        }

        for (const item of codes) {
          const code = String(item.code || "").trim().toUpperCase();
          if (!code) continue;
          let detailUrl;
          try {
            detailUrl = await resolveDetailUrlForCode(
              tabId,
              code,
              baseUrl,
              videoMap,
              ensureMagnetSavedWorkerHidden
            );
          } catch (searchErr) {
            codeResults.push({
              code,
              ok: false,
              error: String(searchErr.message || searchErr),
              ...buildMagnetCodeResult(item),
            });
            continue;
          }

          try {
            await ensureMagnetSavedWorkerHidden();
            await chrome.tabs.update(tabId, { url: detailUrl, active: false });
            await waitForTabComplete(tabId);
            await ensureMagnetSavedWorkerHidden();
            await applyDownloadedStickerOnTab(tabId, code, {
              detail_url: detailUrl,
              page_url: detailUrl,
            });
            await applyMagnetSavedVideoMarkOnTab(tabId, {
              code,
              storage_type: folder.storage_type || "local_magnet",
              has_subtitle: Boolean(item.has_subtitle),
              is_4k: Boolean(item.is_4k),
              detail_url: detailUrl,
              folder_name: folder.folder_name,
            });
            codeResults.push({
              code,
              ok: true,
              ...buildMagnetCodeResult(item),
            });
          } catch (err) {
            codeResults.push({
              code,
              ok: false,
              error: String(err.message || err),
              ...buildMagnetCodeResult(item),
            });
          }
          await sleep(300);
        }

        if (actress?.profile_url) {
          await refreshActressListVisibility(tabId, actress.profile_url, ensureMagnetSavedWorkerHidden);
        }
      } catch (err) {
        for (const item of codes) {
          const code = String(item.code || "").trim().toUpperCase();
          if (!code) continue;
          const existing = codeResults.find((row) => row.code === code);
          if (!existing) {
            codeResults.push({
              code,
              ok: false,
              error: String(err.message || err),
              ...buildMagnetCodeResult(item),
            });
          }
        }
      }

      const realCodeResults = codeResults.filter((row) => row.code !== "-");
      const successCodes = realCodeResults.filter((row) => row.ok).length;
      const folderResult = {
        folder_name: folder.folder_name,
        folder_path: folder.folder_path || "",
        actress: actress || null,
        storage_type: folder.storage_type || "local_magnet",
        actress_marked: actressMarked,
        ok: successCodes > 0 || actressMarked,
        error:
          successCodes > 0
            ? ""
            : actressMarked
              ? "全部番号标记失败"
              : actress
                ? "女优页标记与番号同步均失败"
                : "全部番号标记失败（收藏女优未匹配，已尝试番号搜索）",
        code_results: realCodeResults.length ? realCodeResults : codeResults,
        total_codes: codes.length,
        success_codes: successCodes,
        fail_codes: codes.length - successCodes,
      };
      folderResults.push(folderResult);
      sendMagnetSavedProgress({
        phase: "export",
        message: `正在写入：${folder.folder_name}`,
        current: index + 1,
        total: folders.length,
      });
      await applySyncFolderExport(
        "magnet_saved_sync_folder_done",
        {
          session_id: sessionId,
          log_roots: logRoots,
          folder_result: folderResult,
        },
        folderResult
      );
      await sleep(400);
    }

    sendMagnetSavedDone({
      session_id: sessionId,
      folder_results: folderResults,
      error: "",
      log_roots: logRoots,
    });
  } catch (err) {
    sendMagnetSavedDone({
      session_id: sessionId,
      folder_results: folderResults,
      error: String(err.message || err),
      log_roots: logRoots,
    });
  } finally {
    magnetSavedSyncRunning = false;
    await releaseMagnetSavedWorker();
  }
}

function sendVideoDownloadedProgress(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "video_downloaded_sync_progress", ...payload }));
}

function sendVideoDownloadedDone(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "video_downloaded_sync_done", ...payload }));
}

async function releaseVideoDownloadedWorker() {
  videoDownloadedMarkTabId = null;
  if (videoDownloadedWorkerWindowId == null) return;
  try {
    await chrome.windows.remove(videoDownloadedWorkerWindowId);
  } catch (_) {
    /* ignore */
  }
  videoDownloadedWorkerWindowId = null;
}

async function ensureVideoDownloadedWorkerHidden() {
  if (videoDownloadedWorkerWindowId == null) return;
  try {
    await chrome.windows.update(videoDownloadedWorkerWindowId, {
      focused: false,
      state: "minimized",
    });
  } catch (_) {
    /* ignore */
  }
}

async function getVideoDownloadedMarkTab(baseUrl) {
  if (videoDownloadedMarkTabId) {
    try {
      await chrome.tabs.get(videoDownloadedMarkTabId);
      await ensureVideoDownloadedWorkerHidden();
      return videoDownloadedMarkTabId;
    } catch (_) {
      await releaseVideoDownloadedWorker();
    }
  }

  const win = await chrome.windows.create({
    url: baseUrl,
    state: "minimized",
    focused: false,
  });
  videoDownloadedWorkerWindowId = win.id;
  videoDownloadedMarkTabId = await resolveTabIdFromWindow(win, baseUrl);
  await ensureVideoDownloadedWorkerHidden();
  return videoDownloadedMarkTabId;
}

async function markVideoDownloadedActressOnTab(tabId, message) {
  await injectJavdbLayout(tabId);
  let lastError = "无法注入已下载标记";
  for (let attempt = 0; attempt < 12; attempt++) {
    await sleep(attempt === 0 ? 1200 : 650);
    const ping = await invokePendingDownloadMark(tabId, { type: "ping" });
    if (!ping?.ok) {
      lastError = ping?.message || lastError;
      continue;
    }
    const result = await invokePendingDownloadMark(tabId, message);
    if (result?.ok) return result;
    lastError = result?.message || lastError;
  }
  throw new Error(lastError);
}

async function applyVideoDownloadedMarkOnTab(tabId, payload) {
  await injectJavdbLayout(tabId);
  const message = { type: "mark_video_downloaded", video: payload };
  let lastError = "无法在详情页标记已下载";
  for (let attempt = 0; attempt < 12; attempt++) {
    await sleep(attempt === 0 ? 1200 : 650);
    const ping = await invokeStickerAction(tabId, { type: "ping" });
    if (!ping?.ok) {
      lastError = ping?.message || lastError;
      continue;
    }
    const result = await invokeStickerAction(tabId, message);
    if (result?.ok) return result;
    lastError = result?.message || lastError;
  }
  throw new Error(lastError);
}

function copyVideoDownloadedFlags(item) {
  return {
    has_subtitle: Boolean(item?.has_subtitle),
    is_4k: Boolean(item?.is_4k),
    has_subtitle_file: Boolean(item?.has_subtitle_file),
    has_subtitle_name: Boolean(item?.has_subtitle_name),
  };
}

function buildVideoDownloadedCodeResult(item, extra = {}) {
  return {
    code: item.code,
    source_file: item.source_file || "",
    ...copyVideoDownloadedFlags(item),
    ...extra,
  };
}

async function runVideoDownloadedSync(request) {
  if (videoDownloadedSyncRunning) {
    sendVideoDownloadedDone({
      session_id: request.session_id || "",
      folder_results: [],
      error: "影片已下载同步正在进行中",
      log_roots: request.log_roots || [],
    });
    return;
  }

  const folders = Array.isArray(request.folders) ? request.folders : [];
  const logRoots = Array.isArray(request.log_roots) ? request.log_roots : [];
  const sessionId = request.session_id || "";
  const collections = globalThis.JM_pendingDownloadCollections;
  const magnetSync = globalThis.JM_magnetSavedSync;

  if (!folders.length) {
    sendVideoDownloadedDone({
      session_id: sessionId,
      folder_results: [],
      error: "影片已下载目录下没有可处理的女优文件夹",
      log_roots: logRoots,
    });
    return;
  }

  videoDownloadedSyncRunning = true;
  const folderResults = [];

  try {
    const baseUrl = await getJavdbBaseUrl();
    const tabId = await getVideoDownloadedMarkTab(baseUrl);

    sendVideoDownloadedProgress({
      phase: "collection",
      message: "后台抓取收藏女优列表（含翻页）…",
      current: 0,
      total: folders.length,
    });

    const actressResult = await collections.fetchAllCollectionEntries(
      tabId,
      baseUrl,
      collections.ACTRESS_COLLECTION_PATH,
      "actors",
      sleep
    );
    if (actressResult.loginRequired) {
      sendVideoDownloadedDone({
        session_id: sessionId,
        folder_results: folders.map((folder) => ({
          folder_name: folder.folder_name,
          folder_path: folder.folder_path || "",
          ok: false,
          error: "请先登录 JavDB",
          code_results: [],
          total_codes: (folder.codes || []).length,
          success_codes: 0,
          fail_codes: (folder.codes || []).length,
        })),
        error: "请先登录 JavDB",
        log_roots: logRoots,
      });
      return;
    }

    const actresses = actressResult.entries || [];

    for (let index = 0; index < folders.length; index++) {
      const folder = folders[index];
      const codes = Array.isArray(folder.codes) ? folder.codes : [];
      sendVideoDownloadedProgress({
        phase: "marking",
        message: `正在处理：${folder.folder_name}`,
        current: index + 1,
        total: folders.length,
      });

      const matchName = String(folder.actress_match_name || folder.folder_name || "").trim();
      const actress = collections.matchFolderInActresses(matchName, actresses);

      const codeResults = [];
      let actressMarked = false;
      let videoMap = {};
      try {
        if (actress) {
          await navigateWorkerTab(tabId, actress.profile_url, ensureVideoDownloadedWorkerHidden);

          try {
            await markVideoDownloadedActressOnTab(tabId, {
              type: "mark_video_downloaded_actress",
              actress: {
                javdb_id: actress.javdb_id,
                name: actress.name,
                folder_name: folder.folder_name,
                profile_url: actress.profile_url,
              },
            });
            actressMarked = true;
          } catch (markErr) {
            codeResults.push({
              code: "-",
              ok: false,
              error: `女优页标记失败: ${String(markErr.message || markErr)}`,
              has_subtitle: false,
              is_4k: false,
            });
          }

          videoMap = await magnetSync.fetchActressVideoMap(tabId, actress.profile_url, baseUrl, sleep);
        }

        for (const item of codes) {
          const code = String(item.code || "").trim().toUpperCase();
          if (!code) continue;
          let detailUrl;
          try {
            detailUrl = await resolveDetailUrlForCode(
              tabId,
              code,
              baseUrl,
              videoMap,
              ensureVideoDownloadedWorkerHidden
            );
          } catch (searchErr) {
            codeResults.push(
              buildVideoDownloadedCodeResult(item, {
                ok: false,
                error: String(searchErr.message || searchErr),
              })
            );
            continue;
          }

          try {
            await navigateWorkerTab(tabId, detailUrl, ensureVideoDownloadedWorkerHidden);
            await applyDownloadedStickerOnTab(tabId, code, {
              detail_url: detailUrl,
              page_url: detailUrl,
            });
            await applyVideoDownloadedMarkOnTab(tabId, {
              code,
              has_subtitle: Boolean(item.has_subtitle),
              is_4k: Boolean(item.is_4k),
              detail_url: detailUrl,
              folder_name: folder.folder_name,
            });
            codeResults.push(buildVideoDownloadedCodeResult(item, { ok: true }));
            broadcastListVisibilityRefresh();
          } catch (err) {
            codeResults.push(
              buildVideoDownloadedCodeResult(item, {
                ok: false,
                error: String(err.message || err),
              })
            );
          }
          await sleep(300);
        }

        if (actress?.profile_url) {
          await refreshActressListVisibility(tabId, actress.profile_url, ensureVideoDownloadedWorkerHidden);
        }
      } catch (err) {
        for (const item of codes) {
          const code = String(item.code || "").trim().toUpperCase();
          if (!code) continue;
          if (!codeResults.find((row) => row.code === code)) {
            codeResults.push(
              buildVideoDownloadedCodeResult(item, {
                ok: false,
                error: String(err.message || err),
              })
            );
          }
        }
      }

      const realCodeResults = codeResults.filter((row) => row.code !== "-");
      const successCodes = realCodeResults.filter((row) => row.ok).length;
      const folderResult = {
        folder_name: folder.folder_name,
        folder_path: folder.folder_path || "",
        actress: actress || null,
        ok: successCodes > 0 || actressMarked,
        error:
          successCodes > 0
            ? ""
            : actressMarked
              ? "全部番号标记失败"
              : actress
                ? "女优页与番号同步均失败"
                : "全部番号标记失败（收藏女优未匹配，已尝试番号搜索）",
        code_results: realCodeResults.length ? realCodeResults : codeResults,
        total_codes: codes.length,
        success_codes: successCodes,
        fail_codes: codes.length - successCodes,
      };
      folderResults.push(folderResult);
      sendVideoDownloadedProgress({
        phase: "export",
        message: `正在写入：${folder.folder_name}`,
        current: index + 1,
        total: folders.length,
      });
      await applySyncFolderExport(
        "video_downloaded_sync_folder_done",
        {
          session_id: sessionId,
          log_roots: logRoots,
          folder_result: folderResult,
        },
        folderResult
      );
      await sleep(400);
    }

    sendVideoDownloadedDone({
      session_id: sessionId,
      folder_results: folderResults,
      error: "",
      log_roots: logRoots,
    });
  } catch (err) {
    sendVideoDownloadedDone({
      session_id: sessionId,
      folder_results: folderResults,
      error: String(err.message || err),
      log_roots: logRoots,
    });
  } finally {
    videoDownloadedSyncRunning = false;
    await releaseVideoDownloadedWorker();
  }
}

function sendVideoCrackedProgress(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "video_cracked_sync_progress", ...payload }));
}

function sendVideoCrackedDone(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "video_cracked_sync_done", ...payload }));
}

async function releaseVideoCrackedWorker() {
  videoCrackedMarkTabId = null;
  if (videoCrackedWorkerWindowId == null) return;
  try {
    await chrome.windows.remove(videoCrackedWorkerWindowId);
  } catch (_) {
    /* ignore */
  }
  videoCrackedWorkerWindowId = null;
}

async function ensureVideoCrackedWorkerHidden() {
  if (videoCrackedWorkerWindowId == null) return;
  try {
    await chrome.windows.update(videoCrackedWorkerWindowId, {
      focused: false,
      state: "minimized",
    });
  } catch (_) {
    /* ignore */
  }
}

async function getVideoCrackedMarkTab(baseUrl) {
  if (videoCrackedMarkTabId) {
    try {
      await chrome.tabs.get(videoCrackedMarkTabId);
      await ensureVideoCrackedWorkerHidden();
      return videoCrackedMarkTabId;
    } catch (_) {
      await releaseVideoCrackedWorker();
    }
  }

  const win = await chrome.windows.create({
    url: baseUrl,
    state: "minimized",
    focused: false,
  });
  videoCrackedWorkerWindowId = win.id;
  videoCrackedMarkTabId = await resolveTabIdFromWindow(win, baseUrl);
  await ensureVideoCrackedWorkerHidden();
  return videoCrackedMarkTabId;
}

async function markVideoCrackedActressOnTab(tabId, message) {
  await injectJavdbLayout(tabId);
  let lastError = "无法注入已破解标记";
  for (let attempt = 0; attempt < 12; attempt++) {
    await sleep(attempt === 0 ? 1200 : 650);
    const ping = await invokePendingDownloadMark(tabId, { type: "ping" });
    if (!ping?.ok) {
      lastError = ping?.message || lastError;
      continue;
    }
    const result = await invokePendingDownloadMark(tabId, message);
    if (result?.ok) return result;
    lastError = result?.message || lastError;
  }
  throw new Error(lastError);
}

async function applyVideoCrackedMarkOnTab(tabId, payload) {
  await injectJavdbLayout(tabId);
  const message = { type: "mark_video_cracked", video: payload };
  let lastError = "无法在详情页标记已破解";
  for (let attempt = 0; attempt < 12; attempt++) {
    await sleep(attempt === 0 ? 1200 : 650);
    const ping = await invokeStickerAction(tabId, { type: "ping" });
    if (!ping?.ok) {
      lastError = ping?.message || lastError;
      continue;
    }
    const result = await invokeStickerAction(tabId, message);
    if (result?.ok) return result;
    lastError = result?.message || lastError;
  }
  throw new Error(lastError);
}

const CRACK_STATUS_LABELS = {
  cracked: "已破解",
  cracked_sub_pending_burn: "已破解·字幕待烧录",
  pending_extract_sub: "待提取字幕",
  pending_crack: "待破解",
};

function copyVideoCrackedFlags(item) {
  return {
    has_subtitle: Boolean(item?.has_subtitle),
    is_4k: Boolean(item?.is_4k),
    has_subtitle_file: Boolean(item?.has_subtitle_file),
    has_subtitle_name: Boolean(item?.has_subtitle_name),
    has_uncensored_file: Boolean(item?.has_uncensored_file),
    has_uncensored_sub_in_name: Boolean(item?.has_uncensored_sub_in_name),
    has_censored_ch_file: Boolean(item?.has_censored_ch_file),
    crack_status: String(item?.crack_status || "pending_crack"),
    crack_status_label: String(
      item?.crack_status_label || CRACK_STATUS_LABELS[item?.crack_status] || "待破解"
    ),
    source_file: String(item?.source_file || ""),
    uncensored_source_file: String(item?.uncensored_source_file || ""),
    censored_ch_source_file: String(item?.censored_ch_source_file || ""),
  };
}

function buildVideoCrackedCodeResult(item, extra = {}) {
  return {
    code: item.code,
    ...copyVideoCrackedFlags(item),
    ...extra,
  };
}

async function runVideoCrackedSync(request) {
  if (videoCrackedSyncRunning) {
    sendVideoCrackedDone({
      session_id: request.session_id || "",
      folder_results: [],
      error: "影片已破解同步正在进行中",
      log_roots: request.log_roots || [],
    });
    return;
  }

  const folders = Array.isArray(request.folders) ? request.folders : [];
  const logRoots = Array.isArray(request.log_roots) ? request.log_roots : [];
  const sessionId = request.session_id || "";
  const collections = globalThis.JM_pendingDownloadCollections;
  const magnetSync = globalThis.JM_magnetSavedSync;

  if (!folders.length) {
    sendVideoCrackedDone({
      session_id: sessionId,
      folder_results: [],
      error: "影片已破解目录下没有可处理的女优文件夹",
      log_roots: logRoots,
    });
    return;
  }

  videoCrackedSyncRunning = true;
  const folderResults = [];

  sendVideoCrackedProgress({
    phase: "starting",
    message: "正在准备后台同步窗口…",
    current: 0,
    total: folders.length,
  });

  try {
    const baseUrl = await getJavdbBaseUrl();
    const tabId = await getVideoCrackedMarkTab(baseUrl);

    sendVideoCrackedProgress({
      phase: "collection",
      message: "后台抓取收藏女优列表（含翻页）…",
      current: 0,
      total: folders.length,
    });

    const actressResult = await collections.fetchAllCollectionEntries(
      tabId,
      baseUrl,
      collections.ACTRESS_COLLECTION_PATH,
      "actors",
      sleep
    );
    if (actressResult.loginRequired) {
      sendVideoCrackedDone({
        session_id: sessionId,
        folder_results: folders.map((folder) => ({
          folder_name: folder.folder_name,
          folder_path: folder.folder_path || "",
          ok: false,
          error: "请先登录 JavDB",
          code_results: [],
          total_codes: (folder.codes || []).length,
          success_codes: 0,
          fail_codes: (folder.codes || []).length,
        })),
        error: "请先登录 JavDB",
        log_roots: logRoots,
      });
      return;
    }

    const actresses = actressResult.entries || [];

    for (let index = 0; index < folders.length; index++) {
      const folder = folders[index];
      const codes = Array.isArray(folder.codes) ? folder.codes : [];
      sendVideoCrackedProgress({
        phase: "marking",
        message: `正在处理：${folder.folder_name}`,
        current: index + 1,
        total: folders.length,
      });

      const matchName = String(folder.actress_match_name || folder.folder_name || "").trim();
      const actress = collections.matchFolderInActresses(matchName, actresses);

      const codeResults = [];
      let actressMarked = false;
      let videoMap = {};
      try {
        if (actress) {
          await navigateWorkerTab(tabId, actress.profile_url, ensureVideoCrackedWorkerHidden);

          try {
            await markVideoCrackedActressOnTab(tabId, {
              type: "mark_video_cracked_actress",
              actress: {
                javdb_id: actress.javdb_id,
                name: actress.name,
                folder_name: folder.folder_name,
                profile_url: actress.profile_url,
              },
            });
            actressMarked = true;
          } catch (markErr) {
            codeResults.push({
              code: "-",
              ok: false,
              error: `女优页标记失败: ${String(markErr.message || markErr)}`,
              has_subtitle: false,
              is_4k: false,
              crack_status: "pending_crack",
            });
          }

          videoMap = await magnetSync.fetchActressVideoMap(tabId, actress.profile_url, baseUrl, sleep);
        }

        for (const item of codes) {
          const code = String(item.code || "").trim().toUpperCase();
          if (!code) continue;
          let detailUrl;
          try {
            detailUrl = await resolveDetailUrlForCode(
              tabId,
              code,
              baseUrl,
              videoMap,
              ensureVideoCrackedWorkerHidden
            );
          } catch (searchErr) {
            codeResults.push(
              buildVideoCrackedCodeResult(item, {
                ok: false,
                error: String(searchErr.message || searchErr),
              })
            );
            continue;
          }

          try {
            await navigateWorkerTab(tabId, detailUrl, ensureVideoCrackedWorkerHidden);
            await applyDownloadedStickerOnTab(tabId, code, {
              detail_url: detailUrl,
              page_url: detailUrl,
            });
            await applyVideoCrackedMarkOnTab(tabId, {
              code,
              has_subtitle: Boolean(item.has_subtitle),
              is_4k: Boolean(item.is_4k),
              has_subtitle_file: Boolean(item.has_subtitle_file),
              has_uncensored_file: Boolean(item.has_uncensored_file),
              has_uncensored_sub_in_name: Boolean(item.has_uncensored_sub_in_name),
              has_censored_ch_file: Boolean(item.has_censored_ch_file),
              crack_status: String(item.crack_status || "pending_crack"),
              crack_status_label: String(item.crack_status_label || CRACK_STATUS_LABELS[item.crack_status] || ""),
              source_file: String(item.source_file || ""),
              uncensored_source_file: String(item.uncensored_source_file || ""),
              censored_ch_source_file: String(item.censored_ch_source_file || ""),
              detail_url: detailUrl,
              folder_name: folder.folder_name,
            });
            codeResults.push(buildVideoCrackedCodeResult(item, { ok: true }));
            broadcastListVisibilityRefresh();
          } catch (err) {
            codeResults.push(
              buildVideoCrackedCodeResult(item, {
                ok: false,
                error: String(err.message || err),
              })
            );
          }
          await sleep(300);
        }

        if (actress?.profile_url) {
          await refreshActressListVisibility(tabId, actress.profile_url, ensureVideoCrackedWorkerHidden);
        }
      } catch (err) {
        for (const item of codes) {
          const code = String(item.code || "").trim().toUpperCase();
          if (!code) continue;
          if (!codeResults.find((row) => row.code === code)) {
            codeResults.push(
              buildVideoCrackedCodeResult(item, {
                ok: false,
                error: String(err.message || err),
              })
            );
          }
        }
      }

      const realCodeResults = codeResults.filter((row) => row.code !== "-");
      const successCodes = realCodeResults.filter((row) => row.ok).length;
      const folderResult = {
        folder_name: folder.folder_name,
        folder_path: folder.folder_path || "",
        actress: actress || null,
        ok: successCodes > 0 || actressMarked,
        error:
          successCodes > 0
            ? ""
            : actressMarked
              ? "全部番号标记失败"
              : actress
                ? "女优页与番号同步均失败"
                : "全部番号标记失败（收藏女优未匹配，已尝试番号搜索）",
        code_results: realCodeResults.length ? realCodeResults : codeResults,
        total_codes: codes.length,
        success_codes: successCodes,
        fail_codes: codes.length - successCodes,
      };
      folderResults.push(folderResult);
      sendVideoCrackedProgress({
        phase: "export",
        message: `正在写入：${folder.folder_name}`,
        current: index + 1,
        total: folders.length,
      });
      await applySyncFolderExport(
        "video_cracked_sync_folder_done",
        {
          session_id: sessionId,
          log_roots: logRoots,
          folder_result: folderResult,
        },
        folderResult
      );
      await sleep(400);
    }

    sendVideoCrackedDone({
      session_id: sessionId,
      folder_results: folderResults,
      error: "",
      log_roots: logRoots,
    });
  } catch (err) {
    sendVideoCrackedDone({
      session_id: sessionId,
      folder_results: folderResults,
      error: String(err.message || err),
      log_roots: logRoots,
    });
  } finally {
    videoCrackedSyncRunning = false;
    await releaseVideoCrackedWorker();
  }
}

function sendVideoMetadataProgress(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "video_metadata_sync_progress", ...payload }));
}

function sendVideoMetadataDone(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "video_metadata_sync_done", ...payload }));
}

function sendSyncFolderDone(doneType, payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return Promise.resolve({ ok: false, offline: true });
  }
  if (pendingSyncFolderExport) {
    return Promise.resolve({ ok: false, message: "sync_folder_busy" });
  }
  return new Promise((resolve) => {
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      pendingSyncFolderExport = null;
      resolve(result);
    };
    pendingSyncFolderExport = {
      resolve: finish,
      reject: (err) => finish({ ok: false, message: String(err.message || err) }),
    };
    socket.send(JSON.stringify({ type: doneType, ...payload }));
    setTimeout(() => finish({ ok: false, message: "sync_folder_timeout" }), 180000);
  });
}

async function applySyncFolderExport(doneType, payload, folderResult) {
  const keepalive = setInterval(() => {
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "ping" }));
    }
  }, 12000);
  try {
    const ack = await sendSyncFolderDone(doneType, payload);
    if (ack?.folder_result) {
      Object.assign(folderResult, ack.folder_result);
    }
    if (ack?.metadata_export) {
      folderResult.metadata_export = ack.metadata_export;
    }
    return ack;
  } finally {
    clearInterval(keepalive);
  }
}

async function releaseVideoMetadataWorker() {
  videoMetadataMarkTabId = null;
  if (videoMetadataWorkerWindowId == null) return;
  try {
    await chrome.windows.remove(videoMetadataWorkerWindowId);
  } catch (_) {
    /* ignore */
  }
  videoMetadataWorkerWindowId = null;
}

async function ensureVideoMetadataWorkerHidden() {
  if (videoMetadataWorkerWindowId == null) return;
  try {
    await chrome.windows.update(videoMetadataWorkerWindowId, {
      focused: false,
      state: "minimized",
    });
  } catch (_) {
    /* ignore */
  }
}

async function getVideoMetadataMarkTab(baseUrl) {
  if (videoMetadataMarkTabId) {
    try {
      await chrome.tabs.get(videoMetadataMarkTabId);
      await ensureVideoMetadataWorkerHidden();
      return videoMetadataMarkTabId;
    } catch (_) {
      await releaseVideoMetadataWorker();
    }
  }

  const win = await chrome.windows.create({
    url: baseUrl,
    state: "minimized",
    focused: false,
  });
  videoMetadataWorkerWindowId = win.id;
  videoMetadataMarkTabId = await resolveTabIdFromWindow(win, baseUrl);
  await ensureVideoMetadataWorkerHidden();
  return videoMetadataMarkTabId;
}

async function ensureHttpTabForScripting(tabId, fallbackUrl) {
  const tab = await chrome.tabs.get(tabId);
  const url = String(tab.url || "");
  if (/^https?:\/\//i.test(url)) return url;
  const target = String(fallbackUrl || (await getJavdbBaseUrl())).trim();
  if (!/^https?:\/\//i.test(target)) {
    throw new Error(`后台标签页不在 JavDB 页面（当前: ${url || "空白"}）`);
  }
  await navigateWorkerTab(tabId, target, ensureVideoMetadataWorkerHidden);
  return target;
}

async function injectTabScripts(tabId, files, fallbackUrl) {
  if (!files.length) return;
  await ensureHttpTabForScripting(tabId, fallbackUrl);
  await chrome.scripting.executeScript({
    target: { tabId },
    files,
  });
}

async function runInTabWithScripts(tabId, files, runner, args = [], fallbackUrl = "") {
  await injectTabScripts(tabId, files, fallbackUrl);
  await ensureHttpTabForScripting(tabId, fallbackUrl);
  const maxAttempts = 4;
  for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
    try {
      const injection = await chrome.scripting.executeScript({
        target: { tabId },
        func: runner,
        args,
      });
      const frame = injection?.[0];
      if (frame?.error) {
        throw new Error(frame.error.message || String(frame.error));
      }
      return frame?.result;
    } catch (err) {
      if (isFrameRemovedError(err) && attempt < maxAttempts - 1) {
        await sleep(500 + attempt * 300);
        await waitForTabComplete(tabId, 15000).catch(() => {});
        continue;
      }
      throw err;
    }
  }
  return undefined;
}

async function resolveJavdbDetailUrlOnTab(tabId, code, baseUrl, ensureHiddenFn = async () => {}) {
  const searchUrl = `${baseUrl}/search?q=${encodeURIComponent(code)}&f=all`;
  await navigateWorkerTab(tabId, searchUrl, ensureHiddenFn);
  await sleep(1200);
  const result = await runInTabWithScripts(
    tabId,
    ["lib/metadata-sync.js"],
    (expectedCode) => {
      return globalThis.JM_metadataSync.findDetailUrlFromSearchDocument(
        document,
        expectedCode,
        location.origin
      );
    },
    [code],
    searchUrl
  );
  const url = String(result || "").trim();
  if (!url) {
    throw new Error(`JavDB 搜索未找到番号 ${code}`);
  }
  return url;
}

async function resolveDetailUrlForCode(tabId, code, baseUrl, videoMap, ensureHiddenFn = async () => {}) {
  const normalized = String(code || "").trim().toUpperCase();
  if (!normalized) {
    throw new Error("缺少番号");
  }
  const mapped = videoMap && videoMap[normalized];
  if (mapped) return mapped;
  return resolveJavdbDetailUrlOnTab(tabId, normalized, baseUrl, ensureHiddenFn);
}

async function resolveActressProfileFromSearch(tabId, folderName, baseUrl, ensureHiddenFn = async () => {}) {
  const collections = globalThis.JM_pendingDownloadCollections;
  const query = String(folderName || "").trim();
  if (!query) return null;
  const searchUrl = `${baseUrl}/search?q=${encodeURIComponent(query)}&f=all`;
  await chrome.tabs.update(tabId, { url: searchUrl, active: false });
  await waitForTabComplete(tabId);
  await ensureHiddenFn();
  await sleep(1200);
  const actress = await runInTabWithScripts(
    tabId,
    ["lib/pending-download-collections.js", "lib/name-match.js"],
    (name, origin) => {
      return globalThis.JM_pendingDownloadCollections.findActressFromSearchDocument(
        document,
        name,
        origin
      );
    },
    [query, baseUrl],
    searchUrl
  );
  return actress || null;
}

async function fetchImageBase64InWorker(imageUrl, referer) {
  const url = String(imageUrl || "").trim();
  if (!url || !/^https?:\/\//i.test(url)) return null;
  try {
    const headers = {
      Accept: "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    };
    if (referer) headers.Referer = referer;
    const resp = await fetch(url, {
      credentials: "include",
      redirect: "follow",
      referrer: referer || undefined,
      headers,
    });
    if (!resp.ok) return null;
    const buf = await resp.arrayBuffer();
    const bytes = new Uint8Array(buf);
    let binary = "";
    const chunkSize = 0x8000;
    for (let i = 0; i < bytes.length; i += chunkSize) {
      binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunkSize));
    }
    return btoa(binary);
  } catch (_) {
    return null;
  }
}

async function scrapeDetailMetadataOnTab(tabId, detailUrl) {
  const targetUrl = String(detailUrl || "").trim();
  if (!/^https?:\/\//i.test(targetUrl)) {
    throw new Error("无效的 JavDB 详情页地址");
  }
  await navigateWorkerTab(tabId, targetUrl, ensureVideoMetadataWorkerHidden);
  await sleep(1500);
  const result = await runInTabWithScripts(
    tabId,
    ["lib/metadata-sync.js"],
    async () => {
      window.scrollTo(0, document.body.scrollHeight);
      await new Promise((resolve) => setTimeout(resolve, 900));
      return globalThis.JM_metadataSync.parseDetailDocument(document, location.href, location.origin);
    },
    [],
    targetUrl
  );
  if (!result) {
    throw new Error("无法解析 JavDB 详情页元数据");
  }
  return result;
}

async function scrapeJavBusMetadataOnTab(tabId, code) {
  const urls = globalThis.JM_metadataJavbus.buildJavBusUrls(code);
  let lastError = "JavBus 页面无法访问";
  for (const pageUrl of urls) {
    try {
      await chrome.tabs.update(tabId, { url: pageUrl, active: false });
      await waitForTabComplete(tabId);
      await ensureVideoMetadataWorkerHidden();
      await sleep(2200);
      const result = await runInTabWithScripts(
        tabId,
        ["lib/metadata-javbus.js"],
        async () => {
          window.scrollTo(0, document.body.scrollHeight);
          await new Promise((resolve) => setTimeout(resolve, 1200));
          return globalThis.JM_metadataJavbus.parseJavBusDocument(document, location.href, location.origin);
        }
      );
      if (result && (result.title || result.coverUrl || (result.previewUrls && result.previewUrls.length))) {
        return result;
      }
      lastError = "JavBus 页面未解析到有效元数据（可能网络无法访问 javbus.com）";
    } catch (err) {
      lastError = String(err.message || err);
    }
  }
  throw new Error(lastError);
}

async function scrapeCombinedMetadataOnTab(tabId, code, detailUrl, baseUrl) {
  const javbusUrls = globalThis.JM_metadataJavbus.buildJavBusUrls(code);
  const javbusUrl = javbusUrls[0] || "";
  let javdbMeta = null;
  let javbusMeta = null;
  let javdbError = "";
  let resolvedDetailUrl = String(detailUrl || "").trim();

  if (!resolvedDetailUrl && baseUrl) {
    try {
      resolvedDetailUrl = await resolveJavdbDetailUrlOnTab(
        tabId,
        code,
        baseUrl,
        ensureVideoMetadataWorkerHidden
      );
    } catch (_) {
      /* optional search fallback */
    }
  }

  if (resolvedDetailUrl) {
    try {
      javdbMeta = await scrapeDetailMetadataOnTab(tabId, resolvedDetailUrl);
    } catch (err) {
      javdbError = String(err.message || err);
    }
  }

  try {
    javbusMeta = await scrapeJavBusMetadataOnTab(tabId, code);
  } catch (_) {
    /* JavBus optional fallback */
  }

  const merged = globalThis.JM_metadataSync.mergeMetadata(javdbMeta, javbusMeta, {
    code,
    detailUrl: resolvedDetailUrl || javdbMeta?.detailUrl || "",
    javbusUrl: javbusMeta?.detailUrl || javbusUrl,
  });

  if (!merged.title && !merged.coverUrl && !(merged.previewUrls && merged.previewUrls.length)) {
    throw new Error(javdbError || "JavDB 与 JavBus 均未抓取到有效元数据");
  }
  return merged;
}

function metadataAssetExtension(url) {
  const lower = String(url || "").toLowerCase();
  if (lower.includes(".png")) return ".png";
  if (lower.includes(".webp")) return ".webp";
  if (lower.includes(".gif")) return ".gif";
  return ".jpg";
}

function sanitizeMetadataPathPart(text) {
  return String(text || "")
    .replace(/[<>:"/\\|?*\x00-\x1f]/g, "_")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 180) || "_";
}

function writeMetadataAssetToDesktop(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return Promise.resolve({ ok: false, offline: true });
  }
  if (pendingMetadataAsset) {
    return Promise.resolve({ ok: false, message: "metadata_asset_busy" });
  }
  return new Promise((resolve) => {
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      pendingMetadataAsset = null;
      resolve(result);
    };
    pendingMetadataAsset = {
      resolve: finish,
      reject: (err) => finish({ ok: false, message: String(err.message || err) }),
    };
    socket.send(JSON.stringify({ type: "metadata_asset_write", ...payload }));
    setTimeout(() => finish({ ok: false, message: "metadata_asset_timeout" }), 45000);
  });
}

async function downloadImageBase64OnTab(tabId, imageUrl, referer) {
  let result = await fetchImageBase64InWorker(imageUrl, referer);
  if (result) return result;

  const refPage = String(referer || imageUrl || "").trim();
  if (refPage && /^https?:\/\//i.test(refPage)) {
    try {
      await chrome.tabs.update(tabId, { url: refPage, active: false });
      await waitForTabComplete(tabId);
      await sleep(700);
    } catch (_) {
      /* ignore navigation errors */
    }
  }

  try {
    const pageResult = await runInTabWithScripts(
      tabId,
      ["lib/metadata-sync.js"],
      async (url, ref) => globalThis.JM_metadataSync.fetchImageBase64(url, ref),
      [imageUrl, referer]
    );
    return pageResult || null;
  } catch (_) {
    return null;
  }
}

async function saveMetadataImageAsset(tabId, folderPath, relativePath, imageUrl, referer) {
  if (!imageUrl) return false;
  try {
    const contentBase64 = await downloadImageBase64OnTab(tabId, imageUrl, referer);
    if (!contentBase64) return false;
    const result = await writeMetadataAssetToDesktop({
      folder_path: folderPath,
      relative_path: relativePath,
      content_base64: contentBase64,
    });
    return Boolean(result?.ok);
  } catch (_) {
    return false;
  }
}

async function saveMetadataAssetsForCode(tabId, folder, item, meta, actressName, detailUrl) {
  const folderPath = String(folder.folder_path || "");
  if (!folderPath || !meta) {
    return { cover_saved: 0, preview_saved: 0 };
  }

  const code = String(item.code || meta.code || "").trim().toUpperCase();
  const actress = String(meta.actresses || actressName || "").split("、")[0].trim() || actressName;
  const title = String(meta.title || code);
  const subfolder = sanitizeMetadataPathPart(`${code} ${actress}`);
  const coverFile = sanitizeMetadataPathPart(`${code} ${actress} ${title}`);
  const javdbUrl = String(detailUrl || meta.detailUrl || "");
  const javbusUrl = String(meta.javbusUrl || "");

  let coverSaved = 0;
  let previewSaved = 0;

  if (meta.coverUrl) {
    const coverRel = `封面/${subfolder}/${coverFile}${metadataAssetExtension(meta.coverUrl)}`;
    const referer = globalThis.JM_metadataSync.imageReferer(meta.coverUrl, javdbUrl, javbusUrl);
    if (await saveMetadataImageAsset(tabId, folderPath, coverRel, meta.coverUrl, referer)) {
      coverSaved = 1;
    }
  }

  const previewUrls = Array.isArray(meta.previewUrls) ? meta.previewUrls : [];
  for (let index = 0; index < previewUrls.length; index++) {
    const previewUrl = previewUrls[index];
    const previewRel = `封面预览图/${subfolder}/${String(index + 1).padStart(2, "0")}${metadataAssetExtension(previewUrl)}`;
    const referer = globalThis.JM_metadataSync.imageReferer(previewUrl, javdbUrl, javbusUrl);
    if (await saveMetadataImageAsset(tabId, folderPath, previewRel, previewUrl, referer)) {
      previewSaved += 1;
    }
    await sleep(150);
  }

  try {
    const longThumb = await globalThis.JM_detailTools.getLongThumbnail(code);
    if (longThumb) {
      const longUrl =
        typeof longThumb === "string" ? longThumb : longThumb.full || longThumb.thumb || "";
      if (longUrl) {
        const longRel = `封面/${subfolder}/long${metadataAssetExtension(longUrl)}`;
        const referer = globalThis.JM_metadataSync.imageReferer(longUrl, javdbUrl, javbusUrl);
        if (await saveMetadataImageAsset(tabId, folderPath, longRel, longUrl, referer)) {
          coverSaved += 1;
        }
      }
    }
  } catch (_) {
    /* non-fatal */
  }

  return { cover_saved: coverSaved, preview_saved: previewSaved };
}

function copyLocalMediaFlags(item, libraryKind) {
  const base = {
    code: item.code,
    source_file: item.source_file || "",
    source_path: item.source_path || "",
    has_subtitle: Boolean(item?.has_subtitle),
    is_4k: Boolean(item?.is_4k),
    has_subtitle_file: Boolean(item?.has_subtitle_file),
    has_subtitle_name: Boolean(item?.has_subtitle_name),
  };
  if (libraryKind === "video_cracked") {
    return {
      ...base,
      crack_status: String(item?.crack_status || "pending_crack"),
      crack_status_label: String(item?.crack_status_label || ""),
      has_uncensored_file: Boolean(item?.has_uncensored_file),
      has_uncensored_sub_in_name: Boolean(item?.has_uncensored_sub_in_name),
      has_censored_ch_file: Boolean(item?.has_censored_ch_file),
    };
  }
  return base;
}

function buildMetadataCodeResult(item, meta, extra = {}) {
  return {
    code: item.code,
    title: meta?.title || "",
    release_date: meta?.releaseDate || "",
    duration: meta?.duration || "",
    director: meta?.director || "",
    studio: meta?.studio || "",
    series: meta?.series || "",
    categories: meta?.categories || "",
    actresses: meta?.actresses || "",
    rating: meta?.rating || "",
    cover_url: meta?.coverUrl || "",
    javbus_url: meta?.javbusUrl || "",
    metadata_source: meta?.source || "",
    preview_urls: Array.isArray(meta?.previewUrls) ? meta.previewUrls : [],
    preview_count: Array.isArray(meta?.previewUrls) ? meta.previewUrls.length : 0,
    detail_url: meta?.detailUrl || extra.detail_url || "",
    ...copyLocalMediaFlags(item, extra.library_kind || ""),
    ...extra,
  };
}

async function runVideoMetadataSync(request) {
  if (videoMetadataSyncRunning) {
    sendVideoMetadataDone({
      session_id: request.session_id || "",
      library_kind: request.library_kind || "",
      folder_results: [],
      error: "元数据同步正在进行中",
    });
    return;
  }

  const folders = Array.isArray(request.folders) ? request.folders : [];
  const sessionId = request.session_id || "";
  const libraryKind = String(request.library_kind || "video_downloaded");
  const collections = globalThis.JM_pendingDownloadCollections;
  const magnetSync = globalThis.JM_magnetSavedSync;

  if (!folders.length) {
    sendVideoMetadataDone({
      session_id: sessionId,
      library_kind: libraryKind,
      folder_results: [],
      error: "目录下没有可处理的女优文件夹",
    });
    return;
  }

  videoMetadataSyncRunning = true;
  const folderResults = [];

  sendVideoMetadataProgress({
    phase: "starting",
    message: "正在准备后台元数据同步窗口…",
    current: 0,
    total: folders.length,
    library_kind: libraryKind,
  });

  try {
    const baseUrl = await getJavdbBaseUrl();
    const tabId = await getVideoMetadataMarkTab(baseUrl);

    sendVideoMetadataProgress({
      phase: "collection",
      message: "后台抓取收藏女优列表（含翻页）…",
      current: 0,
      total: folders.length,
      library_kind: libraryKind,
    });

    const actressResult = await collections.fetchAllCollectionEntries(
      tabId,
      baseUrl,
      collections.ACTRESS_COLLECTION_PATH,
      "actors",
      sleep
    );
    if (actressResult.loginRequired) {
      sendVideoMetadataProgress({
        phase: "metadata",
        message: "JavDB 未登录，将仅使用 JavBus 抓取元数据…",
        current: 0,
        total: folders.length,
        library_kind: libraryKind,
      });
    }

    const actresses = actressResult.loginRequired ? [] : actressResult.entries || [];

    async function processCodeItem(item, context) {
      const code = String(item.code || "").trim().toUpperCase();
      if (!code) return null;
      const detailUrl = context.videoMap[code] || "";
      const actressName = String(context.actressName || "");

      try {
        await ensureVideoMetadataWorkerHidden();
        const meta = await scrapeCombinedMetadataOnTab(tabId, code, detailUrl, baseUrl);
        const notes = [];
        if (!meta.coverUrl) notes.push("未抓取到封面地址");
        return buildMetadataCodeResult(item, meta, {
          ok: true,
          detail_url: detailUrl || meta.detailUrl || meta.javbusUrl || "",
          javbus_url: meta.javbusUrl || "",
          library_kind: libraryKind,
          cover_saved: 0,
          preview_saved: 0,
          preview_count: Array.isArray(meta.previewUrls) ? meta.previewUrls.length : 0,
          metadata_source: meta.source || "",
          error: notes.join("；"),
        });
      } catch (err) {
        return buildMetadataCodeResult(item, null, {
          ok: false,
          error: String(err.message || err),
          detail_url: detailUrl,
          library_kind: libraryKind,
        });
      }
    }

    for (let index = 0; index < folders.length; index++) {
      const folder = folders[index];
      const codes = Array.isArray(folder.codes) ? folder.codes : [];
      sendVideoMetadataProgress({
        phase: "metadata",
        message: `正在抓取元数据：${folder.folder_name}`,
        current: index + 1,
        total: folders.length,
        library_kind: libraryKind,
      });

      const matchName = String(folder.actress_match_name || folder.folder_name || "").trim();
      const actress = actresses.length ? collections.matchFolderInActresses(matchName, actresses) : null;
      const codeResults = [];
      let videoMap = {};
      if (actress?.profile_url) {
        try {
          await navigateWorkerTab(tabId, actress.profile_url, ensureVideoMetadataWorkerHidden);
          videoMap = await magnetSync.fetchActressVideoMap(tabId, actress.profile_url, baseUrl, sleep);
        } catch (_) {
          videoMap = {};
        }
      }
      const actressName = String(actress?.name || matchName || "");

      for (let codeIndex = 0; codeIndex < codes.length; codeIndex += 1) {
        const item = codes[codeIndex];
        sendVideoMetadataProgress({
          phase: "metadata",
          message: `正在抓取元数据：${folder.folder_name}（${codeIndex + 1}/${codes.length}）`,
          current: index + 1,
          total: folders.length,
          library_kind: libraryKind,
        });
        const result = await processCodeItem(item, { videoMap, actressName });
        if (result) codeResults.push(result);
        await sleep(400);
      }

      const successCodes = codeResults.filter((row) => row.ok).length;
      const folderResult = {
        folder_name: folder.folder_name,
        folder_path: folder.folder_path || "",
        actress: actress || null,
        actress_match_name: matchName,
        ok: successCodes > 0,
        error: successCodes > 0 ? "" : "全部番号元数据抓取失败（女优主页未找到时已尝试番号搜索）",
        code_results: codeResults,
        total_codes: codes.length,
        success_codes: successCodes,
        fail_codes: codes.length - successCodes,
      };
      folderResults.push(folderResult);

      sendVideoMetadataProgress({
        phase: "export",
        message: `正在写入文件：${folder.folder_name}`,
        current: index + 1,
        total: folders.length,
        library_kind: libraryKind,
      });
      const exportAck = await applySyncFolderExport(
        "video_metadata_folder_done",
        {
          session_id: sessionId,
          library_kind: libraryKind,
          current: index + 1,
          total: folders.length,
          folder_result: folderResult,
        },
        folderResult
      );
      if (exportAck?.ok === false && exportAck?.message) {
        folderResult.export_error = String(exportAck.message);
      }
      await sleep(300);
    }

    sendVideoMetadataDone({
      session_id: sessionId,
      library_kind: libraryKind,
      folder_results: folderResults,
      error: "",
    });
  } catch (err) {
    sendVideoMetadataDone({
      session_id: sessionId,
      library_kind: libraryKind,
      folder_results: folderResults,
      error: String(err.message || err),
    });
  } finally {
    videoMetadataSyncRunning = false;
    await releaseVideoMetadataWorker();
  }
}

function sendLooseVideoProgress(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "loose_video_sync_progress", ...payload }));
}

function sendLooseVideoDone(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ type: "loose_video_sync_done", ...payload }));
}

function copyLooseFlags(item) {
  return {
    filename_actress: String(item?.filename_actress || ""),
    has_uncensored: Boolean(item?.has_uncensored),
    has_subtitle: Boolean(item?.has_subtitle),
    has_subtitle_file: Boolean(item?.has_subtitle_file),
    has_subtitle_name: Boolean(item?.has_subtitle_name),
    has_uncensored_sub_in_name: Boolean(item?.has_uncensored_sub_in_name),
    has_censored_ch_file: Boolean(item?.has_censored_ch_file),
    subtitle_kind: String(item?.subtitle_kind || ""),
    is_4k: Boolean(item?.is_4k),
    crack_status: String(item?.crack_status || "pending_crack"),
    source_file: String(item?.source_file || ""),
    source_path: String(item?.source_path || ""),
  };
}

function isPlaceholderActressName(name) {
  const text = String(name || "").trim();
  if (!text) return true;
  const compact = text.replace(/[\s_\-./\\]+/g, "").toUpperCase();
  if (["NA", "N/A", "N-A", "UNKNOWN", "NONE", "NULL", "未知", "无", "-", "—"].includes(compact)) {
    return true;
  }
  return /^N[\s\-/]*A$/i.test(text);
}

function resolveLooseActressName(filenameActress, javdbActress) {
  const fromFile = String(filenameActress || "").trim();
  const fromJavdb = String(javdbActress || "").split("、")[0].trim();
  if (fromFile && !isPlaceholderActressName(fromFile)) return fromFile;
  if (fromJavdb && !isPlaceholderActressName(fromJavdb)) return fromJavdb;
  if (fromFile) return fromFile;
  if (fromJavdb) return fromJavdb;
  return "";
}

function buildLooseItemResult(item, extra = {}) {
  return {
    code: item.code,
    ...copyLooseFlags(item),
    ...extra,
  };
}

async function processLooseVideoItem(tabId, item, baseUrl) {
  const code = String(item.code || "").trim().toUpperCase();
  if (!code) {
    return buildLooseItemResult(item, { ok: false, error: "缺少番号" });
  }

  let detailUrl = "";
  try {
    detailUrl = await resolveDetailUrlForCode(
      tabId,
      code,
      baseUrl,
      {},
      ensureVideoDownloadedWorkerHidden
    );
  } catch (err) {
    return buildLooseItemResult(item, { ok: false, error: String(err.message || err) });
  }

  try {
    await ensureVideoDownloadedWorkerHidden();
    await chrome.tabs.update(tabId, { url: detailUrl, active: false });
    await waitForTabComplete(tabId);
    await applyDownloadedStickerOnTab(tabId, code, {
      detail_url: detailUrl,
      page_url: detailUrl,
    });
    await applyVideoDownloadedMarkOnTab(tabId, {
      code,
      has_subtitle: Boolean(item.has_subtitle),
      is_4k: Boolean(item.is_4k),
      detail_url: detailUrl,
      folder_name: "散片",
    });
    if (item.has_uncensored) {
      await applyVideoCrackedMarkOnTab(tabId, {
        code,
        has_subtitle: Boolean(item.has_subtitle),
        is_4k: Boolean(item.is_4k),
        has_subtitle_file: Boolean(item.has_subtitle_file),
        has_uncensored_file: true,
        crack_status: String(item.crack_status || "cracked"),
        crack_status_label: String(
          item.crack_status_label || CRACK_STATUS_LABELS[item.crack_status] || "已破解"
        ),
        detail_url: detailUrl,
        folder_name: "散片",
        source_file: String(item.source_file || ""),
      });
    }

    const meta = await scrapeDetailMetadataOnTab(tabId, detailUrl);
    const javdbActress = String(meta?.actresses || "").split("、")[0].trim();
    const actress = resolveLooseActressName(item.filename_actress, meta?.actresses);
    return buildLooseItemResult(item, {
      ok: true,
      title: meta?.title || "",
      actress,
      actresses: meta?.actresses || "",
      javdb_actress: javdbActress,
      filename_actress: String(item.filename_actress || "").trim(),
      detail_url: detailUrl,
    });
  } catch (err) {
    return buildLooseItemResult(item, { ok: false, error: String(err.message || err), detail_url: detailUrl });
  }
}

async function runLooseVideoSync(request) {
  if (looseVideoSyncRunning) {
    sendLooseVideoDone({
      session_id: request.session_id || "",
      root_results: [],
      error: "散片处理任务正在进行中",
    });
    return;
  }

  const roots = Array.isArray(request.roots) ? request.roots : [];
  const sessionId = request.session_id || "";
  if (!roots.length) {
    sendLooseVideoDone({
      session_id: sessionId,
      root_results: [],
      error: "散片目录下没有可处理的影片",
    });
    return;
  }

  looseVideoSyncRunning = true;
  const rootResults = [];

  try {
    const baseUrl = await getJavdbBaseUrl();
    const tabId = await getVideoDownloadedMarkTab(baseUrl);

    for (let index = 0; index < roots.length; index += 1) {
      const root = roots[index];
      const items = Array.isArray(root.items) ? root.items : [];
      sendLooseVideoProgress({
        phase: "marking",
        message: `正在处理散片目录：${root.root_name || root.root_path || ""}`,
        current: index + 1,
        total: roots.length,
      });

      const itemResults = [];
      for (let itemIndex = 0; itemIndex < items.length; itemIndex += 1) {
        const item = items[itemIndex];
        sendLooseVideoProgress({
          phase: "marking",
          message: `正在处理 ${item.code || ""}（${itemIndex + 1}/${items.length}）`,
          current: index + 1,
          total: roots.length,
        });
        const result = await processLooseVideoItem(tabId, item, baseUrl);
        itemResults.push(result);
        await sleep(400);
      }

      const successItems = itemResults.filter((row) => row.ok).length;
      const rootResult = {
        root_path: root.root_path || "",
        root_name: root.root_name || "",
        folder_path: root.root_path || "",
        ok: successItems > 0,
        error: successItems > 0 ? "" : "全部散片处理失败",
        item_results: itemResults,
        total_items: items.length,
        success_items: successItems,
        fail_items: items.length - successItems,
      };
      rootResults.push(rootResult);

      sendLooseVideoProgress({
        phase: "export",
        message: `正在写入与整理：${root.root_name || ""}`,
        current: index + 1,
        total: roots.length,
      });
      await applySyncFolderExport(
        "loose_video_sync_folder_done",
        {
          session_id: sessionId,
          current: index + 1,
          total: roots.length,
          root_result: rootResult,
        },
        rootResult
      );
      await sleep(300);
    }

    sendLooseVideoDone({
      session_id: sessionId,
      root_results: rootResults,
      error: "",
    });
  } catch (err) {
    sendLooseVideoDone({
      session_id: sessionId,
      root_results: rootResults,
      error: String(err.message || err),
    });
  } finally {
    looseVideoSyncRunning = false;
    await releaseVideoDownloadedWorker();
  }
}

function writeMagnetTxtToDesktop(message) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return Promise.resolve({ ok: false, offline: true });
  }

  if (pendingMagnetTxt) {
    return Promise.resolve({ ok: false, message: "magnet_txt_busy" });
  }

  return new Promise((resolve) => {
    let settled = false;
    const finish = (payload) => {
      if (settled) return;
      settled = true;
      pendingMagnetTxt = null;
      resolve(payload);
    };

    pendingMagnetTxt = {
      resolve: (msg) => finish(msg),
      reject: (err) => finish({ ok: false, message: String(err.message || err) }),
    };

    socket.send(
      JSON.stringify({
        type: "magnet_txt_write",
        filename: message.filename,
        content: message.content,
        code: message.code || "",
        allow_empty: Boolean(message.allowEmpty),
      })
    );

    setTimeout(() => finish({ ok: false, message: "桌面保存超时" }), 15000);
  });
}

function writeMagnetTxtBatchToDesktop(payload) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return Promise.resolve({ ok: false, offline: true });
  }
  if (pendingMagnetTxtBatch) {
    return Promise.resolve({ ok: false, message: "magnet_txt_batch_busy" });
  }

  return new Promise((resolve) => {
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      pendingMagnetTxtBatch = null;
      resolve(result);
    };

    pendingMagnetTxtBatch = {
      resolve: (msg) => finish(msg),
      reject: (err) => finish({ ok: false, message: String(err.message || err) }),
    };

    socket.send(
      JSON.stringify({
        type: "magnet_txt_batch_write",
        actress_name: payload.actressName || "",
        files: payload.files || {},
        processed_codes: payload.processedCodes || [],
      })
    );

    setTimeout(() => finish({ ok: false, message: "桌面批量保存超时" }), 30000);
  });
}

function lookupActressFolderCacheKey(actressName, javdbId = "") {
  return `${String(actressName || "").trim()}\0${String(javdbId || "").trim()}`;
}

function lookupActressFolderFromDesktop(actressName, javdbId = "") {
  const cacheKey = lookupActressFolderCacheKey(actressName, javdbId);
  if (actressFolderLookupCache.has(cacheKey)) {
    return Promise.resolve(actressFolderLookupCache.get(cacheKey));
  }

  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return Promise.resolve({ ok: false, offline: true });
  }

  for (const pending of pendingActressFolderLookups.values()) {
    if (pending.cacheKey === cacheKey) {
      return pending.promise;
    }
  }

  const serial = ++wsRequestSerial;
  let resolveOuter;
  const promise = new Promise((resolve) => {
    resolveOuter = resolve;
  });

  let settled = false;
  const finish = (result) => {
    if (settled) return;
    settled = true;
    pendingActressFolderLookups.delete(serial);
    if (result?.ok && result?.found && result?.folder_path) {
      actressFolderLookupCache.set(cacheKey, result);
    }
    resolveOuter(result);
  };

  pendingActressFolderLookups.set(serial, { cacheKey, promise, resolve: finish });

  socket.send(
    JSON.stringify({
      type: "actress_folder_lookup",
      actress_name: actressName || "",
      javdb_id: String(javdbId || "").trim(),
      serial,
    })
  );

  setTimeout(() => finish({ ok: false, message: "查询女优文件夹超时" }), 12000);

  return promise;
}

function readMagnetSummaryFromDesktop(actressName, pendingDownload = false) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    return Promise.resolve({ ok: false, offline: true });
  }

  const serial = ++magnetSummarySerial;
  return new Promise((resolve) => {
    let settled = false;
    const finish = (result) => {
      if (settled) return;
      settled = true;
      pendingMagnetSummaries.delete(serial);
      resolve(result);
    };

    pendingMagnetSummaries.set(serial, { resolve: finish });

    socket.send(
      JSON.stringify({
        type: "magnet_summary_read",
        actress_name: actressName || "",
        pending_download: Boolean(pendingDownload),
        serial,
      })
    );

    setTimeout(() => finish({ ok: false, message: "读取总结.txt 超时" }), 12000);
  });
}

async function markDownloadedAfterBatchMatch(record) {
  const core = globalThis.JM_magnetTxtCore;
  const code = core?.normalizeCode ? core.normalizeCode(record.code) : String(record.code || "").toUpperCase();
  if (!code) return;

  const stored = await chrome.storage.local.get("javdbStickerData");
  const data = stored.javdbStickerData || {};
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const recordedAt = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;

  const hideRecord = {
    code,
    title: String(record.title || ""),
    detail_url: String(record.detail_url || ""),
    page_url: String(record.detail_url || ""),
    recorded_at: recordedAt,
  };

  if (!data.downloaded) data.downloaded = {};
  if (!data.marked) data.marked = {};
  if (!data.videoDownloadedVideos) data.videoDownloadedVideos = {};

  data.downloaded[code] = hideRecord;
  for (const markedKey of Object.keys(data.marked || {})) {
    if ((core?.normalizeCode ? core.normalizeCode(markedKey) : markedKey.toUpperCase()) === code) {
      delete data.marked[markedKey];
    }
  }
  data.videoDownloadedVideos[code] = {
    code,
    title: hideRecord.title,
    has_subtitle: Boolean(record.has_subtitle),
    is_4k: Boolean(record.is_4k),
    detail_url: hideRecord.detail_url,
    folder_name: String(record.folder_name || ""),
    recorded_at: recordedAt,
  };

  await chrome.storage.local.set({ javdbStickerData: data });

  try {
    await sendStickerActionToDesktop({ action: "downloaded", ...hideRecord });
  } catch (_) {
    /* ignore */
  }
  try {
    await sendStickerActionToDesktop({
      action: "video_downloaded_video",
      code,
      title: hideRecord.title,
      has_subtitle: Boolean(record.has_subtitle),
      is_4k: Boolean(record.is_4k),
      detail_url: hideRecord.detail_url,
      folder_name: String(record.folder_name || ""),
      recorded_at: recordedAt,
    });
  } catch (_) {
    /* ignore */
  }

  broadcastStickerSync(data);
  chrome.tabs.query({ url: ["https://javdb.com/*", "https://*.javdb.com/*"] }, (tabs) => {
    for (const tab of tabs) {
      chrome.tabs.sendMessage(tab.id, { type: "refresh_list_visibility" }).catch(() => {});
    }
  });
}

async function transitionActressPendingToMagnetSaved({ actressName, actressJavdbId, profileUrl }) {
  const javdbId = String(actressJavdbId || "").trim();
  if (!javdbId) return;

  const stored = await chrome.storage.local.get("javdbStickerData");
  const data = stored.javdbStickerData || {};
  if (!data.pendingDownloadActresses) data.pendingDownloadActresses = {};
  if (!data.magnetSavedActresses) data.magnetSavedActresses = {};

  delete data.pendingDownloadActresses[javdbId];

  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const recordedAt = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;

  const record = {
    javdb_id: javdbId,
    name: String(actressName || ""),
    folder_name: String(actressName || ""),
    profile_url: String(profileUrl || ""),
    storage_type: "local_magnet",
    recorded_at: recordedAt,
  };
  data.magnetSavedActresses[javdbId] = record;

  await chrome.storage.local.set({ javdbStickerData: data });

  try {
    await sendStickerActionToDesktop({ action: "magnet_saved_actress", ...record });
  } catch (_) {
    /* ignore */
  }

  broadcastStickerSync(data);
}

async function runBatchGenerateMagnetTxtJob(payload) {
  const core = globalThis.JM_magnetTxtCore;
  const magnetSync = globalThis.JM_magnetSavedSync;
  if (!core || !magnetSync) {
    showMagnetTxtNotification(false, "磁链后台模块未加载，请重新加载扩展。", "");
    return { ok: false };
  }
  if (batchGenerateMagnetTxtRunning) {
    showMagnetTxtNotification(false, "批量生成任务正在进行中。", "");
    return { ok: false, busy: true };
  }

  const actressName = String(payload?.actressName || "").trim();
  const profileUrl = String(payload?.profileUrl || "").trim();
  const tabId = payload?.tabId;
  if (!actressName || !profileUrl || !tabId) {
    showMagnetTxtNotification(false, "缺少女优页信息，请在女优作品页重试。", "");
    return { ok: false };
  }

  batchGenerateMagnetTxtRunning = true;
  broadcastMagnetTxtStatus({
    status: "running",
    code: "",
    message: `${actressName}：正在收集已标记番号…`,
  });

  try {
    const stored = await chrome.storage.local.get("javdbStickerData");
    const marked = stored.javdbStickerData?.marked || {};
    const markedCodes = Object.keys(marked);
    if (!markedCodes.length) {
      throw new Error("当前没有已标记待下载的番号。");
    }

    const tab = await chrome.tabs.get(tabId).catch(() => null);
    const baseUrl = tab?.url ? new URL(tab.url).origin : "https://javdb.com";
    const videoMap = await magnetSync.fetchActressVideoMap(tabId, profileUrl, baseUrl, sleep);

    const items = [];
    for (const rawCode of markedCodes) {
      const normalized = core.normalizeCode(rawCode);
      const detailUrl = videoMap[normalized];
      if (!detailUrl) continue;
      items.push({
        code: normalized,
        detailUrl,
        title: String(marked[rawCode]?.title || ""),
      });
    }

    if (!items.length) {
      throw new Error("该女优作品页上没有已标记的番号。");
    }

    const rules = await core.loadFilterRules(fetchMagnetFilterRulesFromDesktopAsync);
    const crackMagnets = new Set();
    const pendingMagnets = new Set();
    const summary = { fourK: [], subtitle: [], hd: [], none: [] };

    for (let index = 0; index < items.length; index += 1) {
      const item = items[index];
      broadcastMagnetTxtStatus({
        status: "running",
        code: item.code,
        message: `${actressName}：批量筛查 ${index + 1}/${items.length} · ${item.code}`,
      });

      const result = await core.screenMagnetAllStages({
        code: item.code,
        detailUrl: item.detailUrl,
        javdbMagnets: null,
        actressHint: actressName,
        rulesConfig: rules,
      });

      if (result.fourK?.ok) {
        if (result.fourK.magnet?.startsWith("magnet:?")) crackMagnets.add(result.fourK.magnet);
        summary.fourK.push(item.code);
      }
      if (result.subtitle?.ok) {
        if (result.subtitle.magnet?.startsWith("magnet:?")) crackMagnets.add(result.subtitle.magnet);
        summary.subtitle.push(item.code);
      }
      if (result.hd?.ok && !result.subtitle?.ok) {
        if (result.hd.magnet?.startsWith("magnet:?")) pendingMagnets.add(result.hd.magnet);
        summary.hd.push(item.code);
      }
      if (!result.fourK?.ok && !result.subtitle?.ok && !result.hd?.ok) {
        summary.none.push(item.code);
      }

      const anyMatch = result.fourK?.ok || result.subtitle?.ok || result.hd?.ok;
      if (anyMatch) {
        await markDownloadedAfterBatchMatch({
          code: item.code,
          title: item.title,
          detail_url: item.detailUrl,
          has_subtitle: Boolean(result.subtitle?.ok),
          is_4k: Boolean(result.fourK?.ok),
          folder_name: actressName,
        });
      }

      await sleep(400);
    }

    const files = {
      "破解.txt": Array.from(crackMagnets).join("\n"),
      "待匹配字幕.txt": Array.from(pendingMagnets).join("\n"),
      "总结.txt": core.buildBatchSummaryText(summary),
    };

    const desktop = await writeMagnetTxtBatchToDesktop({
      actressName,
      files,
      processedCodes: items.map((item) => item.code),
    });
    if (!desktop.ok) {
      const hint = desktop.offline
        ? `桌面未连接，无法写入女优文件夹。请启动 ${APP_DISPLAY_NAME} 并保持扩展已配对。`
        : desktop.message || "批量保存失败";
      throw new Error(hint);
    }

    const msg = `已保存到 ${desktop.folder_path || actressName}：破解.txt（${crackMagnets.size} 条）· 待匹配字幕.txt（${pendingMagnets.size} 条）· 总结.txt`;
    showMagnetTxtNotification(true, msg, actressName);
    broadcastMagnetTxtStatus({ status: "done", code: "", message: msg });
    await transitionActressPendingToMagnetSaved({
      actressName,
      actressJavdbId: payload?.actressJavdbId,
      profileUrl,
    });
    return { ok: true, folder_path: desktop.folder_path, summary };
  } catch (err) {
    const message = String(err.message || err);
    showMagnetTxtNotification(false, message, actressName);
    broadcastMagnetTxtStatus({ status: "error", code: "", message });
    return { ok: false, message };
  } finally {
    batchGenerateMagnetTxtRunning = false;
  }
}

function sendStickerActionToDesktop(payload) {
  return new Promise((resolve, reject) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      resolve({ ok: false, offline: true });
      return;
    }

    const serial = ++stickerActionSerial;
    const timer = setTimeout(() => {
      pendingStickerActions.delete(serial);
      reject(new Error("桌面保存超时"));
    }, 12000);

    pendingStickerActions.set(serial, { resolve, reject, timer });
    socket.send(JSON.stringify({ type: "sticker_action", ...payload, _serial: serial }));
  });
}

async function runNewWorksCheck() {
  newWorksCheckCancelled = false;
  const stored = await chrome.storage.local.get(["javdbStickerData"]);
  const data = stored.javdbStickerData || {};
  const collectedMap = data.collectedActresses || {};
  const actressList = Object.values(collectedMap);
  if (!actressList.length) {
    return { ok: false, message: "请先同步收藏女优到扩展" };
  }

  const marked = new Set();
  for (const key of ["blocked", "verified", "downloaded", "marked"]) {
    const bucket = data[key] || {};
    for (const code of Object.keys(bucket)) {
      marked.add(String(code).toUpperCase());
    }
  }

  const results = [];
  for (const actress of actressList) {
    if (newWorksCheckCancelled) {
      return {
        ok: false,
        cancelled: true,
        message: "检测已取消",
        results,
        total_actresses: actressList.length,
      };
    }
    const javdbId = String(
      actress.javdb_id ||
        actress.id ||
        actress.starId ||
        (String(actress.profile_url || "").match(/\/(actors|stars)\/([^/?#]+)/i)?.[2] || "")
    ).trim();
    const name = String(actress.name || "").trim();
    if (!javdbId) {
      results.push({ name, javdb_id: "", codes: [], error: "无法识别女优ID" });
      continue;
    }
    try {
      const codes = await globalThis.JM_detailTools.fetchActressPageCodes(javdbId);
      const pending = codes.filter((code) => !marked.has(String(code).toUpperCase()));
      if (pending.length) {
        results.push({ name, javdb_id: javdbId, codes: pending });
      }
    } catch (err) {
      results.push({ name, javdb_id: javdbId, codes: [], error: String(err.message || err) });
    }
    await sleep(600);
  }
  return { ok: true, results, total_actresses: actressList.length };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === "reset_bridge_connection") {
    settings.token = "";
    void chrome.storage.local.remove("bridgeToken").finally(() => {
      void loadSettings().then(() => connect());
    });
    sendResponse({ ok: true });
    return false;
  }

  if (message.type === "batch_generate_magnet_txt_start") {
    if (!sender.tab?.id) {
      sendResponse({ ok: false, message: "missing_tab" });
      return false;
    }
    sendResponse({ ok: true, started: true });
    scheduleBatchGenerateMagnetTxtJob({
      actressName: message.actressName,
      actressJavdbId: message.actressJavdbId,
      profileUrl: message.profileUrl,
      tabId: sender.tab.id,
    });
    return false;
  }

  if (message.type === "sync_actresses") {
    runActressSync({ force: Boolean(message.force), reason: "manual_button" }).then(sendResponse);
    return true;
  }

  if (message.type === "get_actress_sync_status") {
    chrome.storage.local
      .get(["actressSyncLastDate", "actressSyncLastCount", "actressSyncLastAt"])
      .then((stored) => {
        sendResponse({
          ok: true,
          lastDate: stored.actressSyncLastDate || "",
          count: stored.actressSyncLastCount || 0,
          syncedAt: stored.actressSyncLastAt || "",
          running: actressSyncRunning,
        });
      });
    return true;
  }

  if (message.type === "sticker_action") {
    const payload = { ...message };
    delete payload.type;
    sendStickerActionToDesktop(payload)
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "generate_magnet_txt_start") {
    const code = String(message.code || "").trim();
    if (!code) {
      sendResponse({ ok: false, message: "missing_code" });
      return false;
    }
    runGenerateMagnetTxtJob({
      code,
      detailUrl: message.detailUrl,
      javdbMagnets: message.javdbMagnets,
      actress: message.actress,
      title: message.title,
    });
    sendResponse({ ok: true, started: true });
    return false;
  }

  if (message.type === "fetch_actress_page_items") {
    const magnetSync = globalThis.JM_magnetSavedSync;
    const profileUrl = String(message.profileUrl || "").trim();
    const tabId = sender.tab?.id;
    if (!magnetSync?.fetchActressPageItems || !profileUrl || !tabId) {
      sendResponse({ ok: false, message: "missing_tab_or_profile" });
      return true;
    }
    chrome.tabs
      .get(tabId)
      .then((tab) => {
        const baseUrl = tab?.url ? new URL(tab.url).origin : "https://javdb.com";
        return magnetSync.fetchActressPageItems(tabId, profileUrl, baseUrl, sleep);
      })
      .then((items) => sendResponse({ ok: true, items: items || [] }))
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "lookup_actress_folder") {
    lookupActressFolderFromDesktop(
      String(message.actressName || message.actress_name || "").trim(),
      String(message.javdbId || message.javdb_id || "").trim()
    )
      .then(sendResponse)
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "read_magnet_summary") {
    readMagnetSummaryFromDesktop(
      String(message.actressName || "").trim(),
      Boolean(message.pending_download)
    )
      .then(sendResponse)
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "fetch_actress_video_map") {
    const magnetSync = globalThis.JM_magnetSavedSync;
    const profileUrl = String(message.profileUrl || "").trim();
    const tabId = sender.tab?.id;
    if (!magnetSync || !profileUrl || !tabId) {
      sendResponse({ ok: false, message: "missing_tab_or_profile" });
      return false;
    }
    chrome.tabs
      .get(tabId)
      .then((tab) => {
        const baseUrl = tab?.url ? new URL(tab.url).origin : "https://javdb.com";
        return magnetSync.fetchActressVideoMap(tabId, profileUrl, baseUrl, sleep);
      })
      .then((map) => sendResponse({ ok: true, map: map || {} }))
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "magnet_txt_write") {
    writeMagnetTxtToDesktop(message).then(sendResponse).catch((err) => {
      sendResponse({ ok: false, message: String(err.message || err) });
    });
    return true;
  }

  if (message.type === "magnet_filter_rules_request") {
    fetchMagnetFilterRulesFromDesktopAsync()
      .then((rules) => {
        const ok = Boolean(rules && rules.priorities && rules.priorities.length);
        sendResponse({ ok, rules: rules || null, offline: !socket || socket.readyState !== WebSocket.OPEN });
      })
      .catch(() => sendResponse({ ok: false, rules: null }));
    return true;
  }

  if (message.type === "sticker_sync_request") {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      sendResponse({ ok: false, offline: true });
      return true;
    }
    if (pendingStickerSync) {
      if (pendingStickerSync.timer) clearTimeout(pendingStickerSync.timer);
      pendingStickerSync.reject(new Error("sync_in_progress"));
      pendingStickerSync = null;
    }
    let responded = false;
    const respond = (payload) => {
      if (responded) return;
      responded = true;
      sendResponse(payload);
    };

    const timer = setTimeout(() => {
      if (!pendingStickerSync) return;
      pendingStickerSync.reject(new Error("timeout"));
    }, 5000);

    pendingStickerSync = {
      resolve: (msg) => {
        clearTimeout(timer);
        respond({ ok: true, data: msg });
        pendingStickerSync = null;
      },
      reject: (err) => {
        clearTimeout(timer);
        respond({
          ok: false,
          offline: String(err?.message || err).includes("timeout"),
          message: String(err?.message || err),
        });
        pendingStickerSync = null;
      },
      timer,
    };
    socket.send(JSON.stringify({ type: "sticker_sync_request" }));
    return true;
  }

  if (message.type === "detail_check_sites") {
    const code = String(message.code || "").trim();
    Promise.all([
      globalThis.JM_detailTools.checkMissAv(code),
      globalThis.JM_detailTools.checkJavBus(code),
    ])
      .then((results) => sendResponse({ ok: true, results }))
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "detail_get_long_thumb") {
    const code = String(message.code || "").trim();
    globalThis.JM_detailTools
      .getLongThumbnail(code)
      .then((result) => {
        if (!result) {
          sendResponse({ ok: false, message: "未找到长缩略图" });
          return;
        }
        if (typeof result === "string") {
          sendResponse({ ok: true, url: result, fullUrl: result });
          return;
        }
        sendResponse({ ok: true, url: result.thumb, fullUrl: result.full || result.thumb });
      })
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "detail_search_magnets") {
    const code = String(message.code || "").trim();
    globalThis.JM_detailTools
      .searchMagnetsDual(code)
      .then((data) => sendResponse({ ok: true, ...data }))
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "detail_search_18mag") {
    const code = String(message.code || "").trim();
    const maxResults = Number(message.maxResults) || undefined;
    globalThis.JM_detailTools
      .search18mag(code, maxResults ? { maxResults } : {})
      .then((rows) => sendResponse({ ok: true, rows, total: rows.length }))
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "detail_fetch_actresses") {
    const url = String(message.url || "").trim();
    globalThis.JM_detailTools
      .fetchDetailActresses(url)
      .then((actresses) => sendResponse({ ok: true, actresses }))
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "detail_fetch_actresses_batch") {
    const items = Array.isArray(message.items) ? message.items : [];
    globalThis.JM_detailTools
      .fetchDetailActressesBatch(items, Number(message.concurrency) || 8)
      .then((results) => sendResponse({ ok: true, results }))
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "detail_search_subtitles") {
    const code = String(message.code || "").trim();
    globalThis.JM_detailTools
      .searchXunleiSubtitles(code)
      .then((items) => sendResponse({ ok: true, items }))
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "detail_fetch_subtitle") {
    globalThis.JM_detailTools
      .fetchSubtitleContent(String(message.url || ""))
      .then((content) => sendResponse({ ok: true, content }))
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "detail_download_subtitle") {
    const code = String(message.code || "").trim();
    const ext = String(message.ext || "srt").replace(/^\./, "");
    globalThis.JM_detailTools
      .fetchSubtitleContent(String(message.url || ""))
      .then((content) => {
        const blob = new Blob([content], { type: "application/octet-stream" });
        const url = URL.createObjectURL(blob);
        chrome.downloads.download(
          {
            url,
            filename: `${code}.${ext}`,
            saveAs: false,
          },
          () => {
            URL.revokeObjectURL(url);
            sendResponse({ ok: true });
          }
        );
      })
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "detail_115_offline") {
    globalThis.JM_detailTools
      .add115OfflineTask(String(message.magnet || ""))
      .then((result) => sendResponse({ ok: true, ...result }))
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "save115_filtered") {
    runSave115FilteredJob({
      code: message.code,
      detailUrl: message.detailUrl,
      javdbMagnets: message.javdbMagnets,
      actress: message.actress,
      title: message.title,
    })
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "cancel_new_works_check") {
    newWorksCheckCancelled = true;
    sendResponse({ ok: true });
    return true;
  }

  if (message.type === "check_new_works") {
    runNewWorksCheck()
      .then((result) => sendResponse(result))
      .catch((err) => sendResponse({ ok: false, message: String(err.message || err) }));
    return true;
  }

  if (message.type === "close_current_tab") {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      const tabId = tabs[0]?.id;
      if (tabId) chrome.tabs.remove(tabId);
      sendResponse({ ok: true });
    });
    return true;
  }

  if (message.type === "open_tab") {
    const url = String(message.url || "").trim();
    if (!url) {
      sendResponse({ ok: false, message: "missing_url" });
      return false;
    }
    chrome.tabs.create({ url, active: message.active !== false }, () => {
      sendResponse({ ok: true });
    });
    return true;
  }

  if (message.type === "backup_db_local") {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      sendResponse({ ok: false, message: "桌面端未连接，无法备份" });
      return false;
    }
    const serial = ++stickerActionSerial;
    const timer = setTimeout(() => {
      pendingStickerActions.delete(serial);
      sendResponse({ ok: false, message: "备份超时" });
    }, 15000);
    pendingStickerActions.set(serial, {
      resolve: (result) => sendResponse(result),
      reject: (err) => sendResponse({ ok: false, message: String(err.message || err) }),
      timer,
    });
    socket.send(JSON.stringify({ type: "backup_db_local", _serial: serial }));
    return true;
  }
});
