/*!
 * Voice Path v1.1.2 - Conversation Memory (IndexedDB - 7 day raw / 30 day summary)
 * Sophie remembers across days - opening can use yesterday promise / mood
 * spec: docs/v1.1.2-memory-continuity-spec.md
 *
 * Privacy:
 *   - raw transcript only in browser IndexedDB (not on backend)
 *   - backend /memory/summarize is stateless (Claude Haiku - no log raw unless DEBUG_MEMORY=1)
 *   - raw turns 7 day TTL / summaries 30 day TTL / cleanup auto purge
 *   - Sally 6yo redline inherited (subject_guard at prompt layer)
 *   - Edward purge = chrome devtools > Application > IndexedDB > sophie-memory-v1 > Delete database
 *
 * ES5 only - auth gate auto via fetch cookie credentials
 */
(function (global) {
  "use strict";

  var DB_NAME = "sophie-memory-v1";
  var DB_VERSION = 1;
  var STORE_CONV = "conversations";
  var STORE_SUM = "summaries";

  var TTL_CONV_DAYS = 7;
  var TTL_SUM_DAYS = 30;
  var DAY_MS = 24 * 60 * 60 * 1000;

  function _openDB() {
    return new Promise(function (resolve, reject) {
      if (!global.indexedDB) {
        reject(new Error("IndexedDB not supported"));
        return;
      }
      var req = global.indexedDB.open(DB_NAME, DB_VERSION);
      req.onupgradeneeded = function (e) {
        var db = e.target.result;
        if (!db.objectStoreNames.contains(STORE_CONV)) {
          var convStore = db.createObjectStore(STORE_CONV, { keyPath: "sessionId" });
          convStore.createIndex("timestamp", "timestamp", { unique: false });
          convStore.createIndex("date", "date", { unique: false });
        }
        if (!db.objectStoreNames.contains(STORE_SUM)) {
          db.createObjectStore(STORE_SUM, { keyPath: "date" });
        }
      };
      req.onsuccess = function (e) { resolve(e.target.result); };
      req.onerror = function (e) { reject(e.target.error || new Error("openDB error")); };
    });
  }

  function _todayStr() {
    var d = new Date();
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1);
    if (m.length < 2) m = "0" + m;
    var day = String(d.getDate());
    if (day.length < 2) day = "0" + day;
    return y + "-" + m + "-" + day;
  }

  function _dateNDaysAgo(n) {
    var d = new Date(Date.now() - n * DAY_MS);
    var y = d.getFullYear();
    var m = String(d.getMonth() + 1);
    if (m.length < 2) m = "0" + m;
    var day = String(d.getDate());
    if (day.length < 2) day = "0" + day;
    return y + "-" + m + "-" + day;
  }

  function _withStore(storeName, mode, fn) {
    return _openDB().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(storeName, mode);
        var store = tx.objectStore(storeName);
        var inner;
        try {
          inner = fn(store);
        } catch (e) {
          reject(e);
          return;
        }
        tx.oncomplete = function () { resolve(inner); };
        tx.onerror = function () { reject(tx.error || new Error("tx error")); };
        tx.onabort = function () { reject(tx.error || new Error("tx abort")); };
      }).then(function (r) {
        try { db.close(); } catch (e2) {}
        return r;
      })["catch"](function (err) {
        try { db.close(); } catch (e2) {}
        throw err;
      });
    });
  }

  function _getOrInitConv(store, sessionId) {
    return new Promise(function (resolve, reject) {
      var req = store.get(sessionId);
      req.onsuccess = function () {
        resolve(req.result || {
          sessionId: sessionId,
          timestamp: Date.now(),
          date: _todayStr(),
          turns: []
        });
      };
      req.onerror = function () { reject(req.error || new Error("get conv error")); };
    });
  }

  function recordTurn(sessionId, role, text) {
    if (!sessionId || typeof text !== "string" || !text.trim()) {
      return Promise.resolve(null);
    }
    if (role !== "user" && role !== "sophie") {
      return Promise.resolve(null);
    }
    var safeText = text.length > 500 ? text.slice(0, 500) : text;
    return _withStore(STORE_CONV, "readwrite", function (store) {
      _getOrInitConv(store, sessionId).then(function (rec) {
        rec.turns.push({ role: role, text: safeText, t: Date.now() });
        if (rec.turns.length > 200) {
          rec.turns = rec.turns.slice(-200);
        }
        rec.timestamp = Date.now();
        store.put(rec);
      });
    })["catch"](function (err) {
      try { console.warn("[convMemory] recordTurn fail:", err && err.message); } catch (e) {}
      return null;
    });
  }

  function _collectTurnsForDate(date) {
    return _withStore(STORE_CONV, "readonly", function (store) {
      return new Promise(function (resolve, reject) {
        var all = [];
        var idx = store.index("date");
        var req = idx.openCursor(IDBKeyRange.only(date));
        req.onsuccess = function (e) {
          var cursor = e.target.result;
          if (cursor) {
            var rec = cursor.value;
            if (rec && rec.turns && rec.turns.length) {
              for (var i = 0; i < rec.turns.length; i++) {
                all.push(rec.turns[i]);
              }
            }
            cursor["continue"]();
          } else {
            resolve(all);
          }
        };
        req.onerror = function () { reject(req.error || new Error("cursor error")); };
      }).then(function (arr) {
        arr.sort(function (a, b) { return (a.t || 0) - (b.t || 0); });
        return arr;
      });
    });
  }

  function summarizeDay(date) {
    var d = date || _todayStr();
    return _collectTurnsForDate(d).then(function (turns) {
      if (!turns || turns.length < 2) {
        return null;
      }
      var send = turns.length > 30 ? turns.slice(-30) : turns;
      return fetch("/memory/summarize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ turns: send.map(function (t) {
          return { role: t.role, text: t.text };
        })})
      }).then(function (r) {
        if (!r.ok) {
          throw new Error("summarize HTTP " + r.status);
        }
        return r.json();
      }).then(function (j) {
        if (!j || typeof j.summary !== "string") {
          return null;
        }
        var record = {
          date: d,
          summary: j.summary || "",
          mood: j.mood || "neutral",
          promises: Array.isArray(j.promises) ? j.promises : [],
          ts: Date.now()
        };
        return _withStore(STORE_SUM, "readwrite", function (store) {
          store.put(record);
        }).then(function () {
          try { console.log("[convMemory] summary stored:", d, record.mood, record.promises.length); } catch (e) {}
          return record;
        });
      });
    })["catch"](function (err) {
      try { console.warn("[convMemory] summarizeDay fail:", err && err.message); } catch (e) {}
      return null;
    });
  }

  function getRecentSummaries(daysBack) {
    var n = daysBack || 7;
    return _withStore(STORE_SUM, "readonly", function (store) {
      return new Promise(function (resolve, reject) {
        var results = [];
        var req = store.openCursor();
        req.onsuccess = function (e) {
          var cursor = e.target.result;
          if (cursor) {
            results.push(cursor.value);
            cursor["continue"]();
          } else {
            results.sort(function (a, b) {
              if (a.date < b.date) return 1;
              if (a.date > b.date) return -1;
              return 0;
            });
            resolve(results.slice(0, n));
          }
        };
        req.onerror = function () { reject(req.error || new Error("summaries cursor error")); };
      });
    })["catch"](function (err) {
      try { console.warn("[convMemory] getRecentSummaries fail:", err && err.message); } catch (e) {}
      return [];
    });
  }

  function cleanup() {
    var convCutoff = Date.now() - (TTL_CONV_DAYS * DAY_MS);
    var sumCutoff = _dateNDaysAgo(TTL_SUM_DAYS);
    var p1 = _withStore(STORE_CONV, "readwrite", function (store) {
      var idx = store.index("timestamp");
      var req = idx.openCursor(IDBKeyRange.upperBound(convCutoff));
      req.onsuccess = function (e) {
        var cursor = e.target.result;
        if (cursor) {
          cursor["delete"]();
          cursor["continue"]();
        }
      };
    })["catch"](function (err) {
      try { console.warn("[convMemory] cleanup conv fail:", err && err.message); } catch (e) {}
    });
    var p2 = _withStore(STORE_SUM, "readwrite", function (store) {
      var req = store.openCursor();
      req.onsuccess = function (e) {
        var cursor = e.target.result;
        if (cursor) {
          if (cursor.value && cursor.value.date && cursor.value.date < sumCutoff) {
            cursor["delete"]();
          }
          cursor["continue"]();
        }
      };
    })["catch"](function (err) {
      try { console.warn("[convMemory] cleanup sum fail:", err && err.message); } catch (e) {}
    });
    return Promise.all([p1, p2]);
  }

  global.ConversationMemory = {
    recordTurn: recordTurn,
    summarizeDay: summarizeDay,
    getRecentSummaries: getRecentSummaries,
    cleanup: cleanup,
    todayStr: _todayStr,
    DB_NAME: DB_NAME,
    DB_VERSION: DB_VERSION
  };
})(window);
