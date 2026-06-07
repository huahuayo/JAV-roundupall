/* global globalThis, JM_findBestNameMatch */
(function () {
  "use strict";

  const ACTRESS_COLLECTION_PATH = "/users/collection_actors";
  const SKIP_ACTOR_IDS = new Set(["favorite", "collection", "collections", "search"]);

  function isFrameRemovedError(err) {
    return /frame with id 0 was removed/i.test(String(err?.message || err || ""));
  }

  async function fetchCollectionPage(tabId, baseUrl, page) {
    const url =
      page <= 1
        ? `${baseUrl}${ACTRESS_COLLECTION_PATH}`
        : `${baseUrl}${ACTRESS_COLLECTION_PATH}?page=${page}`;

    const scriptDetails = {
      func: async (fetchUrl, origin, skipActorIds) => {
        const resp = await fetch(fetchUrl, {
          credentials: "include",
          redirect: "follow",
          headers: { Accept: "text/html,application/xhtml+xml" },
        });
        const finalUrl = resp.url || fetchUrl;
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`);
        }
        if (finalUrl.includes("sign_in") || finalUrl.includes("/login")) {
          return { loginRequired: true, entries: [], maxPage: 1 };
        }

        const html = await resp.text();
        const doc = new DOMParser().parseFromString(html, "text/html");
        const map = new Map();
        const skip = new Set((skipActorIds || []).map((s) => String(s).toLowerCase()));

        const addActress = (href, name) => {
          if (!href) return;
          const match = href.match(/\/(actors|stars)\/([^/?#]+)/i);
          if (!match) return;
          const javdbId = match[2];
          if (!javdbId || skip.has(javdbId.toLowerCase())) return;
          const cleanName = String(name || "")
            .replace(/\s+/g, " ")
            .trim();
          if (!cleanName || cleanName.length > 120) return;
          if (/^(收藏|女优|演员|login|登录)$/i.test(cleanName)) return;

          let profileUrl = href;
          try {
            profileUrl = new URL(href, origin).href;
          } catch (_) {
            profileUrl = `${origin}${href.startsWith("/") ? href : `/${href}`}`;
          }

          map.set(javdbId, {
            javdb_id: javdbId,
            name: cleanName,
            profile_url: profileUrl,
            source: "collection_actors",
          });
        };

        doc.querySelectorAll("#actors .actor-box a[href]").forEach((anchor) => {
          const href = anchor.getAttribute("href") || "";
          const name =
            anchor.getAttribute("title")?.trim() ||
            anchor.querySelector(".actor-name")?.textContent?.trim() ||
            anchor.querySelector("img")?.getAttribute("alt")?.trim() ||
            anchor.textContent?.trim();
          addActress(href, name);
        });

        doc.querySelectorAll('a[href*="/actors/"], a[href*="/stars/"]').forEach((anchor) => {
          const href = anchor.getAttribute("href") || "";
          const name =
            anchor.querySelector(".actor-name")?.textContent?.trim() ||
            anchor.querySelector("strong")?.textContent?.trim() ||
            anchor.querySelector("img")?.getAttribute("alt")?.trim() ||
            anchor.getAttribute("title")?.trim() ||
            anchor.textContent?.trim();
          addActress(href, name);
        });

        doc.querySelectorAll(".actor-box, .grid-item, .item").forEach((item) => {
          const anchor = item.querySelector('a[href*="/actors/"], a[href*="/stars/"]');
          if (!anchor) return;
          const href = anchor.getAttribute("href") || "";
          const name =
            item.querySelector(".actor-name")?.textContent?.trim() ||
            anchor.querySelector("img")?.getAttribute("alt")?.trim() ||
            anchor.textContent?.trim();
          addActress(href, name);
        });

        let maxPage = 1;
        doc
          .querySelectorAll("nav.pagination a, .pagination a, .pagination-link, .pagination-list a")
          .forEach((a) => {
            const href = a.getAttribute("href") || "";
            const pageMatch = href.match(/[?&]page=(\d+)/i);
            if (pageMatch) maxPage = Math.max(maxPage, parseInt(pageMatch[1], 10));
            const text = (a.textContent || "").trim();
            if (/^\d+$/.test(text)) maxPage = Math.max(maxPage, parseInt(text, 10));
          });

        return {
          loginRequired: map.size === 0 && /sign_in|請先登|请先登|登录/i.test(html),
          entries: Array.from(map.values()),
          maxPage,
        };
      },
      args: [url, baseUrl, Array.from(SKIP_ACTOR_IDS)],
    };

    const maxAttempts = 4;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      try {
        const injection = await chrome.scripting.executeScript({
          target: { tabId },
          ...scriptDetails,
        });
        const frame = injection?.[0];
        if (!frame) {
          throw new Error("无法在 JavDB 页面注入脚本，请刷新 JavDB 标签页后重试");
        }
        if (frame.error) {
          const detail = frame.error.message || String(frame.error);
          throw new Error(detail);
        }
        if (frame.result == null || typeof frame.result !== "object") {
          throw new Error("无法解析 JavDB 收藏女优页面，请确认已登录 JavDB 且收藏列表可访问");
        }
        return frame.result;
      } catch (err) {
        if (isFrameRemovedError(err) && attempt < maxAttempts - 1) {
          await new Promise((resolve) => setTimeout(resolve, 500 + attempt * 300));
          continue;
        }
        throw err;
      }
    }
    throw new Error("无法读取 JavDB 收藏女优页面");
  }

  async function fetchAllCollectionEntries(tabId, baseUrl, _path, _parserName, sleepFn) {
    const all = new Map();
    let maxPage = 1;
    let loginRequired = false;

    for (let page = 1; page <= maxPage; page++) {
      const pageData = await fetchCollectionPage(tabId, baseUrl, page);
      if (!pageData || typeof pageData !== "object") {
        throw new Error("无法读取 JavDB 收藏女优页面");
      }
      if (pageData.loginRequired) {
        loginRequired = true;
        break;
      }
      maxPage = Math.max(maxPage, pageData.maxPage || 1);
      for (const entry of pageData.entries || []) {
        all.set(entry.javdb_id, entry);
      }
      if (page < maxPage) await sleepFn(350);
    }

    return { loginRequired, entries: Array.from(all.values()) };
  }

  function matchFolderInActresses(folderName, actresses) {
    return JM_findBestNameMatch(folderName, actresses, (item) => item.name);
  }

  function parseActressEntriesFromDocument(doc, origin) {
    const map = new Map();
    const skip = SKIP_ACTOR_IDS;

    const addActress = (href, name) => {
      if (!href) return;
      const match = href.match(/\/(actors|stars)\/([^/?#]+)/i);
      if (!match) return;
      const javdbId = match[2];
      if (!javdbId || skip.has(javdbId.toLowerCase())) return;
      const cleanName = String(name || "")
        .replace(/\s+/g, " ")
        .trim();
      if (!cleanName || cleanName.length > 120) return;
      if (/^(收藏|女优|演员|login|登录)$/i.test(cleanName)) return;

      let profileUrl = href;
      try {
        profileUrl = new URL(href, origin).href;
      } catch (_) {
        profileUrl = `${origin}${href.startsWith("/") ? href : `/${href}`}`;
      }

      map.set(javdbId, {
        javdb_id: javdbId,
        name: cleanName,
        profile_url: profileUrl,
        source: "javdb_search",
      });
    };

    doc.querySelectorAll('a[href*="/actors/"], a[href*="/stars/"]').forEach((anchor) => {
      const href = anchor.getAttribute("href") || "";
      const name =
        anchor.querySelector(".actor-name")?.textContent?.trim() ||
        anchor.querySelector("strong")?.textContent?.trim() ||
        anchor.querySelector("img")?.getAttribute("alt")?.trim() ||
        anchor.getAttribute("title")?.trim() ||
        anchor.textContent?.trim();
      addActress(href, name);
    });

    doc.querySelectorAll(".actor-box, .grid-item, .item").forEach((item) => {
      const anchor = item.querySelector('a[href*="/actors/"], a[href*="/stars/"]');
      if (!anchor) return;
      const href = anchor.getAttribute("href") || "";
      const name =
        item.querySelector(".actor-name")?.textContent?.trim() ||
        anchor.querySelector("img")?.getAttribute("alt")?.trim() ||
        anchor.textContent?.trim();
      addActress(href, name);
    });

    return Array.from(map.values());
  }

  function findActressFromSearchDocument(doc, folderName, origin) {
    const entries = parseActressEntriesFromDocument(doc, origin);
    return matchFolderInActresses(folderName, entries);
  }

  globalThis.JM_pendingDownloadCollections = {
    ACTRESS_COLLECTION_PATH,
    fetchCollectionPage,
    fetchAllCollectionEntries,
    matchFolderInActresses,
    findActressFromSearchDocument,
    parseActressEntriesFromDocument,
  };
})();
