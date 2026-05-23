/*!
 * Voice Path v0.9.0 - 17-State Animation Pool
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

  function IdleRotator() {}
  IdleRotator.prototype.pickNext = function () {
    if (Math.random() < GESTURE_INSERT_PROB) return "stroke-hair";
    return IDLE_VARIANTS[Math.floor(Math.random() * IDLE_VARIANTS.length)];
  };
  IdleRotator.prototype.pickIdleOnly = function () {
    return IDLE_VARIANTS[Math.floor(Math.random() * IDLE_VARIANTS.length)];
  };

  function SpeakingController(pool) {
    this.pool = pool;
    this._t1 = null;
    this._t2 = null;
    this._breathInterval = null;
    this._active = false;
    this._phase = 0;
  }
  SpeakingController.prototype.start = function () {
    this._stopTimers();
    this._active = true;
    this._phase = 1;
    this.pool._playRaw("speaking-with-gesture", false);
    var self = this;
    this._t1 = setTimeout(function () {
      if (!self._active) return;
      self._phase = 2;
      self.pool._playRaw("speaking", true);
      self._t2 = setTimeout(function () {
        if (!self._active) return;
        self._phase = 3;
        self._breathInterval = setInterval(function () {
          if (!self._active) return;
          self._breathePause();
        }, 8000);
      }, 10000);
    }, 5000);
    this.pool._log("speaking start (phase 1: with-gesture)");
  };
  SpeakingController.prototype._breathePause = function () {
    if (!this._active) return;
    var idle = this.pool.idleRotator.pickIdleOnly();
    this.pool._playRaw(idle, false);
    var self = this;
    setTimeout(function () {
      if (!self._active) return;
      self.pool._playRaw("speaking", true);
    }, 1500);
  };
  SpeakingController.prototype.stop = function () {
    this._active = false;
    this._stopTimers();
    var idle = this.pool.idleRotator.pickIdleOnly();
    this.pool._playRaw(idle, true);
    this.pool._log("speaking stop (return idle=" + idle + ")");
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
    var isGesture = (nextIdle === "stroke-hair");
    this.video.loop = !isGesture;
    this.video.muted = true;
    var p = this.video.play();
    if (p && p.then) { p["catch"](function () {}); }
    this.currentState = nextIdle;
    if (this._endHandler) {
      this.video.removeEventListener("ended", this._endHandler);
      this._endHandler = null;
    }
    var self = this;
    if (isGesture) {
      this._endHandler = function () {
        var idle = self.idleRotator.pickIdleOnly();
        self._playRaw(idle, true);
      };
      this.video.addEventListener("ended", this._endHandler, { once: true });
    }
    this._log("returnToIdle -> " + nextIdle);
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
