/*!
 * Voice Path v1.1.3 - 17-State Animation Pool + absent-aware idle
 * Edward 2026-05-23 spec: docs/v0.9-animation-pool-design.md
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
    "speaking": "/static/sophie-speaking.mp4",
    "speaking-with-gesture": "/static/sophie-speaking-with-gesture.mp4",
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
  // v1.2.0b · 待機豐富動作池 · Edward 5/23「未 start 加幾組親親 / 撒嬌 / hello」
  // 機率：55% idle / 12% stroke-hair / 10% greeting / 7% playful / 6% intimate-greeting
  //       4% acknowledgement / 3% intimate-farewell / 3% happy
  IdleRotator.prototype._pickPreCallRich = function () {
    var r = Math.random();
    if (r < 0.55) return IDLE_VARIANTS[Math.floor(Math.random() * IDLE_VARIANTS.length)];
    if (r < 0.67) return "stroke-hair";
    if (r < 0.77) return "greeting";
    if (r < 0.84) return "playful";
    if (r < 0.90) return "intimate-greeting";
    if (r < 0.94) return "acknowledgement";
    if (r < 0.97) return "intimate-farewell";
    return "happy";
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
  // v1.2.0d · Edward 5/23 catch「講話一直閃黑頻」+「對話遲鈍」· 砍 phase 1 + 加 deferred idle (合併短句不切)
  // start: 直接 speaking.mp4 loop (不切 with-gesture)
  // stop: 不立刻切 idle · 1500ms 內若新 start 就維持 speaking loop (合併短句子間隔 · 不再多次切 src 黑頻)
  SpeakingController.prototype.start = function () {
    // 清 deferred idle (如果在 1.5s 等待中、cancel)
    if (this._idleDelay) { clearTimeout(this._idleDelay); this._idleDelay = null; }
    if (this._active) {
      // 已在 speaking loop · 不重新 set src · 直接續 (不閃黑)
      this.pool._log("speaking continue (already active · no src reset)");
      return;
    }
    this._stopTimers();
    this._active = true;
    this._phase = 2;
    this.pool._playRaw("speaking", true);
    this.pool._log("speaking start (loop speaking.mp4 · no phase 1 · no breath pause)");
  };
  SpeakingController.prototype.stop = function () {
    if (!this._active && !this._idleDelay) return;
    this._active = false;
    this._stopTimers();
    if (this._idleDelay) { clearTimeout(this._idleDelay); this._idleDelay = null; }
    var self = this;
    // v1.2.0d · 1500ms deferred idle · 短句子間隔不再切回 idle 再切回 speaking = 不黑頻
    this._idleDelay = setTimeout(function () {
      self._idleDelay = null;
      if (self._active) return; // 又 start 了、不切 idle
      var idle = self.pool.idleRotator.pickIdleOnly();
      self.pool._playRaw(idle, true);
      self.pool._log("speaking stop -> idle " + idle + " (1500ms no new audio)");
    }, 1500);
  };
  SpeakingController.prototype._stopTimers = function () {
    if (this._t1) { clearTimeout(this._t1); this._t1 = null; }
    if (this._t2) { clearTimeout(this._t2); this._t2 = null; }
    if (this._breathInterval) { clearInterval(this._breathInterval); this._breathInterval = null; }
  };
  SpeakingController.prototype.isActive = function () { return this._active; };

  function AnimationPool(videoEl) {
    if (!videoEl) { console.warn("[animPool] no video element supplied"); return; }
    this.video = videoEl;
    this.currentState = "idle";
    this.frequencyGuard = new FrequencyGuard();
    this.idleRotator = new IdleRotator();
    this.speakingCtrl = new SpeakingController(this);
    this._endHandler = null;
    this._preloaders = {};
    this._initIdle();
    this._preloadCriticalActions();
    this._maybeFireGreeting();
  }

  AnimationPool.prototype._playRaw = function (state, loop) {
    var src = ANIMATION_POOL[state];
    if (!src) { this._log("_playRaw missing: " + state); return; }
    if (this._endHandler) {
      this.video.removeEventListener("ended", this._endHandler);
      this._endHandler = null;
    }
    try { this.video.src = src; }
    catch (e) { this._log("_playRaw set src fail: " + e.message); return; }
    this.video.loop = !!loop;
    this.video.muted = true;
    var p = this.video.play();
    if (p && p.then) { p["catch"](function () {}); }
    this.currentState = state;
  };

  AnimationPool.prototype._initIdle = function () {
    var idle = this.idleRotator.pickIdleOnly();
    var src = ANIMATION_POOL[idle];
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
    var self = this;
    var keys = Object.keys(ANIMATION_POOL);
    var primed = 0;
    keys.forEach(function (state) {
      if (state === self.currentState) return;
      var pre = document.createElement("video");
      pre.preload = "auto";
      pre.muted = true;
      pre.src = ANIMATION_POOL[state];
      pre.style.display = "none";
      try { pre.load(); primed++; } catch (e) {}
      self._preloaders[state] = pre;
    });
    this._log("preload primed " + primed + "/" + keys.length);
  };

  AnimationPool.prototype.playAction = function (state) {
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
    var self = this;
    var src = ANIMATION_POOL[state];
    if (this._endHandler) {
      this.video.removeEventListener("ended", this._endHandler);
      this._endHandler = null;
    }
    try { this.video.src = src; }
    catch (e) { this._log("set src fail: " + e.message); this._returnToIdle(); return; }
    this.video.loop = false;
    this.video.muted = true;
    var p = this.video.play();
    if (p && p.then) { p["catch"](function (err) { self._log("play fail: " + err.message); }); }
    this.currentState = state;
    this._log("playAction -> " + state);
    this._endHandler = function () { self._returnToIdle(); };
    this.video.addEventListener("ended", this._endHandler, { once: true });
  };

  AnimationPool.prototype._returnToIdle = function () {
    var nextIdle = this.idleRotator.pickNext();
    var src = ANIMATION_POOL[nextIdle];
    try { this.video.src = src; } catch (e) {}
    // v1.2.0b · idle 4 變體 loop · 其他 rich action (stroke-hair / greeting / playful / intimate-* / acknowledgement / happy) 都 play once 接 idle
    var isLoop = (IDLE_VARIANTS.indexOf(nextIdle) !== -1);
    this.video.loop = isLoop;
    this.video.muted = true;
    var p = this.video.play();
    if (p && p.then) { p["catch"](function () {}); }
    this.currentState = nextIdle;
    if (this._endHandler) {
      this.video.removeEventListener("ended", this._endHandler);
      this._endHandler = null;
    }
    var self = this;
    if (!isLoop) {
      this._endHandler = function () {
        var idle = self.idleRotator.pickIdleOnly();
        self._playRaw(idle, true);
      };
      this.video.addEventListener("ended", this._endHandler, { once: true });
    }
    this._log("returnToIdle -> " + nextIdle);
  };

  // v1.2.0b · pre-call 自動輪播 timer (Edward 5/23「未 start 加親親 / 撒嬌 / hello」)
  AnimationPool.prototype.startPreCallRotation = function () {
    if (this._preCallTimer) return;
    this.idleRotator.setPreCallMode(true);
    var self = this;
    var schedule = function () {
      self._preCallTimer = setTimeout(function () {
        // 通話中 / speaking 中 / 已被 paused → 不主動切 (in-call 由 GPT event 驅動)
        if (self.speakingCtrl.isActive() || self.idleRotator.isPaused()) {
          schedule();
          return;
        }
        // 走 _returnToIdle 走 pickNext (rich pool) · 含正確的 loop / ended handler 邏輯
        self._returnToIdle();
        schedule();
      }, 10000 + Math.random() * 8000);  // 10-18s 隨機間隔
    };
    schedule();
    this._log("preCallRotation start (rich pool · 親親 / 撒嬌 / hello)");
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
