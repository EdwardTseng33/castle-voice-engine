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
    if (!nt) return null;
    // v1.5.0b · 太短的對話片段直接走「完全相等」path · 不走 Levenshtein
    // (「我懂」這類 2 字 phrase 之前被誤過濾)
    if (nt.length < 3) {
      for (var k = 0; k < MANIFEST.phrases.length; k++) {
        if ((MANIFEST.phrases[k]._normalized || _normalize(MANIFEST.phrases[k].sentence)) === nt) {
          return { phrase: MANIFEST.phrases[k], distance: 0, ratio: 0 };
        }
      }
      return null;
    }

    var best = null;
    var bestDist = Infinity;
    var bestRatio = Infinity;

    // v1.9.14 · 霍爾刀 5 · 三層匹配 · 短句 early hit + 長句 prefix + substring
    for (var i = 0; i < MANIFEST.phrases.length; i++) {
      var p = MANIFEST.phrases[i];
      var ns = p._normalized || _normalize(p.sentence);

      // 1. 完整比 (原邏輯) · 整段 Levenshtein
      var lenRatio = Math.abs(ns.length - nt.length) / Math.max(ns.length, nt.length);
      if (lenRatio <= 0.4) {
        var d = _levenshtein(nt, ns);
        var ratio = d / Math.max(nt.length, ns.length);
        if (ratio < 0.30 && d < bestDist) {
          best = p; bestDist = d; bestRatio = ratio;
        }
      }

      // 2. buffer 起手 X 字 vs phrase 整段 (蘇菲剛開口時用)
      if (nt.length >= ns.length) {
        var nt_prefix = nt.substring(0, ns.length);
        var dp = _levenshtein(nt_prefix, ns);
        var ratiop = dp / ns.length;
        if (ratiop < 0.30 && dp < bestDist) {
          best = p; bestDist = dp; bestRatio = ratiop;
        }
      }

      // 3. v1.9.14 · 真 early prefix · buffer 還沒長到 phrase 長度時、用兩端較短長度比
      // 例如 buffer = "我懂你" (3 字) vs phrase = "我懂" (2 字) · 取 buffer 前 2 字 "我懂" vs phrase "我懂" = 完美 match
      // 或 buffer = "早安 Ed" (5 字) vs phrase = "早安 Edward 新的一天" (12 字) · 取兩邊前 5 字比
      if (nt.length >= 2 && ns.length >= 2) {
        var shortLen = Math.min(nt.length, ns.length);
        var nt_head = nt.substring(0, shortLen);
        var ns_head = ns.substring(0, shortLen);
        var de = _levenshtein(nt_head, ns_head);
        var ratioe = de / shortLen;
        // 只在 shortLen 夠長 (≥ 2) 且 ratio 嚴格 (< 0.20) 才算命中 · 避免亂 match
        if (shortLen >= 2 && ratioe < 0.20 && de < bestDist) {
          best = p; bestDist = de; bestRatio = ratioe;
        }
      }

      // 4. v1.9.14 · substring · buffer 內任何位置含 phrase
      if (nt.length > ns.length && nt.indexOf(ns) !== -1) {
        if (0 < bestDist) {
          best = p; bestDist = 0; bestRatio = 0;
        }
      }
    }
    if (best) {
      try { console.log("[PhraseMatcher] HIT · " + best.sentence + " · ratio=" + bestRatio.toFixed(2) + " · buffer=" + nt.slice(0, 40)); } catch (e) {}
    }
    return best ? { phrase: best, distance: bestDist, ratio: bestRatio } : null;
  }

  function manifestInfo() {
    if (!MANIFEST) return { loaded: false, total: 0 };
    return { loaded: true, total: (MANIFEST.phrases || []).length };
  }

  // v2.0.42 · 暴露 phrases 給 preroll greeting 用
  function listPhrases() {
    return (MANIFEST && MANIFEST.phrases) ? MANIFEST.phrases.slice() : [];
  }

  // v0.4.x · 意思向量比對 (取代 Levenshtein 字面比對 · 透過後端 /lipsync/match)
  // 用法: ?semantic=1 啟動 · 觸發走 findMatchingSemantic() 取代 findMatching()
  // 回傳 promise → { phrase, distance: null, ratio: 1 - score, score, semantic } 或 null

  var _semCache = {};
  var _semCacheKeys = [];
  var _SEM_CACHE_MAX = 200;
  var _inflightKey = null;
  var _inflightPromise = null;

  function _semCachePut(key, val) {
    _semCache[key] = val;
    _semCacheKeys.push(key);
    while (_semCacheKeys.length > _SEM_CACHE_MAX) {
      var old = _semCacheKeys.shift();
      delete _semCache[old];
    }
  }

  function findMatchingSemantic(text) {
    if (!text || typeof text !== "string") return Promise.resolve(null);
    var nt = _normalize(text);
    if (!nt) return Promise.resolve(null);
    if (Object.prototype.hasOwnProperty.call(_semCache, nt)) {
      return Promise.resolve(_semCache[nt]);
    }
    if (_inflightKey === nt && _inflightPromise) return _inflightPromise;
    _inflightKey = nt;
    _inflightPromise = fetch("/lipsync/match", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ text: text }),
    })
      .then(function (r) {
        if (!r.ok) return null;
        return r.json();
      })
      .then(function (data) {
        if (!data || !data.ok || !data.match) {
          _semCachePut(nt, null);
          return null;
        }
        var matchPhrase = null;
        if (MANIFEST && MANIFEST.phrases) {
          for (var i = 0; i < MANIFEST.phrases.length; i++) {
            if (MANIFEST.phrases[i].phrase_id === data.match.phrase_id) {
              matchPhrase = MANIFEST.phrases[i];
              break;
            }
          }
        }
        if (!matchPhrase) {
          matchPhrase = {
            phrase_id: data.match.phrase_id,
            sentence: data.match.sentence,
            mp4_url: data.match.mp4_url,
          };
        }
        var out = {
          phrase: matchPhrase,
          distance: null,
          ratio: 1 - data.match.score,
          score: data.match.score,
          semantic: true,
        };
        _semCachePut(nt, out);
        try {
          console.log("[PhraseMatcher.semantic] HIT · " + matchPhrase.sentence +
            " · score=" + data.match.score.toFixed(3) + " · buffer=" + nt.slice(0, 40));
        } catch (e) {}
        return out;
      })
      .catch(function (e) {
        try { console.warn("[PhraseMatcher.semantic] fail:", e.message); } catch (_) {}
        return null;
      })
      .finally(function () {
        if (_inflightKey === nt) {
          _inflightKey = null;
          _inflightPromise = null;
        }
      });
    return _inflightPromise;
  }

  global.PhraseMatcher = {
    init: init,
    findMatching: findMatching,
    findMatchingSemantic: findMatchingSemantic,
    manifestInfo: manifestInfo,
    listPhrases: listPhrases,
  };
})(window);
