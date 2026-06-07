/**
 * Detail-page helpers for service worker: site checks, magnet search, subtitles, 115 offline.
 */
(function (root) {
  "use strict";

  const FETCH_HEADERS = {
    "User-Agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    Accept: "text/html,application/xhtml+xml,application/json",
  };

  function decodeHtml(value) {
    return String(value || "")
      .replace(/&amp;/g, "&")
      .replace(/&quot;/g, '"')
      .replace(/&#39;/g, "'")
      .trim();
  }

  function decodeCfEmail(hex) {
    const encoded = String(hex || "").trim();
    if (encoded.length < 4) return "";
    const key = parseInt(encoded.slice(0, 2), 16);
    if (Number.isNaN(key)) return "";
    let email = "";
    for (let i = 2; i < encoded.length; i += 2) {
      email += String.fromCharCode(parseInt(encoded.slice(i, i + 2), 16) ^ key);
    }
    return email;
  }

  function decodeHtmlEntities(text) {
    return String(text || "").replace(/&#(\d+);/g, (_, num) => {
      const code = Number(num);
      return Number.isFinite(code) ? String.fromCharCode(code) : _;
    });
  }

  function sanitize18magCell(raw) {
    let html = String(raw || "");
    html = html.replace(
      /<a[^>]*href="[^"]*email-protection#([a-f0-9]+)"[^>]*>[\s\S]*?<\/a>/gi,
      (_, hex) => decodeCfEmail(hex)
    );
    html = html.replace(
      /<([a-z0-9]+)[^>]*data-cfemail="([a-f0-9]+)"[^>]*>[\s\S]*?<\/\1>/gi,
      (_, _tag, hex) => decodeCfEmail(hex)
    );
    html = html.replace(/<[^>]+>/g, " ");
    html = decodeHtmlEntities(decodeHtml(html));
    return html.replace(/\s+/g, " ").trim();
  }

  async function fetchText(url, options = {}) {
    const resp = await fetch(url, {
      credentials: options.credentials || "omit",
      headers: { ...FETCH_HEADERS, ...(options.headers || {}) },
      redirect: "follow",
    });
    const text = await resp.text();
    return { ok: resp.ok, status: resp.status, url: resp.url, text };
  }

  function missAvUrl(code) {
    return `https://missav.live/${encodeURIComponent(String(code || "").toLowerCase())}`;
  }

  function javBusUrl(code) {
    return `https://www.javbus.com/${encodeURIComponent(String(code || "").toUpperCase())}`;
  }

  async function checkMissAv(code) {
    const url = missAvUrl(code);
    try {
      const res = await fetchText(url);
      const missing =
        res.status === 404 ||
        /404 Not Found|Page Not Found|页面不存在|找不到/i.test(res.text.slice(0, 8000));
      return { site: "missav", available: res.ok && !missing, url };
    } catch (err) {
      return { site: "missav", available: false, url, error: String(err.message || err) };
    }
  }

  async function checkJavBus(code) {
    const url = javBusUrl(code);
    try {
      const res = await fetchText(url);
      const missing =
        res.status === 404 ||
        /404 Page Not Found|Search Any JAV|没有影片|404/i.test(res.text.slice(0, 12000));
      return { site: "javbus", available: res.ok && !missing, url };
    } catch (err) {
      return { site: "javbus", available: false, url, error: String(err.message || err) };
    }
  }

  function parse18magSearch(html) {
    const results = [];
    const linkRegex = /<a href="(\/![^"]+)">([\s\S]*?)<\/a>/gi;
    let match;
    while ((match = linkRegex.exec(html)) !== null) {
      let block = match[2].split(/<p class="sample"/i)[0];
      const title = block.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
      if (!title) continue;

      const after = html.slice(match.index + match[0].length, match.index + match[0].length + 1200);
      const sampleMatch = after.match(/<p class="sample"[^>]*>([\s\S]*?)<\/p>/i);
      const sample = sampleMatch
        ? sampleMatch[1].replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()
        : "";
      const sizeMatch = after.match(/(\d+(?:\.\d+)?\s*(?:GB|MB|TB|KB))/i);
      const size = sizeMatch ? sizeMatch[1].replace(/\s+/g, "") : "";

      results.push({ title, path: match[1], sample, size });
    }
    return results;
  }

  function parse18magDetail(html) {
    let magnet = "";
    const inputMatch = html.match(/id="input-magnet"[^>]*value="([^"]+)"/i);
    if (inputMatch) magnet = decodeHtml(inputMatch[1]);
    if (!magnet) {
      const hrefMatch = html.match(/class="magnet-box"[\s\S]*?href="(magnet:\?[^"]+)"/i);
      if (hrefMatch) magnet = decodeHtml(hrefMatch[1]);
    }
    const titleMatch = html.match(/class="magnet-title"[^>]*>([^<]+)</i);
    const pageTitle = titleMatch ? titleMatch[1].trim() : "";
    const files = [];
    const fileTableMatch = html.match(/<table class="table table-hover file-list">[\s\S]*?<\/table>/i);
    if (fileTableMatch) {
      const rowRegex = /<tr><td>\s*([\s\S]*?)\s*<\/td><td/gi;
      let row;
      while ((row = rowRegex.exec(fileTableMatch[0])) !== null) {
        const name = sanitize18magCell(row[1]);
        if (name && !/^文件\s*\(/i.test(name)) files.push(name);
      }
    }
    return { magnet, pageTitle, files };
  }

  async function fetchDetailActresses(detailUrl) {
    const url = String(detailUrl || "").trim();
    if (!url) return [];
    const res = await fetchText(url);
    if (!res.ok) throw new Error(`详情页请求失败 (${res.status})`);
    return parseActressesFromDetailHtml(res.text);
  }

  function parseActressesFromDetailHtml(html) {
    const doc = new DOMParser().parseFromString(String(html || ""), "text/html");
    const seen = new Set();
    const list = [];

    function pushActress(anchor) {
      const href = anchor.getAttribute("href") || "";
      const match = href.match(/\/(actors|stars)\/([^/?#]+)/i);
      const javdbId = match ? match[2] : "";
      const name = (anchor.textContent || "").trim();
      const key = javdbId || name;
      if (!name || seen.has(key)) return;
      seen.add(key);
      list.push({ javdb_id: javdbId, name });
    }

    doc.querySelectorAll(
      ".movie-panel-info .panel-block, .video-meta-panel .panel-block, .movie-panel-info .meta"
    ).forEach((block) => {
      const label = block.querySelector("strong, .label")?.textContent || "";
      if (!/演员|演員|actress|star|女优|女優/i.test(label)) return;
      block.querySelectorAll('a[href*="/actors/"], a[href*="/stars/"]').forEach(pushActress);
    });

    if (!list.length) {
      doc.querySelectorAll(
        ".movie-panel-info a[href*='/actors/'], .movie-panel-info a[href*='/stars/'], .video-meta-panel a[href*='/actors/'], .video-meta-panel a[href*='/stars/']"
      ).forEach(pushActress);
    }

    return list;
  }

  async function fetchDetailActressesBatch(items, concurrency = 8) {
    const queue = (items || [])
      .map((item) => ({
        code: String(item.code || "").trim().toUpperCase(),
        url: String(item.url || "").trim(),
      }))
      .filter((item) => item.code && item.url.includes("/v/"));
    const results = {};
    if (!queue.length) return results;

    let index = 0;
    async function worker() {
      while (index < queue.length) {
        const current = queue[index++];
        try {
          const actresses = await fetchDetailActresses(current.url);
          if (actresses.length) results[current.code] = actresses;
        } catch (_) {
          /* skip failed item */
        }
      }
    }

    const workers = Math.min(concurrency, queue.length);
    await Promise.all(Array.from({ length: workers }, () => worker()));
    return results;
  }

  const search18magCache = new Map();
  const SEARCH18MAG_TTL_MS = 5 * 60 * 1000;
  const DEFAULT_18MAG_SEARCH_LIMIT = 30;

  async function mapConcurrent(items, fn, concurrency) {
    if (!items?.length) return [];
    const results = new Array(items.length);
    let index = 0;
    async function worker() {
      while (index < items.length) {
        const current = index++;
        results[current] = await fn(items[current], current);
      }
    }
    const workers = Math.min(concurrency, items.length);
    await Promise.all(Array.from({ length: workers }, () => worker()));
    return results;
  }

  async function search18mag(code, options = {}) {
    const normalized = String(code || "").trim();
    if (!normalized) return [];

    const maxResults = Math.max(
      1,
      Math.min(Number(options.maxResults) || DEFAULT_18MAG_SEARCH_LIMIT, DEFAULT_18MAG_SEARCH_LIMIT)
    );
    const cacheKey = `${normalized.toUpperCase()}::${maxResults}`;
    if (!search18magCache.has(cacheKey)) {
      search18magCache.set(cacheKey, { at: 0, rows: null, pending: null });
    }
    const bucket = search18magCache.get(cacheKey);
    if (bucket.rows && Date.now() - bucket.at < SEARCH18MAG_TTL_MS) {
      return bucket.rows;
    }
    if (bucket.pending) return bucket.pending;

    bucket.pending = (async () => {
      const searchUrl = `https://18mag.net/search?q=${encodeURIComponent(normalized)}`;
      const searchHtml = await fetchText(searchUrl);
      if (!searchHtml.ok) throw new Error(`18mag 搜索失败 (${searchHtml.status})`);
      const hits = parse18magSearch(searchHtml.text).slice(0, maxResults);

      async function fetchHitDetail(hit) {
        const detailUrl = `https://18mag.net${hit.path}`;
        try {
          const detail = await fetchText(detailUrl);
          if (!detail.ok) {
            return {
              source: "18mag",
              title: hit.title,
              listTitle: hit.title,
              magnet: "",
              preview: hit.sample || hit.title,
              size: hit.size || "",
              date: "",
              url: detailUrl,
            };
          }
          const parsed = parse18magDetail(detail.text);
          return {
            source: "18mag",
            title: parsed.pageTitle || hit.title,
            listTitle: hit.title,
            magnet: parsed.magnet || "",
            preview: parsed.files.join("\n") || hit.sample || hit.title,
            size: hit.size || "",
            date: "",
            url: detailUrl,
          };
        } catch (_) {
          return {
            source: "18mag",
            title: hit.title,
            listTitle: hit.title,
            magnet: "",
            preview: hit.sample || hit.title,
            size: hit.size || "",
            date: "",
            url: detailUrl,
          };
        }
      }

      const rows = await mapConcurrent(hits, fetchHitDetail, 8);
      bucket.at = Date.now();
      bucket.rows = rows;
      bucket.pending = null;
      return rows;
    })().catch((err) => {
      bucket.pending = null;
      throw err;
    });

    return bucket.pending;
  }

  function parseSukebei(html, keyword) {
    const results = [];
    const keyNorm = String(keyword || "")
      .replace(/-/g, "")
      .toLowerCase();
    const rowRegex = /<tr[\s\S]*?<\/tr>/gi;
    let rowMatch;
    while ((rowMatch = rowRegex.exec(html)) !== null) {
      const row = rowMatch[0];
      if (!/href=["']magnet:/i.test(row)) continue;
      if (/置顶|pinned/i.test(row)) continue;

      const viewLinkMatch =
        row.match(/<a[^>]+href="\/view\/[^"]+"[^>]*title="([^"]*)"/i) ||
        row.match(/<a[^>]+href='\/view\/[^']+'[^>]*title='([^']*)'/i) ||
        row.match(/<a[^>]+href="\/view\/[^"]+"[^>]*>([\s\S]*?)<\/a>/i) ||
        row.match(/<a[^>]+href='\/view\/[^']+'[^>]*>([\s\S]*?)<\/a>/i);
      const title = viewLinkMatch
        ? viewLinkMatch[1].replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim()
        : "";
      if (!title) continue;
      if (keyNorm) {
        const titleNorm = title.replace(/-/g, "").toLowerCase();
        if (!titleNorm.includes(keyNorm)) continue;
      }

      const magnetMatch =
        row.match(/href="(magnet:[^"]+)"/i) ||
        row.match(/href='(magnet:[^']+)'/i) ||
        row.match(/href=&quot;(magnet:[^&]+)&quot;/i);
      if (!magnetMatch) continue;

      const sizeMatch = row.match(/<td[^>]*class="[^"]*text-center[^"]*"[^>]*>\s*([\d.]+\s*[KMGT]?i?B)\s*<\/td>/i);
      const dateMatch = row.match(/<td[^>]*class="[^"]*text-center[^"]*"[^>]*>\s*(20\d{2}-\d{2}-\d{2})\s*<\/td>/i);
      results.push({
        source: "sukebei",
        title,
        magnet: decodeHtml(magnetMatch[1]),
        preview: title,
        size: sizeMatch ? sizeMatch[1].trim() : "",
        date: dateMatch ? dateMatch[1].trim() : "",
        url: "",
      });
    }
    return results;
  }

  async function searchSukebei(code) {
    const normalized = String(code || "").trim();
    if (!normalized) return [];
    const url = `https://sukebei.nyaa.si/?f=0&c=0_0&q=${encodeURIComponent(normalized)}`;
    const res = await fetchText(url);
    if (!res.ok) throw new Error(`Sukebei 搜索失败 (${res.status})`);
    return parseSukebei(res.text, normalized);
  }

  async function searchMagnetsDual(code) {
    const [mag18, sukebei] = await Promise.allSettled([search18mag(code), searchSukebei(code)]);
    return {
      mag18: mag18.status === "fulfilled" ? mag18.value : [],
      sukebei: sukebei.status === "fulfilled" ? sukebei.value : [],
      errors: {
        mag18: mag18.status === "rejected" ? String(mag18.reason?.message || mag18.reason) : "",
        sukebei: sukebei.status === "rejected" ? String(sukebei.reason?.message || sukebei.reason) : "",
      },
    };
  }

  async function searchXunleiSubtitles(code) {
    const url = `https://api-shoulei-ssl.xunlei.com/oracle/subtitle?gcid=&cid=&name=${encodeURIComponent(code)}`;
    const resp = await fetch(url, { headers: FETCH_HEADERS });
    if (!resp.ok) throw new Error(`迅雷字幕 API 失败 (${resp.status})`);
    const json = await resp.json();
    return Array.isArray(json.data) ? json.data : [];
  }

  async function fetchSubtitleContent(url) {
    const res = await fetchText(url);
    if (!res.ok) throw new Error(`字幕下载失败 (${res.status})`);
    return res.text;
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

  async function getLongThumbnail(code) {
    const carNum2 = String(code || "").trim();
    if (!carNum2) return null;
    const searchUrl = `https://javstore.net/search?q=${encodeURIComponent(
      carNum2.toLowerCase().replace(/^fc2-/i, "")
    )}`;
    const search = await fetchText(searchUrl);
    if (!search.ok) throw new Error("JavStore 搜索失败");

    const tempCarNum = carNum2.toLowerCase().replace(/fc2-(ppv-)?/gi, "").replace(/-/g, "");
    const mainMatch = search.text.match(/<main[\s\S]*?<\/main>/i);
    const scope = mainMatch ? mainMatch[0] : search.text;
    const anchorRegex = /<a[^>]+href="(\/[^"]+)"/gi;
    let detailPath = "";
    let m;
    while ((m = anchorRegex.exec(scope)) !== null) {
      const href = m[1];
      const normalized = href.toLowerCase().replace(/fc2-(ppv-)?/gi, "").replace(/-/g, "");
      if (normalized.includes(tempCarNum)) {
        detailPath = href;
        break;
      }
    }
    if (!detailPath) throw new Error("未找到长缩略图");

    const detail = await fetchText(`https://javstore.net${detailPath}`);
    if (!detail.ok) throw new Error("JavStore 详情失败");

    let imgUrl = "";
    const clickHereMatch =
      detail.text.match(/<a[^>]*href="(https?:[^"]+)"[^>]*>[\s\S]{0,80}?CLICK HERE/i) ||
      detail.text.match(/CLICK HERE[\s\S]{0,120}?<a[^>]*href="(https?:[^"]+)"/i);
    if (clickHereMatch) imgUrl = clickHereMatch[1];

    if (!imgUrl) {
      const imgMatch = detail.text.match(/src="(https?:\/\/[^"]*_s\.jpg[^"]*)"/i);
      if (imgMatch) imgUrl = imgMatch[1];
    }
    if (!imgUrl) {
      const hrefImgMatch = detail.text.match(/href="(https?:\/\/[^"]*_s\.jpg[^"]*)"/i);
      if (hrefImgMatch) imgUrl = hrefImgMatch[1];
    }
    if (!imgUrl) throw new Error("未解析到缩略图");

    const thumb = normalizeThumbnailUrl(imgUrl);
    return {
      thumb,
      full: resolveFullImageUrl(thumb) || thumb,
    };
  }

  async function get115SignInfo() {
    const res = await fetch(`https://115.com/?ct=offline&ac=space&_=${Date.now()}`, {
      credentials: "include",
      headers: FETCH_HEADERS,
    });
    const text = await res.text();
    try {
      return JSON.parse(text);
    } catch (_) {
      return null;
    }
  }

  async function get115DownPathId() {
    const resp = await fetch("https://webapi.115.com/offine/downpath", {
      credentials: "include",
      headers: FETCH_HEADERS,
    });
    const json = await resp.json();
    const list = json?.data || json || [];
    if (Array.isArray(list) && list.length > 0) return String(list[0].id || list[0].file_id || "");
    return "";
  }

  async function add115OfflineTask(magnetLink) {
    const magnet = String(magnetLink || "").trim();
    if (!magnet.startsWith("magnet:")) throw new Error("无效的磁链");
    const signInfo = await get115SignInfo();
    if (!signInfo?.sign || !signInfo?.time) {
      throw new Error("未登录 115 网盘，请先在浏览器登录 115.com");
    }
    const uid = await get115DownPathId();
    if (!uid) throw new Error("无法获取 115 离线下载目录，请先在 115 网盘设置默认离线文件夹");
    const body = new URLSearchParams({
      url: magnet,
      wp_path_id: "",
      uid,
      sign: signInfo.sign,
      time: String(signInfo.time),
    });
    const resp = await fetch("https://115.com/web/lixian/?ct=lixian&ac=add_task_url", {
      method: "POST",
      credentials: "include",
      headers: {
        ...FETCH_HEADERS,
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: body.toString(),
    });
    const text = await resp.text();
    let json = null;
    try {
      json = JSON.parse(text);
    } catch (_) {
      throw new Error("115 返回异常");
    }
    if (json.state === false) throw new Error(json.error_msg || json.errmsg || "115 添加失败");
    return { ok: true, info_hash: json.info_hash || "" };
  }

  async function fetchActressPageCodes(javdbId) {
    const url = `https://javdb.com/actors/${encodeURIComponent(javdbId)}?t=d`;
    const res = await fetchText(url);
    if (!res.ok) throw new Error(`女优页请求失败 (${res.status})`);
    const codes = new Set();
    const titleRegex = /video-title[^>]*>([^<]+)/gi;
    let t;
    while ((t = titleRegex.exec(res.text)) !== null) {
      const text = t[1].replace(/<[^>]+>/g, " ").trim();
      const patterns = [/FC2-PPV-\d{6,7}/i, /[A-Z]{2,10}-\d{2,5}[A-Z]?/i];
      for (const pattern of patterns) {
        const match = text.match(pattern);
        if (match) {
          codes.add(match[0].toUpperCase());
          break;
        }
      }
    }
    return Array.from(codes);
  }

  root.JM_detailTools = {
    missAvUrl,
    javBusUrl,
    checkMissAv,
    checkJavBus,
    search18mag,
    fetchDetailActresses,
    fetchDetailActressesBatch,
    searchMagnetsDual,
    searchXunleiSubtitles,
    fetchSubtitleContent,
    getLongThumbnail,
    add115OfflineTask,
    fetchActressPageCodes,
  };
})(globalThis);
