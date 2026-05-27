/**
 * castle-voice-engine / castle/static/viseme-engine.js
 * (c) 2026 Edward / BeyondPath · viseme-poc-v0.1
 *
 * 業界輕量 lipsync · 跟 Duix / Tavus / HeyGen 同款路線 (非 neural · CPU 即可)
 * Edward 5/27 拍板「以 Duix 為標竿、走業界輕量路線」
 *
 * 核心邏輯:
 *   1. OpenAI Realtime audio_transcript.delta 流給文字
 *   2. 拆字 → 對應中文音節 → 選 viseme id (0-7)
 *   3. 排隊切換 visemeOverlay 元素的 src/style
 *   4. 平均每 180-220ms 一個音節 (中文語速)
 *
 * Feature flag: window.__sophieVisemeEnabled = true (預設 false · ?viseme=1 啟動)
 *
 * 8 形 viseme map (簡化版 · Disney 業界共識):
 *   V0 rest    閉嘴
 *   V1 i       微開橫嘴 (i / y)
 *   V2 e       半張扁嘴 (e / ei)
 *   V3 a       大開嘴 (a / ai / ao)
 *   V4 o       圓嘴 (o / ou)
 *   V5 u       撅嘴 (u / ü)
 *   V6 f       咬唇 (f / w)
 *   V7 smile   微笑閉嘴 (短停頓)
 */

(function (global) {
  "use strict";

  // ---------- 中文聲母 / 韻母 → viseme 對照 ----------
  // 注音 / 拼音兼容簡化版 · 以「韻母」決定嘴形 (聲母影響輕)
  var VOWEL_TO_VISEME = {
    // V3 大開 (a 系)
    "a": 3, "ā": 3, "á": 3, "ǎ": 3, "à": 3,
    "ai": 3, "ao": 3, "an": 3, "ang": 3,
    // V2 半張 (e 系)
    "e": 2, "ē": 2, "é": 2, "ě": 2, "è": 2,
    "ei": 2, "en": 2, "eng": 2, "er": 2,
    // V1 微開橫 (i 系)
    "i": 1, "ī": 1, "í": 1, "ǐ": 1, "ì": 1,
    "in": 1, "ing": 1,
    // V4 圓嘴 (o 系)
    "o": 4, "ō": 4, "ó": 4, "ǒ": 4, "ò": 4,
    "ou": 4, "ong": 4,
    // V5 撅嘴 (u 系)
    "u": 5, "ū": 5, "ú": 5, "ǔ": 5, "ù": 5,
    "un": 5, "ü": 5, "uan": 5
  };

  // 聲母含 f / w 的字 · 蓋過韻母對映用 V6
  var INITIAL_F_W = ["f", "w"];

  // ---------- 中文字 → 韻母粗估 ----------
  // 不做完整拼音轉換 (太重) · 用「常用字 → 主要嘴形」對照
  // 命中常用字 ~ 70% · 沒命中走 fallback (V7 smile)
  var COMMON_CHAR_VISEME = {
    // V0 rest (m/b/p/n 系)
    "嗎": 0, "媽": 0, "麻": 0, "馬": 0, "罵": 0,
    "把": 0, "爸": 0, "吧": 0, "白": 0,
    "拍": 0, "怕": 0, "排": 0,
    "你": 1, "那": 3, "拿": 3, "哪": 3,
    // V1 i (i / y 系)
    "一": 1, "已": 1, "意": 1, "義": 1, "以": 1, "易": 1,
    "你": 1, "妳": 1, "比": 1, "幾": 1, "機": 1, "級": 1,
    "字": 1, "次": 1, "私": 1, "思": 1, "詩": 1, "事": 1,
    "知": 1, "之": 1, "支": 1, "吃": 1, "持": 1, "尺": 1,
    "希": 1, "西": 1, "細": 1, "起": 1,
    // V2 e (e / ei)
    "了": 2, "可": 2, "課": 2, "和": 2, "喝": 2,
    "個": 2, "得": 2, "德": 2,
    "誰": 2, "說": 2, "色": 2, "瑟": 2,
    "黑": 2, "給": 2, "累": 2, "美": 2,
    // V3 a (a / ai / ao / an / ang)
    "啊": 3, "阿": 3, "愛": 3, "哎": 3, "矮": 3, "唉": 3,
    "敖": 3, "好": 3, "號": 3, "高": 3, "告": 3, "教": 3,
    "安": 3, "案": 3, "暗": 3, "按": 3,
    "幫": 3, "上": 3, "想": 3, "上": 3, "讓": 3, "樣": 3, "養": 3,
    "下": 3, "蝦": 3, "夏": 3,
    "他": 3, "她": 3, "它": 3, "打": 3, "大": 3,
    "看": 3, "開": 3, "凱": 3,
    "來": 3, "賴": 3, "拉": 3, "啦": 3,
    "再": 3, "在": 3, "做": 3, "走": 3, "找": 3, "早": 3,
    // V4 o (o / ou / ong)
    "我": 4, "哦": 4, "噢": 4, "歐": 4, "藕": 4,
    "口": 4, "口": 4, "後": 4, "頭": 4, "肉": 4,
    "送": 4, "中": 4, "通": 4, "東": 4, "公": 4, "工": 4,
    "夢": 4, "從": 4,
    "謝": 1, "些": 1,
    // V5 u (u / ü)
    "不": 5, "布": 5, "步": 5, "簿": 5, "部": 5,
    "出": 5, "處": 5, "初": 5, "除": 5,
    "魚": 5, "雨": 5, "與": 5, "玉": 5, "於": 5, "餘": 5,
    "去": 5, "區": 5, "屈": 5,
    "苦": 5, "哭": 5, "庫": 5, "酷": 5,
    "路": 5, "陸": 5, "錄": 5, "綠": 5,
    "做": 5, "祖": 5,
    "怎": 2, "麼": 4,
    "什": 2,
    // V6 f / w
    "我": 4, "問": 4, "玩": 3, "晚": 3, "完": 3, "萬": 3, "外": 3,
    "夫": 6, "服": 6, "服": 6, "府": 6, "父": 6, "復": 6, "副": 6,
    "風": 6, "封": 6, "豐": 6, "馮": 6,
    "飯": 6, "翻": 6, "煩": 6, "凡": 6,
    "為": 4, "微": 1, "未": 1, "唯": 1
  };

  // ---------- public API ----------
  var ViseseEngine = {
    /**
     * 把一個中文字轉成 viseme id
     * @param {string} ch 單一字符
     * @returns {number} 0-7
     */
    charToViseme: function (ch) {
      if (!ch) return 0;
      // 常用字直接查表
      if (COMMON_CHAR_VISEME.hasOwnProperty(ch)) {
        return COMMON_CHAR_VISEME[ch];
      }
      // 標點 / 空白 → V0 rest
      if (/[\s,。、!?？！，；：「」『』（）()…]/.test(ch)) return 0;
      // 英文字母 → fallback 看母音
      var lower = ch.toLowerCase();
      if (VOWEL_TO_VISEME.hasOwnProperty(lower)) return VOWEL_TO_VISEME[lower];
      // f / w 開頭 fallback
      // ASCII a-z 用粗估
      if (/[aeiouy]/.test(lower)) {
        if (lower === "a") return 3;
        if (lower === "e") return 2;
        if (lower === "i" || lower === "y") return 1;
        if (lower === "o") return 4;
        if (lower === "u") return 5;
      }
      // 沒命中 → V7 (微笑、短停頓間隔)
      return 7;
    },

    /**
     * 把字串轉 viseme 序列
     * @param {string} text 一段中文 / 英文混合
     * @returns {Array<number>} viseme ids
     */
    textToVisemes: function (text) {
      if (!text) return [];
      var out = [];
      for (var i = 0; i < text.length; i++) {
        out.push(ViseseEngine.charToViseme(text.charAt(i)));
      }
      return out;
    },

    /**
     * 排隊把 viseme 序列依時間切換到 DOM
     * @param {Array<number>} visemes
     * @param {number} msPerViseme · 每個 viseme 持續毫秒 (預設 200ms · 中文每秒 4-5 字)
     * @param {function(number, number)} onTick · (visemeId, index) 切換時呼叫 · 用於改 DOM
     */
    scheduleVisemes: function (visemes, msPerViseme, onTick) {
      var ms = msPerViseme || 200;
      var timers = [];
      for (var i = 0; i < visemes.length; i++) {
        (function (vid, idx) {
          var t = setTimeout(function () {
            try { onTick(vid, idx); } catch (e) {}
          }, idx * ms);
          timers.push(t);
        })(visemes[i], i);
      }
      // 序列結束後回 rest
      var endT = setTimeout(function () {
        try { onTick(0, visemes.length); } catch (e) {}
      }, visemes.length * ms);
      timers.push(endT);
      return {
        cancel: function () {
          for (var k = 0; k < timers.length; k++) clearTimeout(timers[k]);
        }
      };
    },

    /**
     * Init: 檢查 feature flag · 預設 off
     * @returns {boolean}
     */
    isEnabled: function () {
      // URL param ?viseme=1 開
      try {
        var qs = new URLSearchParams(global.location.search);
        if (qs.get("viseme") === "1") {
          global.__sophieVisemeEnabled = true;
          return true;
        }
      } catch (e) {}
      return global.__sophieVisemeEnabled === true;
    },

    VISEME_COUNT: 8,
    VISEME_NAMES: ["rest", "i", "e", "a", "o", "u", "f", "smile"],

    /**
     * 取得 viseme 對應的 mp4 url (predefined naming)
     */
    visemeUrl: function (id) {
      return "/static/sophie-viseme-" + id + ".mp4";
    },
  };

  global.ViseseEngine = ViseseEngine;
  global.VisemeEngine = ViseseEngine;  // alias · 修常見 typo
})(window);
