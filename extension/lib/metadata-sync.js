/* global globalThis */
(function () {
  "use strict";

  const CODE_PATTERNS = [
    /FC2-PPV-\d{6,7}/i,
    /HEYZO-\d{4}/i,
    /[A-Z]{2,10}-\d{2,5}[A-Z]?/i,
    /[A-Z]{2,10}\d{2,5}[A-Z]?/i,
  ];

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

  function normalizeLabel(text) {
    return String(text || "")
      .replace(/[:：]\s*$/, "")
      .trim()
      .toLowerCase();
  }

  function readBlockValue(block) {
    const valueEl = block.querySelector(".value");
    if (valueEl) {
      return (valueEl.textContent || "").trim();
    }
    const labelEl = block.querySelector("strong, .label");
    const labelText = (labelEl?.textContent || "").trim();
    let text = (block.textContent || "").trim();
    if (labelText) {
      text = text.replace(labelText, "").replace(/^[:：\s]+/, "").trim();
    }
    return text;
  }

  function readBlockLinks(block) {
    const links = Array.from(block.querySelectorAll("a"))
      .map((a) => (a.textContent || "").trim())
      .filter(Boolean);
    if (links.length) return links.join("、");
    return readBlockValue(block);
  }

  function collectPanelMap(doc) {
    const map = {};
    const blocks = doc.querySelectorAll(
      ".movie-panel-info .panel-block, .movie-panel-info .meta, .video-meta-panel .panel-block"
    );
    blocks.forEach((block) => {
      const labelEl = block.querySelector("strong, .label");
      const label = normalizeLabel(labelEl?.textContent || "");
      if (!label) return;
      const hasLinks = block.querySelector("a");
      map[label] = hasLinks ? readBlockLinks(block) : readBlockValue(block);
    });
    return map;
  }

  function pickField(map, patterns) {
    for (const [label, value] of Object.entries(map)) {
      if (patterns.some((pattern) => pattern.test(label))) {
        return String(value || "").trim();
      }
    }
    return "";
  }

  function resolveImageUrl(raw, origin) {
    const src = String(raw || "").trim();
    if (!src || /placeholder|default|avatar|loading/i.test(src)) return "";
    if (/^chrome-extension:/i.test(src)) return "";
    try {
      const href = new URL(src, origin).href;
      if (!/^https?:\/\//i.test(href)) return "";
      return href;
    } catch (_) {
      return "";
    }
  }

  function imageSrc(img) {
    if (!img) return "";
    return (
      img.getAttribute("data-src") ||
      img.getAttribute("data-original") ||
      img.getAttribute("data-url") ||
      img.getAttribute("src") ||
      ""
    );
  }

  function findCoverUrl(doc, origin) {
    const coverEl = doc.querySelector(".column-video-cover .cover, .video-cover, .cover-container");
    if (coverEl) {
      const style = coverEl.getAttribute("style") || "";
      const bgMatch = style.match(/url\(["']?([^"')]+)/i);
      if (bgMatch) {
        const url = resolveImageUrl(bgMatch[1], origin);
        if (url) return url;
      }
    }

    const og = doc.querySelector('meta[property="og:image"], meta[name="twitter:image"]');
    if (og) {
      const url = resolveImageUrl(og.getAttribute("content"), origin);
      if (url) return url;
    }

    const selectors = [
      ".column-video-cover img",
      ".video-cover img",
      ".cover-container img",
      ".movie-panel-info .cover img",
      ".cover img",
      "a.cover-box img",
      ".video-detail .cover img",
    ];
    for (const sel of selectors) {
      const img = doc.querySelector(sel);
      const url = resolveImageUrl(imageSrc(img), origin);
      if (url) return url;
    }

    const coverLink = doc.querySelector(".column-video-cover a[href], .video-cover a[href]");
    if (coverLink) {
      const href = coverLink.getAttribute("href") || "";
      if (/\.(jpg|jpeg|png|webp)(\?|$)/i.test(href)) {
        return resolveImageUrl(href, origin);
      }
    }
    return "";
  }

  function findRating(doc, panel) {
    const fromPanel = pickField(panel, [/评分/, /評分/, /rating/i, /score/i]);
    if (fromPanel) return fromPanel;
    const scoreEl = doc.querySelector(".movie-panel-info .score, .video-detail .score, .score");
    return (scoreEl?.textContent || "").replace(/\s+/g, " ").trim();
  }

  function extractJavdbVideoId(pageUrl, doc) {
    const candidates = [String(pageUrl || ""), doc?.querySelector('link[rel="canonical"]')?.getAttribute("href") || ""];
    const ogUrl = doc?.querySelector('meta[property="og:url"]')?.getAttribute("content") || "";
    if (ogUrl) candidates.push(ogUrl);
    for (const text of candidates) {
      const match = String(text).match(/\/v\/([0-9a-z]+)/i);
      if (match) return match[1];
    }
    return "";
  }

  function samplePreviewIndex(url, videoId) {
    if (!url || !videoId) return -1;
    const match = String(url).match(new RegExp(`${videoId}_[ls]_(\\d+)\\.(jpg|jpeg|png|webp)`, "i"));
    return match ? parseInt(match[1], 10) : -1;
  }

  function toLargeSampleUrl(url, videoId) {
    if (!url || !videoId) return url;
    if (new RegExp(`${videoId}_l_\\d+`, "i").test(url)) return url;
    return String(url).replace(new RegExp(`(${videoId})_s_(\\d+)`, "i"), "$1_l_$2");
  }

  function isCurrentVideoSampleUrl(url, videoId) {
    return samplePreviewIndex(url, videoId) >= 0;
  }

  function findPreviewUrls(doc, origin, pageUrl) {
    const videoId = extractJavdbVideoId(pageUrl, doc);
    if (!videoId) return [];

    const indexed = new Map();
    const addCandidate = (raw) => {
      const url = resolveImageUrl(raw, origin);
      if (!url || !isCurrentVideoSampleUrl(url, videoId)) return;
      const index = samplePreviewIndex(url, videoId);
      const largeUrl = toLargeSampleUrl(url, videoId);
      if (!indexed.has(index)) {
        indexed.set(index, largeUrl);
        return;
      }
      if (/_l_/i.test(largeUrl)) {
        indexed.set(index, largeUrl);
      }
    };

    const previewRoots = doc.querySelectorAll(
      ".preview-images, .tile-images, .video-preview, #preview-tabs, .preview-screenshots, .panel-images"
    );
    const scanRoot = (root) => {
      root.querySelectorAll("a[href]").forEach((link) => addCandidate(link.getAttribute("href")));
      root.querySelectorAll("img").forEach((img) => addCandidate(imageSrc(img)));
    };

    if (previewRoots.length) {
      previewRoots.forEach((root) => {
        if (root.closest(".movie-list-related, .recommendations, .recommended, .related-videos")) return;
        scanRoot(root);
      });
    }

    doc.querySelectorAll("a[href*='jdbstatic.com/samples/'], img[src*='jdbstatic.com/samples/'], img[data-src*='jdbstatic.com/samples/']").forEach((el) => {
      if (el.closest(".movie-list-related, .recommendations, .recommended, .related-videos")) return;
      if (el.tagName === "A") addCandidate(el.getAttribute("href"));
      else addCandidate(imageSrc(el));
    });

    return Array.from(indexed.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([, url]) => url);
  }

  function collectActressLinks(doc) {
    const names = [];
    const seen = new Set();
    doc.querySelectorAll(".movie-panel-info .panel-block, .video-meta-panel .panel-block").forEach((block) => {
      const label = normalizeLabel(block.querySelector("strong, .label")?.textContent || "");
      if (!label || !/演员|演員|actress|star|女优|女優/i.test(label)) return;
      block.querySelectorAll("a").forEach((link) => {
        const name = (link.textContent || "").trim();
        if (!name || seen.has(name)) return;
        seen.add(name);
        names.push(name);
      });
    });
    return names.join("、");
  }

  function collectCategoryLinks(doc) {
    const names = [];
    const seen = new Set();
    doc.querySelectorAll(".movie-panel-info .panel-block, .video-meta-panel .panel-block").forEach((block) => {
      const label = normalizeLabel(block.querySelector("strong, .label")?.textContent || "");
      if (!label || !/类别|類別|genre|tag/i.test(label)) return;
      block.querySelectorAll("a").forEach((link) => {
        const name = (link.textContent || "").trim();
        if (!name || seen.has(name)) return;
        seen.add(name);
        names.push(name);
      });
    });
    doc.querySelectorAll(".tags .tag, .tag-list .tag, .panel-block .tag").forEach((tag) => {
      const name = (tag.textContent || "").trim();
      if (!name || seen.has(name)) return;
      seen.add(name);
      names.push(name);
    });
    return names.join("、");
  }

  function resolvePageUrl(raw, origin) {
    const href = String(raw || "").trim();
    if (!href) return "";
    try {
      return new URL(href, origin).href;
    } catch (_) {
      return "";
    }
  }

  function findDetailUrlFromSearchDocument(doc, code, origin) {
    const expected = normalizeCode(code);
    if (!expected) return "";

    const items = doc.querySelectorAll(
      ".movie-list:not(.movie-list-related) .item, .movie-list:not(.movie-list-related) .grid-item, .movie-list:not(.movie-list-related) .column"
    );
    for (const item of items) {
      const titleEl = item.querySelector(".video-title, .video-title a, a[title]");
      const title = (titleEl?.textContent || titleEl?.getAttribute("title") || "").trim();
      const itemCode = extractCode(title);
      const linkEl = item.querySelector('a[href*="/v/"]');
      if (!linkEl) continue;
      const href = resolvePageUrl(linkEl.getAttribute("href"), origin);
      if (itemCode && itemCode.toUpperCase() === expected.toUpperCase()) {
        return href;
      }
    }

    const first = doc.querySelector('.movie-list:not(.movie-list-related) a[href*="/v/"]');
    return first ? resolvePageUrl(first.getAttribute("href"), origin) : "";
  }

  function parseDetailDocument(doc, pageUrl, origin) {
    const panel = collectPanelMap(doc);
    const titleEl =
      doc.querySelector(".movie-panel-info h2.title") ||
      doc.querySelector(".video-detail h2.title") ||
      doc.querySelector("h2.title") ||
      doc.querySelector(".current-title") ||
      doc.querySelector("h1.title");
    const title = (titleEl?.textContent || doc.title.split("|")[0] || "").trim();
    let code = extractCode(title);
    if (!code) {
      code = normalizeCode(pickField(panel, [/番号/, /番號/, /识别码/, /識別碼/, /code/i]) || "");
    }

    const releaseDateRaw = pickField(panel, [/日期/, /發行/, /发行/, /released/i]);
    const releaseMatch = releaseDateRaw.match(/\d{4}[-/.]\d{1,2}[-/.]\d{1,2}/);
    const releaseDate = releaseMatch ? releaseMatch[0].replace(/\//g, "-") : releaseDateRaw;

    let detailUrl = pageUrl;
    try {
      detailUrl = new URL(pageUrl, origin).href;
    } catch (_) {
      detailUrl = pageUrl;
    }

    return {
      code: code || "",
      title,
      releaseDate,
      duration: pickField(panel, [/时长/, /時長/, /分鐘/, /分钟/, /duration/i, /length/i]),
      director: pickField(panel, [/导演/, /導演/, /director/i]),
      studio: pickField(panel, [/片商/, /制作/, /製作/, /maker/i, /studio/i, /label/i]),
      series: pickField(panel, [/系列/, /series/i]),
      categories: pickField(panel, [/类别/, /類別/, /genre/i, /tag/i]) || collectCategoryLinks(doc),
      actresses: pickField(panel, [/演员/, /演員/, /actress/i, /star/i, /女优/, /女優/i]) || collectActressLinks(doc),
      rating: findRating(doc, panel),
      coverUrl: findCoverUrl(doc, origin),
      previewUrls: findPreviewUrls(doc, origin, detailUrl),
      detailUrl,
      source: "javdb",
      pageTitle: doc.title || "",
    };
  }

  function mergeUniqueUrls(primary, fallback) {
    const seen = new Set();
    const result = [];
    for (const url of [...(primary || []), ...(fallback || [])]) {
      const text = String(url || "").trim();
      if (!text || seen.has(text)) continue;
      seen.add(text);
      result.push(text);
    }
    return result;
  }

  function mergeMetadata(primary, fallback, extras) {
    const a = primary || {};
    const b = fallback || {};
    const pick = (key) => String(a[key] || b[key] || "").trim();
    return {
      code: pick("code") || String(extras?.code || "").trim(),
      title: pick("title"),
      releaseDate: pick("releaseDate"),
      duration: pick("duration"),
      director: pick("director"),
      studio: pick("studio") || pick("publisher"),
      series: pick("series"),
      categories: pick("categories"),
      actresses: pick("actresses"),
      rating: pick("rating"),
      coverUrl: String(a.coverUrl || b.coverUrl || "").trim(),
      previewUrls:
        Array.isArray(a.previewUrls) && a.previewUrls.length
          ? a.previewUrls
          : mergeUniqueUrls(a.previewUrls, b.previewUrls),
      detailUrl: String(extras?.detailUrl || a.detailUrl || "").trim(),
      javbusUrl: String(extras?.javbusUrl || b.detailUrl || "").trim(),
      source: [a.source, b.source].filter(Boolean).join("+") || "merged",
      pageTitle: pick("pageTitle"),
    };
  }

  function imageReferer(imageUrl, javdbUrl, javbusUrl) {
    const url = String(imageUrl || "").toLowerCase();
    if (url.includes("javbus") || url.includes("buscdn") || url.includes("dmm.co.jp")) {
      return javbusUrl || javdbUrl || "https://www.javbus.com/";
    }
    return javdbUrl || javbusUrl || imageUrl;
  }

  async function fetchDetailMetadata(pageUrl, origin) {
    const resp = await fetch(pageUrl, {
      credentials: "include",
      redirect: "follow",
      headers: { Accept: "text/html,application/xhtml+xml" },
    });
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    const html = await resp.text();
    const doc = new DOMParser().parseFromString(html, "text/html");
    return parseDetailDocument(doc, pageUrl, origin);
  }

  async function fetchImageBase64(imageUrl, referer) {
    const resp = await fetch(imageUrl, {
      credentials: "include",
      referrer: referer || imageUrl,
      headers: { Accept: "image/*,*/*" },
    });
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}`);
    }
    const buf = await resp.arrayBuffer();
    const bytes = new Uint8Array(buf);
    let binary = "";
    for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
    return btoa(binary);
  }

  globalThis.JM_metadataSync = {
    fetchDetailMetadata,
    parseDetailDocument,
    fetchImageBase64,
    mergeMetadata,
    imageReferer,
    normalizeCode,
    findDetailUrlFromSearchDocument,
  };
})();
