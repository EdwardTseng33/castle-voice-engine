/*!
 * Voice Path v2.0.32-mobile-perf-safe-fix (calcifer 2026-05-29 · 手機卡頓安全效能修 · 桌面不變)
 * base: v2.0.16-revert-talking-idle · idle 嘴閉 · 講話切 sophie-speaking 上層
 * Edward 2026-05-25 21:36 catch: v2.0.14/15 方向反了 · idle 應該嘴閉 · 講話才嘴動
 * Phase C 真實價值保留:pre-call rotator flag + is-rotating opacity 1 + idle rotator 30-60s
 * 砍:in-call queue 7-10s + postSpeakWatcher (對話期間切 idle = 反向錯誤)
 * ES5 only
 */
(function (global) {
  "use strict";

  var ANIMATION_POOL = {
    "idle": "/static/sophie-idle.mp4",
    "idle-2": "/static/sophie-idle-2.mp4",
    "idle-3": "/static/sophie-idle-3.mp4",
    "idle-4": "/static/sophie-idle-4.mp4",
    "stroke-hair": "/static/sophie-stroke-hair.mp4",
    /* v1.9.13 · 霍爾 verdict 加回 speaking fallback · 沒命中 lipsync 時用 · 蘇菲講話有動感不凍結 */
    "speaking": "/static/sophie-speaking.mp4",
    "task-received": "/static/sophie-task-received.mp4",
    "task-handoff": "/static/sophie-task-handoff.mp4",
    "happy": "/static/sophie-happy.mp4",
    "acknowledgement": "/static/sophie-acknowledgement.mp4",
    "apologetic": "/static/sophie-apologetic.mp4",
    "resigned": "/static/sophie-resigned.mp4",
    "greeting": "/static/sophie-greeting.mp4",
    "playful": "/static/sophie-playful.mp4",
    "intimate-greeting": "/static/sophie-intimate-greeting.mp4",
    "intimate-farewell": "/static/sophie-intimate-farewell.mp4"
  };

  var IDLE_VARIANTS = ["idle", "idle-2", "idle-3", "idle-4"];
  var GESTURE_INSERT_PROB = 0.12;
  // v1.1.3 - absent-state idle slowdown + gesture bias
  var ABSENT_IDLE_INTERVAL_MS = 20000;  // 20s rotator interval when Edward absent
  var ABSENT_GESTURE_PROB = 0.12;       // 12% stroke-hair when absent (waiting feel)
  var ABSENT_THRESHOLD_S = 10;          // absent >= 10s before slowdown kicks in
  var GREETED_KEY = "sophie_first_greeting_done";
  var GREETED_TTL_MS = 24 * 60 * 60 * 1000;
  var HIGH_PRIORITY = { "task-handoff": 1, "intimate-farewell": 1 };

  // v2.0.32 (2026-05-29 calcifer mobile-perf-safe-fix) - pure detect - zero side effect - revertible
  // root cause (Chrome MCP console evidence):
  //   #1 open-page preload 15 large mp4 (5-8MB each) -> mobile 95MB + 15 retained in memory
  //   #2 pre-call(14-22s) + idle rotator(30-60s) two timers fight same video -> play() interrupted x7
  //   #3 coldstart watchdog races rotation - nudge #1-4 all give up - waste re-fetch 4 large mp4
  // mobile strategy: preload only idle - longer rotation interval - preload=metadata not full - desktop unchanged
  // ?perf=desktop force desktop path (debug) - ?perf=mobile force mobile path (verify on desktop)
  var IS_MOBILE = (function () {
    try {
      var qs = (global.location && global.location.search) || "";
      if (qs.indexOf("perf=desktop") !== -1) return false;
      if (qs.indexOf("perf=mobile") !== -1) return true;
      var ua = (global.navigator && global.navigator.userAgent) || "";
      var uaMobile = /iPhone|iPad|iPod|Android|Mobile|Windows Phone/i.test(ua);
      var lowCore = (global.navigator && global.navigator.hardwareConcurrency && global.navigator.hardwareConcurrency <= 4);
      var lowMem = (global.navigator && global.navigator.deviceMemory && global.navigator.deviceMemory <= 4);
      return !!(uaMobile || lowCore || lowMem);
    } catch (e) { return false; }
  })();

  function FrequencyGuard() { this._lastTrigger = {}; }
  FrequencyGuard.COOLDOWN_MS = {
    "happy": 30000,
    "acknowledgement": 30000,
    "apologetic": 60000,
    "resigned": 45000,
    "greeting": 600000,
    "intimate-greeting": 300000,
    "intimate-farewell": 300000,
    "playful": 45000,
    "task-received": 0,
    "task-handoff": 0,
    "stroke-hair": 20000,
    "speaking": 0,
    "speaking-with-gesture": 0
  };
  FrequencyGuard.prototype.canTrigger = function (state) {
    var now = Date.now();
    var cool = FrequencyGuard.COOLDOWN_MS[state] || 0;
    if (cool === 0) return true;
    var last = this._lastTrigger[state] || 0;
    if (now - last < cool) return false;
    this._lastTrigger[state] = now;
    return true;
  };

  // v1.1.1 · 時段微調機率
  // 深夜 22-5 點：手勢機率降到 6% (不活蹦)
  // 早上 5-9 點：手勢機率拉到 18% (活力)
  // 中午 12-14 點：playful 12% (午後輕鬆) · acknowledgement 5%
  // 晚上工作時段 18-22：acknowledgement 5% (陪伴感) · 手勢預設 12%
  // 其餘：手勢預設 12% (GESTURE_INSERT_PROB)
  function _gestureProbForHour(h) {
    if (h >= 22 || h < 5) return 0.06;
    if (h >= 5 && h < 9)  return 0.18;
    return GESTURE_INSERT_PROB;
  }

  function IdleRotator() {
    this._paused = false;
    this._absent = false;  // v1.1.3
    this._preCall = false; // v1.2.0b · pre-call (未 Start) 用 rich 池
  }
  // v1.3.5 · 待機豐富動作池 · 適合 pre-call (未 Start) 場景 · 砍情緒反應類
  // v2.0.23 · Edward 5/26 catch · 加情緒類進 pre-call 池 · 蘇菲待機更生動
  // 機率：55% idle (4 變體輪播)
  //      13% stroke-hair (摸頭髮 / 撒嬌)
  //      11% playful (玩耍 / 表情變化)
  //      7% greeting (打招呼 hello)
  //      7% happy (開心 · 新加 v2.0.23)
  //      4% acknowledgement (輕點頭 · 新加 v2.0.23)
  //      3% intimate-greeting (親近招呼 · 新加 v2.0.23 · L2 伴侶感)
  // 砍：speaking / task-* / apologetic / resigned / intimate-farewell (對話 / 負面 / 結束類 · 不適合待機 random)
  IdleRotator.prototype._pickPreCallRich = function () {
    var r = Math.random();
    if (r < 0.55) return IDLE_VARIANTS[Math.floor(Math.random() * IDLE_VARIANTS.length)];
    if (r < 0.68) return "stroke-hair";
    if (r < 0.79) return "playful";
    if (r < 0.86) return "greeting";
    if (r < 0.93) return "happy";
    if (r < 0.97) return "acknowledgement";
    return "intimate-greeting";
  };
  IdleRotator.prototype.pickNext = function () {
    var h = new Date().getHours();
    var prob = _gestureProbForHour(h);
    // v1.1.3 - absent state: use ABSENT_GESTURE_PROB (12% stroke-hair) and slow rotation handled externally
    if (this._absent) {
      if (Math.random() < ABSENT_GESTURE_PROB) return "stroke-hair";
      return IDLE_VARIANTS[Math.floor(Math.random() * IDLE_VARIANTS.length)];
    }
    // v1.2.0b - pre-call rich rotation
    if (this._preCall) {
      return this._pickPreCallRich();
    }
    if (Math.random() < prob) return "stroke-hair";
    return IDLE_VARIANTS[Math.floor(Math.random() * IDLE_VARIANTS.length)];
  };
  // v1.2.0b · 通話前後切換 pre-call mode
  IdleRotator.prototype.setPreCallMode = function (b) { this._preCall = !!b; };
  IdleRotator.prototype.isPreCallMode = function () { return !!this._preCall; };
  IdleRotator.prototype.pickIdleOnly = function () {
    return IDLE_VARIANTS[Math.floor(Math.random() * IDLE_VARIANTS.length)];
  };
  IdleRotator.prototype.pause = function () { this._paused = true; };
  IdleRotator.prototype.resume = function () { this._paused = false; };
  IdleRotator.prototype.isPaused = function () { return !!this._paused; };
  // v1.1.3 absent-state hooks (Edward left frame ≥ 10s)
  IdleRotator.prototype.setAbsent = function () { this._absent = true; };
  IdleRotator.prototype.clearAbsent = function () { this._absent = false; };
  IdleRotator.prototype.isAbsent = function () { return !!this._absent; };
  // 時段微調 hook (給外部 caller 查詢 · 不影響內部 pickNext)
  IdleRotator.prototype.gestureProbForHour = function (h) {
    return _gestureProbForHour(typeof h === "number" ? h : new Date().getHours());
  };

  function SpeakingController(pool) {
    this.pool = pool;
    this._t1 = null;
    this._t2 = null;
    this._breathInterval = null;
    this._active = false;
    this._phase = 0;
  }
  // v2.0.16-revert-talking-idle · Edward 2026-05-25 21:36 catch · 方向反了
  // idle = 嘴閉版 / 講話 = 切上層 sophie-speaking (嘴自然律動) / 結束 = 切回 idle
  // 走 _setSpeakingLayer(active) · 不受 __sophieStableSingleVideo 擋 (走上層 video opacity · 不換底層 src)
  // visual mode 仍 maintain (給 idle rotator 看 · 講話期間不擾 idle 切換)
  SpeakingController.prototype.start = function () {
    if (this._idleDelay) { clearTimeout(this._idleDelay); this._idleDelay = null; }
    if (this._active) {
      this.pool._log("speaking start · already active");
      return;
    }
    this._active = true;
    this._phase = 2;
    // 切上層 speaking video · opacity 0→1 (lipsync 沒 active 時才切 · 精準 lipsync 優先)
    if (!window.__sophieLipsyncActive && window.__sophieVisualMode !== "lipsync") {
      this.pool._setSpeakingLayer(true);
      window.__sophieVisualMode = "speaking";
    }
    this.pool._log("speaking start · upper layer on (sophie-speaking 嘴律動)");
  };
  SpeakingController.prototype.stop = function () {
    if (!this._active) return;
    this._active = false;
    this._stopTimers();
    // lipsync active 時不動 (lipsync onended 自己接管)
    if (window.__sophieLipsyncActive || window.__sophieVisualMode === "lipsync") {
      this.pool._log("speaking stop · skip (lipsync 接管)");
      return;
    }
    // 上層 fade out · 透出底層 idle (嘴閉)
    this.pool._setSpeakingLayer(false);
    window.__sophieVisualMode = "idle";
    window.__sophieLastSpeakEndMs = Date.now();
    this.pool._log("speaking stop · upper layer off · back to idle (嘴閉)");
  };
  SpeakingController.prototype._stopTimers = function () {
    if (this._t1) { clearTimeout(this._t1); this._t1 = null; }
    if (this._t2) { clearTimeout(this._t2); this._t2 = null; }
    if (this._breathInterval) { clearInterval(this._breathInterval); this._breathInterval = null; }
  };
  SpeakingController.prototype.isActive = function () { return this._active; };

  function AnimationPool(videoEl, speakingVideoEl) {
    if (!videoEl) { console.warn("[animPool] no video element supplied"); return; }
    // v1.2.0g · 砍 double buffer · 回單 video 簡潔架構
    this.video = videoEl;
    this.speakingVideo = speakingVideoEl || (global.document && global.document.getElementById ? global.document.getElementById("liveVideoSpeaking") : null);
    this.director = global.__sophieAvatarDirector || global.avatarDirector || null;
    this.currentState = "idle";
    this.frequencyGuard = new FrequencyGuard();
    this.idleRotator = new IdleRotator();
    this.speakingCtrl = new SpeakingController(this);
    this._endHandler = null;
    this._preloaders = {};
    // v1.3.0 · 音量驅動微呼吸 + 手動 loop 避開 native loop 黑頻
    this._audioCtx = null;
    this._analyser = null;
    this._breathRAF = null;
    this._currentAmp = 0;
    this._audioDrivenSpeaking = false;
    this._lastRemoteAudioMs = 0;
    this._initIdle();
    this._initSpeakingLayer();
    this._installManualLoop();
    this._preloadCriticalActions();
    this._maybeFireGreeting();
    // v2.0.34 · Edward 5/29 catch「桌機+手機 avatar 整個亂跳」· 預設全關「自動換畫面」
    //   watchdog + idle rotator + (index 的 pre-call rotation) 三者搶 video.src = 亂跳 + 卡 Start
    //   止血: 預設只播單支 idle.mp4 靜靜 loop + 靜態臉 poster · 沒東西換 = 不跳
    //   ?rotation=1 才重開 (debug / 之後單一管家大重整再正規化)
    // watchdog (冷啟自癒 · 偶發空白用 · 但會 nudge 重載造成跳) · 預設關 · poster 已兜底空白
    if (global.__sophieEnableColdStartWatchdog === true) {
      this._startColdStartWatchdog();
    }
    // idle rotator (4 變體輪播 · 預設關 · 待機就單支 idle 不換)
    if (global.__sophieEnableAvatarIdleRotation === true) {
      if (IS_MOBILE) {
        this._startIdleRotator(120000, 180000);
      } else {
        this._startIdleRotator(30000, 60000);
      }
    }
  }

  // v2.0.30 · cold-start blank self-heal watchdog
  // 偵測 live video 冷啟卡 readyState 0 (Modal 503 / 冷啟網路 stall) · 重 nudge 載入直到能播
  AnimationPool.prototype._startColdStartWatchdog = function () {
    var self = this;
    var v = this.video;
    if (!v) return;
    var attempts = 0;
    var MAX_ATTEMPTS = 4;
    var check = function () {
      // 已能播 (readyState >= 2 HAVE_CURRENT_DATA · 有畫面) → 收工
      if (v.readyState >= 2 && v.videoWidth > 0) {
        self._log("coldstart watchdog OK · readyState=" + v.readyState + " · vw=" + v.videoWidth + " · attempts=" + attempts);
        return;
      }
      // 講話 / lipsync / 開場招呼播放中 → 不干預 · reschedule
      // v0.4.2 · Edward 5/29 catch「開場招呼沒了」· watchdog 看到招呼載入時 readyState<2 誤判空白 → 蓋掉招呼
      //   修: 加 __sophiePrerollPlaying guard · 招呼播放中 watchdog 讓路
      if (global.__sophieLipsyncActive || global.__sophieVisualMode === "lipsync" ||
          global.__sophieVisualMode === "speaking" || global.__sophiePrerollPlaying) {
        setTimeout(check, 2500);
        return;
      }
      if (attempts >= MAX_ATTEMPTS) {
        self._log("coldstart watchdog give up after " + attempts + " attempts · readyState=" + v.readyState);
        return;
      }
      attempts++;
      var idleSrc = "/static/sophie-idle.mp4";
      try {
        if (self.idleRotator && self.idleRotator.pickIdleOnly) {
          var pick = self.idleRotator.pickIdleOnly();
          if (ANIMATION_POOL[pick]) idleSrc = ANIMATION_POOL[pick];
        }
      } catch (e) {}
      self._log("coldstart watchdog nudge #" + attempts + " · readyState=" + v.readyState + " · err=" + (v.error ? v.error.code : "none") + " · re-load " + idleSrc.split("/").pop());
      if (self.director && self.director.playIdle) {
        // 新 _seq · 重發 v.src= + v.play() = 重新 fetch Range (暖 Modal · 同手動 fetch 的恢復路徑)
        self.director.playIdle(idleSrc, "coldstart-heal");
      } else {
        try {
          if (v.getAttribute("src") !== idleSrc) v.src = idleSrc;
          v.loop = true; v.muted = true;
          try { v.load(); } catch (loadErr) {}
          var p = v.play();
          if (p && p["catch"]) p["catch"](function () {});
        } catch (e) { self._log("coldstart watchdog nudge fail: " + e.message); }
      }
      // backoff: 2.5s · 3.5s · 4.5s · 5.5s
      setTimeout(check, 2500 + attempts * 1000);
    };
    // 首次延遲 2.5s 才檢 (給正常冷載一個合理 buffer 窗口 · 不過早干預)
    setTimeout(check, 2500);
  };

  // v2.0.14-idle-talk-queue · Edward 2026-05-25 拍板 · 4 idle 嘴微動 + 對話期間不切 + 結束 fade 切下個
  // 對話期間：visual mode === "speaking" / "idle-talk" / "lipsync" → 跳過 + reschedule
  // 對話結束：__sophieLastSpeakEndMs 在 200ms 內 → 立刻 fade 切下個 idle (給對話一個視覺收尾)
  // 否則：維持原 30-60s 隨機輪播 (待機自然輪換)
  AnimationPool.prototype._startIdleRotator = function (minMs, maxMs) {
    if (this._idleRotatorTimer) return;
    var self = this;
    var IDLE_VARIANTS = [
      "/static/sophie-idle.mp4",
      "/static/sophie-idle-2.mp4",
      "/static/sophie-idle-3.mp4",
      "/static/sophie-idle-4.mp4"
    ];
    minMs = minMs || 30000;
    maxMs = maxMs || 60000;
    var pickNext = function (currentSrc) {
      var pool = IDLE_VARIANTS.filter(function (s) {
        return currentSrc.indexOf(s.split("/").pop()) === -1;
      });
      if (pool.length === 0) pool = IDLE_VARIANTS;
      return pool[Math.floor(Math.random() * pool.length)];
    };
    // v2.0.15-no-orange-flash · Edward 5/25 catch · 改 preload-first swap · is-rotating opacity 保持 1 (不透橘底)
    // 流程：先 hidden preload next mp4 → canplay 後 swap v.src + 加 is-rotating (CSS 500ms fade) → 200ms 後移除
    var doSwitchIdle = function (label) {
      try {
        var v = self.video;
        if (!v) return;
        var nextSrc = pickNext(v.currentSrc || v.src || "");
        // 先在 hidden preload element 載入 next mp4 · canplay 後才 swap (不透底色)
        var pre = document.createElement("video");
        pre.preload = "auto";
        pre.muted = true;
        pre.style.display = "none";
        pre.src = nextSrc;
        var swapped = false;
        var doSwap = function () {
          if (swapped) return;
          swapped = true;
          try { pre.parentNode && pre.parentNode.removeChild(pre); } catch (e) {}
          v.classList.add("is-rotating");
          // v2.0.30 · cold-start race fix · 走 AvatarDirector 單一 owner (_seq guard)
          // 不再裸 v.src= / v.play() · 避免打斷 init playIdle 的 pending play (AbortError 卡 readyState 0 = 空白)
          // preload 已暖 (上面 pre.src 已 cache) · Director 的 v.src= 命中 cache · 不透橘底
          if (self.director && self.director.playIdle) {
            self.director.playIdle(nextSrc, "idle-rotator");
          } else {
            try {
              v.src = nextSrc;
              v.loop = true;
              v.muted = true;
              var pp = v.play();
              if (pp && pp["catch"]) pp["catch"](function () {});
            } catch (e) { self._log("swap src fail: " + e.message); }
          }
          // 500ms 後移除 is-rotating · CSS transition 結束 fade 自然結尾
          setTimeout(function () { v.classList.remove("is-rotating"); }, 520);
          self._log("idle rotator [" + label + "] -> " + nextSrc.split("/").pop());
        };
        pre.addEventListener("canplaythrough", doSwap, { once: true });
        pre.addEventListener("canplay", doSwap, { once: true });
        // safety: 800ms 沒 ready 就直接 swap (檔案應該 cached · 不會這麼慢)
        setTimeout(doSwap, 800);
        try { document.body.appendChild(pre); pre.load(); } catch (e) { doSwap(); }
      } catch (e) {
        self._log("idle rotator [" + label + "] fail: " + e.message);
      }
    };
    // v2.0.16 · 砍 postSpeakWatcher + in-call queue (方向反 · idle 不該對話期間切)
    // 對話期間 = 上層 speaking video 顯示 (嘴律動) · 底層 idle 不該換 · 換 idle 反而干擾講話視覺
    // 只保留 30-60s 待機輪播 · 講話期間 schedule 跳過 (mode = speaking)
    var schedule = function () {
      var delay = minMs + Math.random() * (maxMs - minMs);
      self._idleRotatorTimer = setTimeout(function () {
        self._idleRotatorTimer = null;
        // lipsync / speaking / 開場招呼 active 跳過 (上層覆蓋中 · 底層切了也看不見)
        if (global.__sophieLipsyncActive ||
            global.__sophieVisualMode === "lipsync" ||
            global.__sophieVisualMode === "speaking" ||
            global.__sophiePrerollPlaying) {
          schedule();
          return;
        }
        // action play 中跳過
        if (self.currentState && self.currentState !== "idle") {
          schedule();
          return;
        }
        doSwitchIdle("scheduled");
        schedule();
      }, delay);
    };
    schedule();
    self._log("idle rotator v2.0.16 started · 30-60s 待機輪播 · 講話期間跳過 · 4 variants 嘴閉版");
  };

  AnimationPool.prototype._stopIdleRotator = function () {
    if (this._idleRotatorTimer) {
      clearTimeout(this._idleRotatorTimer);
      this._idleRotatorTimer = null;
    }
    if (this._postSpeakWatcher) {
      clearInterval(this._postSpeakWatcher);
      this._postSpeakWatcher = null;
    }
  };

  // v1.3.0 · 手動 loop · 在 video 快結束 (剩 0.15s) 時主動 currentTime=0 + play
  // 避開 Chrome native video.loop 接縫黑 frame
  AnimationPool.prototype._installManualLoop = function () {
    var self = this;
    var EPS = 0.18; // 提前 0.18s 重置 (大概 4 frame · 不會看到 loop 點)
    this.video.addEventListener("timeupdate", function () {
      var v = self.video;
      if (!v.loop) return;
      if (!isFinite(v.duration) || v.duration <= 0) return;
      if (v.currentTime >= v.duration - EPS) {
        try {
          v.currentTime = 0;
          var p = v.play();
          if (p && p.then) p["catch"](function () {});
        } catch (e) {}
      }
    });
    this.video.addEventListener("ended", function () {
      // 防呆 · 萬一 timeupdate 沒搶到 · ended 也接 (但 video.loop=true 通常不會 fire ended)
      if (self.video.loop) {
        try { self.video.currentTime = 0; self.video.play(); } catch (e) {}
      }
    });
  };

  // v1.3.0 · 接 OpenAI realtime audio stream · 抓即時音量驅動微呼吸 + 亮度浮動
  AnimationPool.prototype._initSpeakingLayer = function () {
    var v = this.speakingVideo;
    if (!v) return;
    try {
      if (!v.getAttribute("src")) v.src = "/static/sophie-speaking.mp4";
      v.loop = true;
      v.muted = true;
      v.autoplay = true;
      // v2.1.3 stop-bleed: do NOT preload=auto / load() at construct time (added +6.5MB to open)
      //   speaking layer not needed before entering a call -> warm only when Start pressed
      //   _setSpeakingLayer already has readyState guard + load() fallback (readyState<3 waits canplaythrough)
      v.setAttribute("preload", "none");
    } catch (e) {}
  };

  AnimationPool.prototype._setSpeakingLayer = function (active) {
    var v = this.speakingVideo;
    if (!v) return false;
    try {
      if (this._speakingPauseTimer) {
        clearTimeout(this._speakingPauseTimer);
        this._speakingPauseTimer = null;
      }
      if (active) {
        if (!v.getAttribute("src")) v.src = "/static/sophie-speaking.mp4";
        v.loop = true;
        v.muted = true;
        // v2.0.19 · 卡西法 5/26 deep debug · readyState guard
        // root cause: cold start / Modal 冷啟 / CDN miss → speakingVideo readyState=2 (HAVE_CURRENT_DATA)
        // play() 後 currentTime 卡 0.99 不前進 = 嘴 frozen frame = Edward 真實看到「嘴沒動」
        // guard: readyState >= 3 (HAVE_FUTURE_DATA) 才切 is-visible · 否則 wait canplaythrough 或 1500ms fallback
        var self = this;
        var doActivate = function () {
          try {
            var pp = v.play();
            if (pp && pp["catch"]) pp["catch"](function () {});
            v.classList.add("is-visible");
            self.video.style.transform = "";
            self.video.style.filter = "";
            setTimeout(function () {
              try {
                if (self.speakingVideo && self.speakingVideo.classList.contains("is-visible") && self.video && !self.video.paused) {
                  self.video.pause();
                  self._idlePausedForSpeaking = true;
                }
              } catch (pauseIdleErr) {}
            }, 220);
          } catch (actErr) {
            self._log("v2.0.19 doActivate fail: " + actErr.message);
          }
        };
        if (v.readyState >= 3) {
          self._log("v2.0.19 speaking activate · readyState=" + v.readyState + " (immediate)");
          doActivate();
        } else {
          self._log("v2.0.19 speaking wait canplaythrough · readyState=" + v.readyState);
          try { v.load(); } catch (loadErr) {}
          var fired = false;
          var onCanPlay = function () {
            if (fired) return;
            fired = true;
            try { v.removeEventListener("canplaythrough", onCanPlay); } catch (e) {}
            self._log("v2.0.19 canplaythrough fired · readyState=" + v.readyState + " · activate");
            doActivate();
          };
          v.addEventListener("canplaythrough", onCanPlay, { once: true });
          setTimeout(function () {
            if (fired) return;
            fired = true;
            try { v.removeEventListener("canplaythrough", onCanPlay); } catch (e) {}
            self._log("v2.0.19 canplaythrough timeout 1500ms · fallback activate · readyState=" + v.readyState);
            doActivate();
          }, 1500);
        }
      } else {
        try {
          if (this.video && this.video.paused) {
            var ip = this.video.play();
            if (ip && ip["catch"]) ip["catch"](function () {});
          }
        } catch (idlePlayErr) {}
        this._idlePausedForSpeaking = false;
        v.classList.remove("is-visible");
        var sv = v;
        this._speakingPauseTimer = setTimeout(function () {
          try {
            if (!sv.classList.contains("is-visible")) sv.pause();
          } catch (speakingPauseErr) {}
        }, 260);
      }
      return true;
    } catch (e) {
      this._log("speaking layer fail: " + e.message);
      return false;
    }
  };

  AnimationPool.prototype.attachAudioAnalyser = function (audioEl) {
    if (!audioEl || this._analyser) return; // 已 attach 過、不重複
    try {
      var AC = window.AudioContext || window.webkitAudioContext;
      if (!AC) { this._log("AudioContext unsupported · skip breath"); return; }
      this._audioCtx = new AC();
      var src = this._audioCtx.createMediaElementSource(audioEl);
      this._analyser = this._audioCtx.createAnalyser();
      this._analyser.fftSize = 256;
      this._analyser.smoothingTimeConstant = 0.8;
      src.connect(this._analyser);
      this._startBreathLoop();
      this._analyser.connect(this._audioCtx.destination); // 連回 destination · 不然 audio 不出聲
      this._startBreathLoop();
      this._log("audio analyser attached · breath loop started");
    } catch (e) {
      this._log("attachAudioAnalyser fail: " + e.message);
    }
  };

  // v2.0.36 · Edward 5/29「講 10 秒嘴只動 3-5 秒」· 暴露「距上次偵測到蘇菲聲音多久 (ms)」
  //   讓 index.html 的 scheduleSpeakingStop defer 給真實聲音 (資料訊號的 done 早於播放完 = 嘴早停)
  AnimationPool.prototype.msSinceAudio = function () {
    return Date.now() - (this._lastRemoteAudioMs || 0);
  };

  AnimationPool.prototype._startBreathLoop = function () {
    if (this._breathRAF) return;
    var self = this;
    var buf = new Uint8Array(this._analyser.frequencyBinCount);
    var _breathLastSetMs = 0; // v2.0.11-throttle · 50ms 一次 set CSS · 防 GPU 跟 video 解碼搶 (Edward 5/25 catch B 卡格)
    var tick = function () {
      self._breathRAF = requestAnimationFrame(tick);
      if (!self._analyser) return;
      self._analyser.getByteFrequencyData(buf);
      // 抓 0-1khz 範圍 (人聲核心) 的平均能量
      var sum = 0; var n = Math.min(20, buf.length);
      for (var i = 0; i < n; i++) sum += buf[i];
      var avg = sum / n / 255; // 0-1
      // smooth + 限幅
      self._currentAmp = self._currentAmp * 0.7 + avg * 0.3;
      var amp = self._currentAmp;
      var now = Date.now();
      // v2.0.14 · 砍 audio analyser trigger speaking 邏輯 · idle mp4 自帶嘴微動
      // 仍呼叫 speakingCtrl.start/stop 作為 visual mode flag (給 idle rotator 看 · 對話期間不切)
      if (global.__sophieDisableAudioVisualFallback !== true) {
        if (amp > 0.018) {
          self._lastRemoteAudioMs = now;
          if (!self._audioDrivenSpeaking && !global.__sophieLipsyncActive) {
            self._audioDrivenSpeaking = true;
            if (self.speakingCtrl && !self.speakingCtrl.isActive()) {
              self.startSpeaking();
              self._log("audio analyser -> speaking flag on (idle 自帶嘴微動 · 不切 src)");
            }
          }
        } else if (self._audioDrivenSpeaking && self._lastRemoteAudioMs && (now - self._lastRemoteAudioMs) > 1800 &&
                   now > (global.__sophieSpeakingHoldUntil || 0)) {
          self._audioDrivenSpeaking = false;
          if (self.speakingCtrl && self.speakingCtrl.isActive()) {
            self.stopSpeaking();
            self._log("audio analyser -> speaking flag off (mark __sophieLastSpeakEndMs)");
          }
        }
      }
      // v2.0.11-throttle · 50ms 才 set CSS · 不每幀 (60fps→20fps) · 防 GPU 跟 video 解碼搶 = Edward 5/25 catch 卡格 root cause
      if (global.__sophieReduceVisualLoad !== false) return;
      if (now - _breathLastSetMs < 50) return;
      _breathLastSetMs = now;
      // 套用到 video style
      // - 講話中：scale 1.00~1.025 微縮放 (呼吸感) + brightness 1.00~1.06
      // - 待機 (沒講話)：amp 接近 0 · scale 1.00 · brightness 1.00
      var scale = 1 + amp * 0.025;
      var bright = 1 + amp * 0.06;
      self.video.style.transform = "scale(" + scale.toFixed(3) + ")";
      self.video.style.filter = "brightness(" + bright.toFixed(3) + ")";
    };
    tick();
  };

  AnimationPool.prototype._stopBreathLoop = function () {
    if (this._breathRAF) { cancelAnimationFrame(this._breathRAF); this._breathRAF = null; }
    this.video.style.transform = "";
    this.video.style.filter = "";
  };

  AnimationPool.prototype._playRaw = function (state, loop) {
    if (global.__sophieStableSingleVideo === true) {
      this.currentState = state || this.currentState;
      this._log("_playRaw skipped · stable single-video mode: " + state);
      return;
    }
    var src = ANIMATION_POOL[state];
    if (!src) { this._log("_playRaw missing: " + state); return; }
    if (this._endHandler) {
      this.video.removeEventListener("ended", this._endHandler);
      this._endHandler = null;
    }
    if (this.director && this.director.play) {
      var mode = (IDLE_VARIANTS.indexOf(state) !== -1 || state === "idle") ? "idle" : "action";
      this.director.play({
        mode: mode,
        src: src,
        loop: !!loop,
        owner: "animation-pool",
        label: state
      });
      this.currentState = state;
      return;
    }
    // v1.2.0g · src 切換時短暫 opacity 0.3 隱黑頻 (transition 150ms)
    var self = this;
    var sameSrc = false;
    try { sameSrc = (this.video.currentSrc && this.video.currentSrc.indexOf(src) !== -1); } catch (e) {}
    if (!sameSrc) {
      this.video.classList.add("is-switching");
      try { this.video.src = src; }
      catch (e) { this._log("_playRaw set src fail: " + e.message); this.video.classList.remove("is-switching"); return; }
      // canplay 後移除 is-switching · fade 回 opacity 1
      var onReady = function () {
        self.video.removeEventListener("canplay", onReady);
        self.video.classList.remove("is-switching");
      };
      this.video.addEventListener("canplay", onReady, { once: true });
      // safety fallback 500ms 後強制復原
      setTimeout(function () {
        try { self.video.removeEventListener("canplay", onReady); } catch (e) {}
        self.video.classList.remove("is-switching");
      }, 500);
    }
    this.video.loop = !!loop;
    this.video.muted = true;
    var p = this.video.play();
    if (p && p.then) { p["catch"](function () {}); }
    this.currentState = state;
  };

  AnimationPool.prototype._initIdle = function () {
    var idle = this.idleRotator.pickIdleOnly();
    var src = ANIMATION_POOL[idle];
    if (this.director && this.director.playIdle) {
      this.director.playIdle(src, "init-idle");
      this.currentState = idle;
      this._log("idle init OK via AvatarDirector src=" + idle);
      return;
    }
    try {
      if (this.video.getAttribute("src") !== src) { this.video.src = src; }
    } catch (e) {}
    this.video.loop = true;
    this.video.muted = true;
    this.video.autoplay = true;
    this.video.setAttribute("preload", "auto");
    var p = this.video.play();
    if (p && p.then) { p["catch"](function () {}); }
    this.currentState = idle;
    this._log("idle init OK src=" + idle);
  };

  AnimationPool.prototype._preloadCriticalActions = function () {
    // v2.1.3 stop-bleed (root cause: open-page preload whole lib -> desktop 16 ~126MB / mobile 4 metadata)
    //   open page only needs 1 idle: liveVideo tag already src=sophie-idle.mp4 + preload=metadata + autoplay loop,
    //   _initIdle() also ensures play -> NO extra preload needed at open.
    //   all other 15 lazy (load only at the moment they actually play):
    //     doSwitchIdle/doSwitchPreCall = preload-first swap (own createElement+load; do NOT read _preloaders)
    //     _playRaw (emotion) = this.video.src=src then canplay (does NOT read _preloaders)
    //     setSpeakingSrc (speak) = v.src + v.load() on demand
    //   grep confirms _preloaders only written here, no consumer depends on pre-warm -> zero functional regression.
    //   ?legacyPreload=1 to use old path (debug / measurement baseline)
    if (global.__sophieLegacyPreload === true) {
      var self = this;
      var keys = IS_MOBILE ? IDLE_VARIANTS.slice() : Object.keys(ANIMATION_POOL);
      var preloadMode = IS_MOBILE ? "metadata" : "auto";
      var primed = 0;
      keys.forEach(function (state) {
        if (state === self.currentState) return;
        if (!ANIMATION_POOL[state]) return;
        var pre = document.createElement("video");
        pre.preload = preloadMode;
        pre.muted = true;
        pre.src = ANIMATION_POOL[state];
        pre.style.display = "none";
        try { pre.load(); primed++; } catch (e) {}
        self._preloaders[state] = pre;
      });
      this._log("[legacy] preload primed " + primed + "/" + keys.length + " (mode=" + preloadMode + " mobile=" + IS_MOBILE + ")");
      return;
    }
    this._log("v2.1.3 stop-bleed open preload SKIP (keep 1 idle by tag, rest lazy) mobile=" + IS_MOBILE);
  };

  AnimationPool.prototype.playAction = function (state) {
    if (global.__sophieEnableAvatarActions !== true) {
      this._log("playAction skipped · disabled for anti-flicker stable mode: " + state);
      return;
    }
    if (state === "idle") return;
    if (IDLE_VARIANTS.indexOf(state) !== -1) return;
    if (!ANIMATION_POOL[state]) {
      this._log("playAction unknown state: " + state);
      return;
    }
    if (this.speakingCtrl.isActive() && !HIGH_PRIORITY[state]) {
      this._log("playAction skipped (speaking active): " + state);
      return;
    }
    if (!this.frequencyGuard.canTrigger(state)) {
      this._log("playAction throttled: " + state);
      return;
    }
    this._playRaw(state, false);
    this._log("playAction -> " + state);
    var self = this;
    this._endHandler = function () { self._returnToIdle(); };
    this.video.addEventListener("ended", this._endHandler, { once: true });
  };

  AnimationPool.prototype._returnToIdle = function () {
    if (global.__sophieStableSingleVideo === true) {
      this.currentState = "idle";
      this._log("returnToIdle skipped · stable single-video mode");
      return;
    }
    var nextIdle = this.idleRotator.pickNext();
    var isLoop = (IDLE_VARIANTS.indexOf(nextIdle) !== -1);
    this._playRaw(nextIdle, isLoop);
    if (!isLoop) {
      var self = this;
      this._endHandler = function () {
        var idle = self.idleRotator.pickIdleOnly();
        self._playRaw(idle, true);
      };
      this.video.addEventListener("ended", this._endHandler, { once: true });
    }
    this._log("returnToIdle -> " + nextIdle);
  };

  // v1.2.0b · pre-call 自動輪播 timer (Edward 5/23「未 start 加親親 / 撒嬌 / hello」)
  // v2.0.15 · Edward 5/25 catch · 修「flag 寫死 false 沒啟動」+ 改走 _doSwitchIdleRich (preload-first swap · 不透橘底)
  // 不再受 __sophieStableSingleVideo 限制 (pre-call 不在 in-call · 不擔心通話閃頻)
  AnimationPool.prototype.startPreCallRotation = function () {
    if (global.__sophieEnableAvatarIdleRotation !== true) {
      this._log("preCallRotation skipped · disabled for anti-flicker stable mode");
      return;
    }
    if (this._preCallTimer) return;
    this.idleRotator.setPreCallMode(true);
    var self = this;
    var ANIMATION_POOL_LOCAL = {
      "idle": "/static/sophie-idle.mp4",
      "idle-2": "/static/sophie-idle-2.mp4",
      "idle-3": "/static/sophie-idle-3.mp4",
      "idle-4": "/static/sophie-idle-4.mp4",
      "stroke-hair": "/static/sophie-stroke-hair.mp4",
      "playful": "/static/sophie-playful.mp4",
      "greeting": "/static/sophie-greeting.mp4",
      // v2.0.23 · 加情緒類 (Edward 5/26 catch · 待機更生動)
      "happy": "/static/sophie-happy.mp4",
      "acknowledgement": "/static/sophie-acknowledgement.mp4",
      "intimate-greeting": "/static/sophie-intimate-greeting.mp4"
    };
    // 走 preload-first swap (preload next 完才切 · is-rotating opacity 1 · 不透底色)
    // 動作類 (stroke-hair / playful / greeting) 播完接回 random idle (loop)
    var doSwitchPreCall = function () {
      var v = self.video;
      if (!v) return;
      var nextState = self.idleRotator.pickNext();  // rich pool
      var nextSrc = ANIMATION_POOL_LOCAL[nextState] || ANIMATION_POOL_LOCAL["idle"];
      var isIdle = (nextState && nextState.indexOf("idle") === 0);
      // hidden preload first
      var pre = document.createElement("video");
      pre.preload = "auto";
      pre.muted = true;
      pre.style.display = "none";
      pre.src = nextSrc;
      var swapped = false;
      var doSwap = function () {
        if (swapped) return;
        swapped = true;
        try { pre.parentNode && pre.parentNode.removeChild(pre); } catch (e) {}
        // 砍既有 ended handler (防動作播完 _returnToIdle 重複觸發)
        if (self._endHandler) {
          try { v.removeEventListener("ended", self._endHandler); } catch (e) {}
          self._endHandler = null;
        }
        v.classList.add("is-rotating");
        // v2.0.30 · cold-start race fix · 走 AvatarDirector 單一 owner (_seq guard)
        // 不再裸 v.src= / v.play() · 避免打斷 init playIdle 的 pending play (AbortError 卡 readyState 0 = 空白)
        // 動作 (non-loop) 播完接回 random idle · 走 Director onEnded (內建 _seq guard · 不用裸 ended listener)
        var afterAction = function () {
          var idle = self.idleRotator.pickIdleOnly();
          var idleSrc = ANIMATION_POOL_LOCAL[idle];
          // 動作後接 idle · 再次 preload swap
          var pre2 = document.createElement("video");
          pre2.preload = "auto";
          pre2.muted = true;
          pre2.style.display = "none";
          pre2.src = idleSrc;
          var s2 = false;
          var swap2 = function () {
            if (s2) return; s2 = true;
            try { pre2.parentNode && pre2.parentNode.removeChild(pre2); } catch (e) {}
            v.classList.add("is-rotating");
            if (self.director && self.director.playIdle) {
              self.director.playIdle(idleSrc, "precall-action-idle");
            } else {
              try { v.src = idleSrc; v.loop = true; v.muted = true; var p2 = v.play(); if (p2 && p2["catch"]) p2["catch"](function () {}); } catch (e) {}
            }
            setTimeout(function () { v.classList.remove("is-rotating"); }, 520);
            self._log("preCall action -> idle (" + idle + ")");
          };
          pre2.addEventListener("canplaythrough", swap2, { once: true });
          pre2.addEventListener("canplay", swap2, { once: true });
          setTimeout(swap2, 800);
          try { document.body.appendChild(pre2); pre2.load(); } catch (e) { swap2(); }
        };
        if (self.director && self.director.play) {
          if (isIdle) {
            self.director.playIdle(nextSrc, "precall-idle");
          } else {
            self.director.play({
              mode: "action",
              src: nextSrc,
              loop: false,
              owner: "precall-rotation",
              label: nextState,
              onEnded: afterAction
            });
          }
        } else {
          // fallback (無 Director) · 保留舊裸 swap + 手動 ended listener
          if (self._endHandler) {
            try { v.removeEventListener("ended", self._endHandler); } catch (e) {}
            self._endHandler = null;
          }
          try {
            v.src = nextSrc;
            v.loop = !!isIdle;
            v.muted = true;
            var pp = v.play();
            if (pp && pp["catch"]) pp["catch"](function () {});
          } catch (e) { self._log("preCall swap fail: " + e.message); }
          if (!isIdle) {
            self._endHandler = function () {
              try { v.removeEventListener("ended", self._endHandler); } catch (e) {}
              self._endHandler = null;
              afterAction();
            };
            v.addEventListener("ended", self._endHandler, { once: true });
          }
        }
        setTimeout(function () { v.classList.remove("is-rotating"); }, 520);
        self.currentState = nextState;
        self._log("preCallRotation -> " + nextState);
      };
      pre.addEventListener("canplaythrough", doSwap, { once: true });
      pre.addEventListener("canplay", doSwap, { once: true });
      setTimeout(doSwap, 800);
      try { document.body.appendChild(pre); pre.load(); } catch (e) { doSwap(); }
    };
    var schedule = function () {
      self._preCallTimer = setTimeout(function () {
        if (self.speakingCtrl.isActive() || self.idleRotator.isPaused()) {
          schedule();
          return;
        }
        // in-call mode 不主動切 (在 _startIdleRotator 自己有 7-10s 短間隔 in-call queue)
        if (global.__sophieVisualMode === "idle-talk" || global.__sophieVisualMode === "speaking" || global.__sophieVisualMode === "lipsync") {
          schedule();
          return;
        }
        doSwitchPreCall();
        schedule();
      // v2.0.32 mobile-perf-safe-fix #3 (root cause: every switch builds hidden preload video + swap = decode cost)
      //   desktop: 14-22s (unchanged) · mobile: 28-44s (2x slower) -> fewer hidden video creations + swaps
      }, (IS_MOBILE ? 28000 : 14000) + Math.random() * (IS_MOBILE ? 16000 : 8000));
    };
    schedule();
    this._log("preCallRotation v2.0.15 start · rich pool · idle 65 / stroke-hair 15 / playful 12 / greeting 8 · interval=" + (IS_MOBILE ? "28-44s(mobile)" : "14-22s") + " · preload-first swap");
  };

  AnimationPool.prototype.stopPreCallRotation = function () {
    if (this._preCallTimer) {
      clearTimeout(this._preCallTimer);
      this._preCallTimer = null;
    }
    this.idleRotator.setPreCallMode(false);
    this._log("preCallRotation stop (back to normal idle)");
  };

  // v1.1.3 - force greeting (used when Edward returns from absent); bypasses 600s greeting cooldown
  AnimationPool.prototype.playGreetingNoThrottle = function () {
    // Reset greeting last-trigger so playAction will fire it now.
    if (this.frequencyGuard && this.frequencyGuard._lastTrigger) {
      this.frequencyGuard._lastTrigger["greeting"] = 0;
    }
    // Clear absent flag (Edward returned)
    if (this.idleRotator && this.idleRotator.clearAbsent) {
      this.idleRotator.clearAbsent();
    }
    this.playAction("greeting");
    this._log("playGreetingNoThrottle fired (edward returned)");
  };

  AnimationPool.prototype.startSpeaking = function () {
    if (this.speakingCtrl.isActive()) return;
    this.speakingCtrl.start();
  };
  AnimationPool.prototype.stopSpeaking = function () {
    this.speakingCtrl.stop();
  };

  // v2.0.29 · Edward 5/27 字數選池 · 蘇菲講話長度動態配對應影片
  // 3s 影片 (短回 / 1-3 字 / 嗯啦 對啊)
  // 5s 影片 (中等 / 4-11 字 / 預設 · sophie-speaking.mp4)
  // 10s 影片 (長句 / 12+ 字 / 完整段落)
  // 規格紀律: 三支影片首尾都是 idle 第 1 幀 · 接 idle 無縫
  AnimationPool.prototype.setSpeakingSrc = function (srcUrl) {
    var v = this.speakingVideo;
    if (!v) return false;
    try {
      var current = v.getAttribute("src") || "";
      // 已是同 src · 不必 reload
      if (current.indexOf(srcUrl) !== -1) {
        this._log("[v2.0.29] setSpeakingSrc no-op: " + srcUrl.split("/").pop());
        return true;
      }
      v.src = srcUrl;
      try { v.load(); } catch (loadErr) {}
      this._log("[v2.0.29] setSpeakingSrc → " + srcUrl.split("/").pop());
      return true;
    } catch (e) {
      this._log("[v2.0.29] setSpeakingSrc fail: " + e.message);
      return false;
    }
  };

  AnimationPool.prototype._maybeFireGreeting = function () {
    try {
      var rec = localStorage.getItem(GREETED_KEY);
      var now = Date.now();
      var shouldGreet = false;
      if (!rec) { shouldGreet = true; }
      else {
        var lastTs = parseInt(rec, 10);
        if (isNaN(lastTs) || (now - lastTs) > GREETED_TTL_MS) { shouldGreet = true; }
      }
      if (shouldGreet) {
        var self = this;
        setTimeout(function () {
          self.playAction("greeting");
          try { localStorage.setItem(GREETED_KEY, String(Date.now())); } catch (e) {}
        }, 1500);
        this._log("greeting scheduled (first open or TTL expired)");
      } else {
        this._log("greeting skipped (within 24h TTL)");
      }
    } catch (e) {
      this._log("greeting check fail: " + e.message);
    }
  };

  AnimationPool.prototype.getState = function () { return this.currentState; };

  AnimationPool.prototype._log = function (msg) {
    try { console.log("[animPool]", msg); } catch (e) {}
    if (global.__sophie && typeof global.__sophie.log === "function") {
      try { global.__sophie.log("[animPool] " + msg); } catch (e) {}
    }
  };

  global.AnimationPool = AnimationPool;
  global.ANIMATION_POOL_STATES = Object.keys(ANIMATION_POOL);
  global.FrequencyGuard = FrequencyGuard;
  global.IdleRotator = IdleRotator;
  global.SpeakingController = SpeakingController;
})(window);
