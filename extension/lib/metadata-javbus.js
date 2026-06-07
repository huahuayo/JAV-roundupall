/* global globalThis */
(function () {
  "use strict";

  function normalizeCode(raw) {
    const text = String(raw || "").toUpperCase().trim();
    const match = text.match(/^([A-Z]+)-?(\d+[A-Z]?)$/);
    if (match) return `${match[1]}-${match[2]}`;
    return text;
  }

  function normalizeLabel(text) {
    return String(text || "")
      .replace(/[:：]\s*$/, "")
      .trim()
      .toLowerCase();
  }

  function resolveImageUrl(raw, origin) {
    const src = String(raw || "").trim();
    if (!src || /placeholder|default|avatar|loading|1px/i.test(src)) return "";
    try {
      return new URL(src, origin).href;
    } catch (_) {
      return "";
    }
  }

  function imageSrc(img) {
    if (!img) return "";
    return (
      img.getAttribute("data-src") ||
      img.getAttribute("data-original") ||
      img.getAttribute("src") ||
      ""
    );
  }

  function buildJavBusUrls(code) {
    const normalized = normalizeCode(code);
    if (!normalized) return [];
    const encoded = encodeURIComponent(normalized);
    return [
      `https://www.javbus.com/${encoded}`,
      `https://www.javbus.com/en/${encoded}`,
      `https://javbus.com/${encoded}`,
    ];
  }

  function collectActresses(doc) {
    const names = [];
    const seen = new Set();
    doc.querySelectorAll(".star-name a, #video_cast .star-name a, .avatar-box .photo-info span").forEach((node) => {
      const name = (node.textContent || "").trim();
      if (!name || seen.has(name)) return;
      seen.add(name);
      names.push(name);
    });
    return names.join("、");
  }

  function collectCategories(doc) {
    const names = [];
    const seen = new Set();
    doc.querySelectorAll(".genre a, #genre a, .info .genre a").forEach((node) => {
      const name = (node.textContent || "").trim();
      if (!name || seen.has(name)) return;
      seen.add(name);
      names.push(name);
    });
    return names.join("、");
  }

  function isBlockedPage(doc) {
    const title = String(doc.title || "").toLowerCase();
    const bodyText = String(doc.body?.innerText || "").slice(0, 1200).toLowerCase();
    if (/404|not found|页面不存在|頁面不存在|page not found/.test(title + bodyText)) {
      return true;
    }
    const hasCover = Boolean(
      doc.querySelector(".bigImage img, #video_jacket img, a.bigImage, h3")
    );
    const ageModal = doc.querySelector(
      "#warningModal.show, #warningModal.in, .modal-backdrop.in, .modal-backdrop.show"
    );
    if (ageModal && !hasCover) {
      return true;
    }
    return false;
  }

  function pickInfo(info, patterns) {
    for (const [label, value] of Object.entries(info)) {
      if (patterns.some((pattern) => pattern.test(label))) {
        return String(value || "").trim();
      }
    }
    return "";
  }

  function collectInfoMap(doc) {
    const map = {};
    doc.querySelectorAll(".info p").forEach((row) => {
      const header = row.querySelector("span.header, .header");
      const label = normalizeLabel(header?.textContent || "");
      if (!label) return;
      const links = Array.from(row.querySelectorAll("a"))
        .map((a) => (a.textContent || "").trim())
        .filter(Boolean);
      if (links.length) {
        map[label] = links.join("、");
        return;
      }
      let text = (row.textContent || "").trim();
      if (header) {
        text = text.replace(header.textContent || "", "").replace(/^[:：\s]+/, "").trim();
      }
      map[label] = text;
    });
    return map;
  }

  function findCoverUrl(doc, origin) {
    const selectors = ["#video_jacket img", ".bigImage img", ".screencap img", ".photo img", "a.bigImage img"];
    for (const sel of selectors) {
      const img = doc.querySelector(sel);
      const url = resolveImageUrl(imageSrc(img), origin);
      if (url) return url;
    }
    const bigImage = doc.querySelector("a.bigImage, .bigImage");
    if (bigImage) {
      const href = bigImage.getAttribute("href") || bigImage.href || "";
      if (href && !/javascript:/i.test(href)) {
        const resolved = resolveImageUrl(href, origin);
        if (resolved) return resolved;
      }
      const style = bigImage.getAttribute("style") || "";
      const bgMatch = style.match(/url\(['"]?([^'")]+)/i);
      if (bgMatch) {
        return resolveImageUrl(bgMatch[1], origin);
      }
    }
    const jacketLink = doc.querySelector("#video_jacket a[href]");
    if (jacketLink) {
      const href = jacketLink.getAttribute("href") || jacketLink.href || "";
      const resolved = resolveImageUrl(href, origin);
      if (resolved) return resolved;
    }
    const og = doc.querySelector('meta[property="og:image"]');
    if (og) {
      return resolveImageUrl(og.getAttribute("content"), origin);
    }
    return "";
  }

  function findPreviewUrls(doc, origin) {
    const urls = [];
    const seen = new Set();
    const pushUrl = (raw) => {
      const url = resolveImageUrl(raw, origin);
      if (!url || seen.has(url)) return;
      if (/avatar|logo|icon|1px|spacer/i.test(url)) return;
      seen.add(url);
      urls.push(url);
    };

    doc.querySelectorAll("#sample-waterfall .sample-box img, .sample-box img, .preview-thumb img").forEach((img) => {
      pushUrl(imageSrc(img));
    });

    doc.querySelectorAll("#sample-waterfall a.sample-box, a.sample-box").forEach((link) => {
      const href = link.getAttribute("href") || "";
      if (/\.(jpg|jpeg|png|webp)(\?|$)/i.test(href)) {
        pushUrl(href);
      }
      const img = link.querySelector("img");
      if (img) pushUrl(imageSrc(img));
    });

    return urls;
  }

  function parseJavBusDocument(doc, pageUrl, origin) {
    if (isBlockedPage(doc)) {
      return {
        code: "",
        title: "",
        coverUrl: "",
        previewUrls: [],
        detailUrl: pageUrl,
        source: "javbus",
        pageTitle: doc.title || "",
      };
    }

    const info = collectInfoMap(doc);
    const titleEl = doc.querySelector("h3");
    const title = (titleEl?.textContent || doc.title || "").trim();
    let code = pickInfo(info, [/识别码/, /識別碼/, /番号/, /番號/, /code/i]);
    if (!code) {
      const match = title.match(/^[A-Z0-9]+-[A-Z0-9]+/i);
      code = match ? normalizeCode(match[0]) : "";
    } else {
      code = normalizeCode(code);
    }

    const releaseDateRaw = pickInfo(info, [/发行日期/, /發行日期/, /日期/, /date/i]);
    const releaseMatch = releaseDateRaw.match(/\d{4}[-/.]\d{1,2}[-/.]\d{1,2}/);
    const releaseDate = releaseMatch ? releaseMatch[0].replace(/\//g, "-") : releaseDateRaw;

    let detailUrl = pageUrl;
    try {
      detailUrl = new URL(pageUrl, origin).href;
    } catch (_) {
      detailUrl = pageUrl;
    }

    return {
      code,
      title,
      releaseDate,
      duration: pickInfo(info, [/长度/, /長度/, /duration/i, /time/i]),
      director: pickInfo(info, [/导演/, /導演/, /director/i]),
      studio: pickInfo(info, [/制作/, /製作/, /maker/i, /studio/i, /label/i]),
      series: pickInfo(info, [/系列/, /series/i]),
      categories: pickInfo(info, [/类别/, /類別/, /genre/i, /tag/i]) || collectCategories(doc),
      actresses: pickInfo(info, [/演员/, /演員/, /actress/i, /star/i, /女优/, /女優/i]) || collectActresses(doc),
      publisher: pickInfo(info, [/发行/, /發行/, /publisher/i]),
      rating: "",
      coverUrl: findCoverUrl(doc, origin),
      previewUrls: findPreviewUrls(doc, origin),
      detailUrl,
      source: "javbus",
      pageTitle: doc.title || "",
    };
  }

  async function fetchJavBusMetadata(pageUrl, origin) {
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
    return parseJavBusDocument(doc, pageUrl, origin);
  }

  globalThis.JM_metadataJavbus = {
    buildJavBusUrls,
    parseJavBusDocument,
    fetchJavBusMetadata,
    normalizeCode,
  };
})();
