/* global globalThis */
(function () {
  "use strict";

  const MAX_PROFILE_PAGES = 25;
  const FETCH_TIMEOUT_MS = 20000;

  function isFrameRemovedError(err) {
    return /frame with id 0 was removed/i.test(String(err?.message || err || ""));
  }

  async function executeScriptWithRetry(tabId, details) {
    const maxAttempts = 4;
    for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
      try {
        const injection = await chrome.scripting.executeScript({
          target: { tabId },
          ...details,
        });
        const frame = injection?.[0];
        if (frame?.error) {
          throw new Error(frame.error.message || String(frame.error));
        }
        return frame?.result;
      } catch (err) {
        if (isFrameRemovedError(err) && attempt < maxAttempts - 1) {
          await new Promise((resolve) => setTimeout(resolve, 500 + attempt * 300));
          continue;
        }
        throw err;
      }
    }
    return undefined;
  }

  async function fetchActressVideoMap(tabId, profileUrl, baseUrl, sleepFn) {
    const all = new Map();
    let maxPage = 1;

    for (let page = 1; page <= maxPage && page <= MAX_PROFILE_PAGES; page += 1) {
      const pageUrl =
        page <= 1
          ? profileUrl
          : `${profileUrl}${profileUrl.includes("?") ? "&" : "?"}page=${page}`;

      const result = await executeScriptWithRetry(tabId, {
        func: async (fetchUrl, origin, timeoutMs) => {
          const controller = new AbortController();
          const timer = setTimeout(() => controller.abort(), timeoutMs);
          let resp;
          try {
            resp = await fetch(fetchUrl, {
              credentials: "include",
              redirect: "follow",
              headers: { Accept: "text/html,application/xhtml+xml" },
              signal: controller.signal,
            });
          } catch (err) {
            if (err && err.name === "AbortError") {
              throw new Error(`请求超时 (${timeoutMs}ms)`);
            }
            throw err;
          } finally {
            clearTimeout(timer);
          }
          if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
          }

          const html = await resp.text();
          const doc = new DOMParser().parseFromString(html, "text/html");
          const normalizeCode = (raw) => {
            const text = String(raw || "").toUpperCase().trim();
            const match = text.match(/^([A-Z]+)-?(\d+[A-Z]?)$/);
            if (match) return `${match[1]}-${match[2]}`;
            return text;
          };
          const patterns = [
            /FC2-PPV-\d{6,7}/i,
            /HEYZO-\d{4}/i,
            /[A-Z]{2,10}-\d{2,5}[A-Z]?/i,
            /[A-Z]{2,10}\d{2,5}[A-Z]?/i,
          ];
          const extractCode = (text) => {
            const cleaned = String(text || "")
              .replace(/[\[\(（【].*?[\]\)）】]/g, " ")
              .replace(/[_\.\s]+/g, " ");
            for (const pattern of patterns) {
              const match = cleaned.match(pattern);
              if (match) return normalizeCode(match[0]);
            }
            return null;
          };

          const map = new Map();
          const movieList = doc.querySelector(
            ".movie-list:not(.movie-list-related):not(.related-movies)"
          );
          const items = movieList
            ? Array.from(movieList.children).filter((el) =>
                el.matches(".item, .column, .grid-item")
              )
            : [];

          for (const item of items) {
            const titleEl =
              item.querySelector(".video-title, .video-title a, a[title]");
            const title = (titleEl?.textContent || titleEl?.getAttribute("title") || "").trim();
            const code = extractCode(title);
            const linkEl = item.querySelector('a[href*="/v/"]');
            if (!code || !linkEl) continue;
            let href = linkEl.getAttribute("href") || "";
            try {
              href = new URL(href, origin).href;
            } catch (_) {
              href = `${origin}${href.startsWith("/") ? href : `/${href}`}`;
            }
            map.set(code.toUpperCase(), href);
          }

          let maxPageLocal = 1;
          doc
            .querySelectorAll(
              "nav.pagination a, .pagination a, .pagination-link, .pagination-list a"
            )
            .forEach((a) => {
              const href = a.getAttribute("href") || "";
              const pageMatch = href.match(/[?&]page=(\d+)/i);
              if (pageMatch) maxPageLocal = Math.max(maxPageLocal, parseInt(pageMatch[1], 10));
              const text = (a.textContent || "").trim();
              if (/^\d+$/.test(text)) maxPageLocal = Math.max(maxPageLocal, parseInt(text, 10));
            });

          return { entries: Array.from(map.entries()), maxPage: maxPageLocal };
        },
        args: [pageUrl, baseUrl, FETCH_TIMEOUT_MS],
      });

      if (!result) {
        throw new Error("无法解析女优作品列表");
      }
      maxPage = Math.min(Math.max(maxPage, result.maxPage || 1), MAX_PROFILE_PAGES);
      for (const [code, href] of result.entries || []) {
        all.set(code, href);
      }
      if (page < maxPage) await sleepFn(300);
    }

    return Object.fromEntries(all);
  }

  async function fetchActressPageItems(tabId, profileUrl, baseUrl, sleepFn) {
    const all = [];
    const seen = new Set();
    let maxPage = 1;

    for (let page = 1; page <= maxPage && page <= MAX_PROFILE_PAGES; page += 1) {
      const pageUrl =
        page <= 1
          ? profileUrl
          : `${profileUrl}${profileUrl.includes("?") ? "&" : "?"}page=${page}`;

      const result = await executeScriptWithRetry(tabId, {
        func: async (fetchUrl, origin, timeoutMs) => {
          const controller = new AbortController();
          const timer = setTimeout(() => controller.abort(), timeoutMs);
          let resp;
          try {
            resp = await fetch(fetchUrl, {
              credentials: "include",
              redirect: "follow",
              headers: { Accept: "text/html,application/xhtml+xml" },
              signal: controller.signal,
            });
          } catch (err) {
            if (err && err.name === "AbortError") {
              throw new Error(`请求超时 (${timeoutMs}ms)`);
            }
            throw err;
          } finally {
            clearTimeout(timer);
          }
          if (!resp.ok) {
            throw new Error(`HTTP ${resp.status}`);
          }

          const html = await resp.text();
          const doc = new DOMParser().parseFromString(html, "text/html");
          const normalizeCode = (raw) => {
            const text = String(raw || "").toUpperCase().trim();
            const match = text.match(/^([A-Z]+)-?(\d+[A-Z]?)$/);
            if (match) return `${match[1]}-${match[2]}`;
            return text;
          };
          const patterns = [
            /FC2-PPV-\d{6,7}/i,
            /HEYZO-\d{4}/i,
            /[A-Z]{2,10}-\d{2,5}[A-Z]?/i,
            /[A-Z]{2,10}\d{2,5}[A-Z]?/i,
          ];
          const extractCode = (text) => {
            const cleaned = String(text || "")
              .replace(/[\[\(（【].*?[\]\)）】]/g, " ")
              .replace(/[_\.\s]+/g, " ");
            for (const pattern of patterns) {
              const match = cleaned.match(pattern);
              if (match) return normalizeCode(match[0]);
            }
            return null;
          };

          const items = [];
          const movieList = doc.querySelector(
            ".movie-list:not(.movie-list-related):not(.related-movies)"
          );
          const nodes = movieList
            ? Array.from(movieList.children).filter((el) =>
                el.matches(".item, .column, .grid-item")
              )
            : [];

          for (const item of nodes) {
            const titleEl =
              item.querySelector(".video-title, .video-title a, a[title]");
            const title = (titleEl?.textContent || titleEl?.getAttribute("title") || "").trim();
            const code = extractCode(title);
            const linkEl = item.querySelector('a[href*="/v/"]');
            if (!code || !linkEl) continue;
            let href = linkEl.getAttribute("href") || "";
            try {
              href = new URL(href, origin).href;
            } catch (_) {
              href = `${origin}${href.startsWith("/") ? href : `/${href}`}`;
            }
            const imgEl = item.querySelector("img");
            const coverUrl = imgEl?.getAttribute("src") || imgEl?.getAttribute("data-src") || "";
            items.push({
              code: code.toUpperCase(),
              title,
              detailUrl: href,
              coverUrl,
            });
          }

          let maxPageLocal = 1;
          doc
            .querySelectorAll(
              "nav.pagination a, .pagination a, .pagination-link, .pagination-list a"
            )
            .forEach((a) => {
              const href = a.getAttribute("href") || "";
              const pageMatch = href.match(/[?&]page=(\d+)/i);
              if (pageMatch) maxPageLocal = Math.max(maxPageLocal, parseInt(pageMatch[1], 10));
              const text = (a.textContent || "").trim();
              if (/^\d+$/.test(text)) maxPageLocal = Math.max(maxPageLocal, parseInt(text, 10));
            });

          return { items, maxPage: maxPageLocal };
        },
        args: [pageUrl, baseUrl, FETCH_TIMEOUT_MS],
      });

      if (!result) {
        throw new Error("无法解析女优作品列表");
      }
      maxPage = Math.min(Math.max(maxPage, result.maxPage || 1), MAX_PROFILE_PAGES);
      for (const item of result.items || []) {
        const code = String(item.code || "").toUpperCase();
        if (!code || seen.has(code)) continue;
        seen.add(code);
        all.push(item);
      }
      if (page < maxPage) await sleepFn(300);
    }

    return all;
  }

  globalThis.JM_magnetSavedSync = {
    fetchActressVideoMap,
    fetchActressPageItems,
  };
})();
