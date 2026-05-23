// castle/static/phrase-matcher.js
// v1.5.0 · 蘇菲嘴對齊預錄 mp4 fuzzy match
//
// 流程:
// 1. init() · 載入 /lipsync/manifest.json
// 2. GPT realtime stream transcript delta 累積到 5+ 字
// 3. findMatching(text) · Levenshtein distance / max_len < 0.30 命中
// 4. 命中 → return phrase 物件 · 含 mp4_url + sentence
// 5. caller (index.html dc message handler) 把 video.src 切到 mp4_url + muted
// 6. audio 維持 GPT realtime · 視覺上嘴跟著預錄嘴型動 (大致對齊 · fuzzy match 命中保證內容相近)

(function (global) {
  var MANIFEST = null;
  var LOAD_PROMISE = null;

  function _normalize(s) {
    if (!s || typeof s !== "string") return "";
    // 砍標點 + 空白 + 轉小寫 · 避免標點影響 match
    return s.replace(/[，。！？、・·~～\s\!\?\.\,\:\;]/g, "").toLowerCase();
  }

  function _levenshtein(a, b) {
    if (a === b) return 0;
    var m = a.length, n = b.length;
    if (m === 0) return n;
    if (n === 0) return m;
    var prev = new Array(n + 1);
    var curr = new Array(n + 1);
    for (var j = 0; j <= n; j++) prev[j] = j;
    for (var i = 1; i <= m; i++) {
      curr[0] = i;
      for (var jj = 1; jj <= n; jj++) {
        var cost = a.charCodeAt(i - 1) === b.charCodeAt(jj - 1) ? 0 : 1;
        curr[jj] = Math.min(curr[jj - 1] + 1, prev[jj] + 1, prev[jj - 1] + cost);
      }
      var t = prev; prev = curr; curr = t;
    }
    return prev[n];
  }

  function init() {
    if (LOAD_PROMISE) return LOAD_PROMISE;
    LOAD_PROMISE = fetch("/lipsync/manifest.json", { cache: "no-store" })
      .then(function (r) {
        if (!r.ok) return { phrases: [] };
        return r.json();
      })
      .then(function (data) {
        MANIFEST = data;
        // 預先 _normalize 所有 sentence 存進 manifest entry
        if (MANIFEST && MANIFEST.phrases) {
          MANIFEST.phrases.forEach(function (p) {
            p._normalized = _normalize(p.sentence);
          });
        }
        console.log("[PhraseMatcher] manifest loaded · " + (MANIFEST.phrases ? MANIFEST.phrases.length : 0) + " phrases");
        return MANIFEST;
      })
      .catch(function (e) {
        console.warn("[PhraseMatcher] manifest load fail:", e.message);
        MANIFEST = { phrases: [] };
        return MANIFEST;
      });
    return LOAD_PROMISE;
  }

  // text = GPT 正在講的話 (累積中的 transcript)
  // 回 { phrase, distance, ratio } 或 null
  function findMatching(text) {
    if (!MANIFEST || !MANIFEST.phrases || MANIFEST.phrases.length === 0) return null;
    var nt = _normalize(text);
    if (!nt || nt.length < 3) return null;  // 太短不 match · 避免誤觸

    var best = null;
    var bestDist = Infinity;
    var bestRatio = Infinity;

    for (var i = 0; i < MANIFEST.phrases.length; i++) {
      var p = MANIFEST.phrases[i];
      var ns = p._normalized || _normalize(p.sentence);
      // 快速 reject · 長度差距 > 40% 不算 match
      var lenRatio = Math.abs(ns.length - nt.length) / Math.max(ns.length, nt.length);
      if (lenRatio > 0.4) continue;
      var d = _levenshtein(nt, ns);
      var ratio = d / Math.max(nt.length, ns.length);
      if (ratio < 0.30 && d < bestDist) {
        best = p;
        bestDist = d;
        bestRatio = ratio;
      }
    }
    return best ? { phrase: best, distance: bestDist, ratio: bestRatio } : null;
  }

  function manifestInfo() {
    if (!MANIFEST) return { loaded: false, total: 0 };
    return { loaded: true, total: (MANIFEST.phrases || []).length };
  }

  global.PhraseMatcher = {
    init: init,
    findMatching: findMatching,
    manifestInfo: manifestInfo,
  };
})(window);
