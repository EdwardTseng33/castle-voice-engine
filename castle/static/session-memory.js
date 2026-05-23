/*!
 * Voice Path v1.1.1 · Session Memory (localStorage-only)
 * 蘇菲歷史感知 · 不存對話 / 不存音訊 / 不存個資
 * spec: docs/v1.1.1-ambient-awareness-spec.md
 * ES5 only · 不依賴後端 / 不踩 OAuth
 */
(function (global) {
  "use strict";

  var SESSION_KEY = "sophie_session_v1";

  function readSessionMemory() {
    try {
      var raw = localStorage.getItem(SESSION_KEY);
      if (!raw) {
        return { lastVisit: null, totalSessions: 0, lastGreeting: null };
      }
      var parsed = JSON.parse(raw);
      // 反序列化 ISO 字串 → Date
      if (parsed.lastVisit) {
        var d = new Date(parsed.lastVisit);
        // invalid date 防呆 (清除掉)
        parsed.lastVisit = isNaN(d.getTime()) ? null : d;
      } else {
        parsed.lastVisit = null;
      }
      if (typeof parsed.totalSessions !== "number" || parsed.totalSessions < 0) {
        parsed.totalSessions = 0;
      }
      if (typeof parsed.lastGreeting !== "string") {
        parsed.lastGreeting = null;
      }
      return parsed;
    } catch (e) {
      // localStorage 不可用 / quota / parse 失敗 → 全當首訪
      try { console.warn("[sessionMemory] read fail:", e && e.message); } catch (e2) {}
      return { lastVisit: null, totalSessions: 0, lastGreeting: null };
    }
  }

  function writeSessionMemory(greeting) {
    try {
      var prev = readSessionMemory();
      var data = {
        lastVisit: new Date().toISOString(),
        totalSessions: (prev.totalSessions || 0) + 1,
        lastGreeting: typeof greeting === "string" ? greeting : null
      };
      localStorage.setItem(SESSION_KEY, JSON.stringify(data));
      return data;
    } catch (e) {
      try { console.warn("[sessionMemory] write fail:", e && e.message); } catch (e2) {}
      return null;
    }
  }

  // 工具：算 last visit 跟現在差距（分鐘）· null = 首訪
  function minutesSinceLastVisit(memory) {
    if (!memory || !memory.lastVisit) return null;
    var now = new Date();
    return (now.getTime() - memory.lastVisit.getTime()) / 1000 / 60;
  }

  // public API
  global.SessionMemory = {
    read: readSessionMemory,
    write: writeSessionMemory,
    minutesSinceLastVisit: minutesSinceLastVisit,
    KEY: SESSION_KEY
  };
})(window);
