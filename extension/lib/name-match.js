/* global globalThis */
(function () {
  "use strict";

  const TRAD_TO_SIMP = {
    愛: "爱",
    學: "学",
    國: "国",
    馬: "马",
    長: "长",
    門: "门",
    開: "开",
    關: "关",
    東: "东",
    車: "车",
    書: "书",
    記: "记",
    話: "话",
    語: "语",
    說: "说",
    讀: "读",
    寫: "写",
    聽: "听",
    見: "见",
    覺: "觉",
    觀: "观",
    親: "亲",
    廣: "广",
    應: "应",
    頭: "头",
    無: "无",
    時: "时",
    會: "会",
    來: "来",
    個: "个",
    們: "们",
    這: "这",
    還: "还",
    過: "过",
    進: "进",
    遠: "远",
    邊: "边",
    裡: "里",
    後: "后",
    從: "从",
    電: "电",
    畫: "画",
    發: "发",
    經: "经",
    現: "现",
    業: "业",
    產: "产",
    動: "动",
    務: "务",
    員: "员",
    網: "网",
    聯: "联",
    聲: "声",
    與: "与",
    為: "为",
    韋: "韦",
    韓: "韩",
    萬: "万",
    華: "华",
    葉: "叶",
    榮: "荣",
    樹: "树",
    機: "机",
    歷: "历",
    壓: "压",
    縣: "县",
    顯: "显",
    陽: "阳",
    陰: "阴",
    雲: "云",
    電: "电",
    靈: "灵",
    麗: "丽",
    齊: "齐",
    龍: "龙",
    鳳: "凤",
    鳥: "鸟",
    魚: "鱼",
    貝: "贝",
    貴: "贵",
    賀: "贺",
    資: "资",
    賣: "卖",
    買: "买",
    紅: "红",
    純: "纯",
    細: "细",
    終: "终",
    結: "结",
    絕: "绝",
    統: "统",
    絲: "丝",
    綠: "绿",
    線: "线",
    練: "练",
    總: "总",
    繼: "继",
    續: "续",
    維: "维",
    羅: "罗",
    義: "义",
    習: "习",
    聖: "圣",
    聞: "闻",
    聰: "聪",
    職: "职",
    臉: "脸",
    興: "兴",
    舊: "旧",
    節: "节",
    藝: "艺",
    藥: "药",
    號: "号",
    衛: "卫",
    裝: "装",
    視: "视",
    覽: "览",
    計: "计",
    訂: "订",
    訓: "训",
    記: "记",
    許: "许",
    識: "识",
    調: "调",
    談: "谈",
    請: "请",
    謝: "谢",
    護: "护",
    負: "负",
    費: "费",
    貿: "贸",
    賓: "宾",
    賢: "贤",
    贊: "赞",
    軟: "软",
    輕: "轻",
    較: "较",
    輪: "轮",
    農: "农",
    適: "适",
    選: "选",
    遺: "遗",
    還: "还",
    邊: "边",
    郵: "邮",
    鄉: "乡",
    醫: "医",
    釋: "释",
    鋼: "钢",
    錄: "录",
    錢: "钱",
    鍵: "键",
    鐵: "铁",
    長: "长",
    開: "开",
    間: "间",
    閃: "闪",
    閉: "闭",
    開: "开",
    關: "关",
    陳: "陈",
    陸: "陆",
    險: "险",
    雙: "双",
    雜: "杂",
    離: "离",
    難: "难",
    雞: "鸡",
    電: "电",
    靜: "静",
    頂: "顶",
    順: "顺",
    預: "预",
    領: "领",
    頭: "头",
    題: "题",
    類: "类",
    額: "额",
    風: "风",
    飛: "飞",
    飯: "饭",
    飲: "饮",
    館: "馆",
    馬: "马",
    驗: "验",
    體: "体",
    髮: "发",
    鬥: "斗",
    魯: "鲁",
    鮮: "鲜",
    鳴: "鸣",
    黃: "黄",
    點: "点",
    黨: "党",
    齊: "齐",
    齒: "齿",
    龍: "龙",
    龜: "龟",
  };

  function toSimplified(text) {
    return String(text || "")
      .split("")
      .map((ch) => TRAD_TO_SIMP[ch] || ch)
      .join("");
  }

  function levenshtein(a, b) {
    if (a === b) return 0;
    if (!a.length) return b.length;
    if (!b.length) return a.length;
    const row = new Array(b.length + 1);
    for (let i = 0; i <= b.length; i++) row[i] = i;
    for (let i = 1; i <= a.length; i++) {
      let prev = i - 1;
      row[0] = i;
      for (let j = 1; j <= b.length; j++) {
        const temp = row[j];
        const cost = a[i - 1] === b[j - 1] ? 0 : 1;
        row[j] = Math.min(row[j] + 1, row[j - 1] + 1, prev + cost);
        prev = temp;
      }
    }
    return row[b.length];
  }

  function normalizeCjkKey(name) {
    let text = toSimplified(String(name || "").normalize("NFKC"));
    text = text.replace(/\([^)]*\)/g, " ").replace(/（[^）]*）/g, " ");
    text = text.replace(/[・·.．\-_/\\|]/g, "");
    text = text.replace(/\s+/g, "").toLowerCase();
    return text;
  }

  function normalizeEnglishName(name) {
    return String(name || "")
      .replace(/\([^)]*\)/g, " ")
      .replace(/（[^）]*）/g, " ")
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9\s]/gi, " ")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  function hasLatinLetters(text) {
    return /[a-z]/i.test(String(text || ""));
  }

  function englishNamesMatch(a, b) {
    const na = normalizeEnglishName(a);
    const nb = normalizeEnglishName(b);
    if (!na || !nb) return false;
    if (na === nb) return true;

    const compactA = na.replace(/\s/g, "");
    const compactB = nb.replace(/\s/g, "");
    if (compactA === compactB) return true;

    const tokensA = na.split(" ").filter(Boolean).sort().join("");
    const tokensB = nb.split(" ").filter(Boolean).sort().join("");
    if (tokensA === tokensB) return true;

    if (compactA.includes(compactB) || compactB.includes(compactA)) {
      return Math.min(compactA.length, compactB.length) >= 4;
    }

    if (compactA.length >= 4 && compactB.length >= 4) {
      const limit = Math.max(1, Math.floor(Math.min(compactA.length, compactB.length) * 0.18));
      if (levenshtein(compactA, compactB) <= limit) return true;
    }
    return false;
  }

  function namesMatch(a, b) {
    if (!a || !b) return false;
    const left = String(a).trim();
    const right = String(b).trim();
    if (!left || !right) return false;

    const cjkA = normalizeCjkKey(left);
    const cjkB = normalizeCjkKey(right);
    if (cjkA && cjkB) {
      if (cjkA === cjkB) return true;
      if (cjkA.includes(cjkB) || cjkB.includes(cjkA)) return true;
    }

    if (hasLatinLetters(left) || hasLatinLetters(right)) {
      if (englishNamesMatch(left, right)) return true;
    }

    return false;
  }

  function findBestNameMatch(target, entries, getName) {
    const list = Array.isArray(entries) ? entries : [];
    let exact = null;
    let fuzzy = null;

    for (const entry of list) {
      const name = getName(entry);
      if (!name) continue;
      if (namesMatch(target, name)) {
        if (normalizeCjkKey(target) === normalizeCjkKey(name) || normalizeEnglishName(target) === normalizeEnglishName(name)) {
          exact = entry;
          break;
        }
        if (!fuzzy) fuzzy = entry;
      }
    }
    return exact || fuzzy || null;
  }

  globalThis.JM_namesMatch = namesMatch;
  globalThis.JM_findBestNameMatch = findBestNameMatch;
  globalThis.JM_normalizeCjkKey = normalizeCjkKey;
})();
