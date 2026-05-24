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
  // 機率：65% idle (4 變體輪播)
  //      15% stroke-hair (摸頭髮 / 撒嬌)
  //      12% playful (玩耍 / 表情變化)
  //      8% greeting (打招呼 hello)
  // 砍：intimate-* (親密互動 · 訪客不該看)
  // 砍：acknowledgement / happy / apologetic / resigned (對話反應類 · 不適合待機 random)
  IdleRotator.prototype._pickPreCallRich = function () {
    var r = Math.random();
    if (r < 0.65) return IDLE_VARIANTS[Math.floor(Math.random() * IDLE_VARIANTS.length)];
    if (r < 0.80) return "stroke-hair";
    if (r < 0.92) return "playful";
    return "greeting";
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
  // v1.9.13 · 霍爾 verdict · 加回 speaking fallback · 視覺優先順序：
  // 精準 lipsync > fuzzy lipsync > sophie-speaking.mp4 loop > idle
  // start: 切 sophie-speaking.mp4 loop (除非 lipsync 已 active)
  // stop: 切回 idle (含 lipsync 中斷情況)
  SpeakingController.prototype.start = function () {
    if (this._idleDelay) { clearTimeout(this._idleDelay); this._idleDelay = null; }
    if (this._active) {
      this.pool._log("speaking continue (already active)");
      return;
    }
    this._stopTimers();
    this._active = true;
    this._phase = 2;
    this.pool.currentState = "speaking";
    if (window.__sophieStableSingleVideo === true) {
      window.__sophieVisualMode = "speaking";
      this.pool._log("speaking start · stable single-video mode, no src switch");
      return;
    }
    // v1.9.15 · lipsync 已鎖 · 不動 video
    if (window.__sophieLipsyncActive || window.__sophieVisualMode === "lipsync") {
      this.pool._log("speaking start · skip src switch (lipsync 鎖住)");
      return;
    }
    window.__sophieVisualMode = "speaking";
    if (this.pool.director && this.pool.director.playSpeaking) {
      this.pool.director.playSpeaking("/static/sophie-speaking.mp4", "speaking-start");
      this.pool._log("speaking start -> AvatarDirector");
      return;
    }
    // v2.x · 禁止直接 v.src · 改走 Compositor.dispatch
    try {
      if (window.__sophieAvatarCompositor && window.__sophieAvatarCompositor.dispatch) {
        window.__sophieAvatarCompositor.dispatch({
          type: "play_speaking",
          src: "/static/sophie-speaking.mp4",
          owner: "speakingCtrl-fallback",
          reason: "speaking start · no director path"
        });
        this.pool._log("speaking start -> Compositor (fallback path)");
      } else {
        this.pool._log("speaking start FAIL · no Compositor or Director · refuse direct v.src write");
      }
    } catch (e) {
      this.pool._log("speaking start Compositor fail: " + e.message);
    }
  };
  SpeakingController.prototype.stop = function () {
    if (!this._active && !this._idleDelay) return;
    // v1.9.15 · 霍爾刀 1 · lipsync active 時 stop 不准動 video · 由 lipsync onended 決定
    if (window.__sophieLipsyncActive || window.__sophieVisualMode === "lipsync") {
      this._active = false;
      this._stopTimers();
      this.pool._log("speaking stop · skip (lipsync 鎖住 · 等 clip onended 接管)");
      return;
    }
    this._active = false;
    this._stopTimers();
    if (this._idleDelay) { clearTimeout(this._idleDelay); this._idleDelay = null; }
    if (window.__sophieStableSingleVideo === true) {
      window.__sophieVisualMode = "idle";
      this.pool.currentState = "idle";
      this.pool._log("speaking stop · stable single-video mode, no src switch");
      return;
    }
    var self = this;
    this._idleDelay = setTimeout(function () {
      self._idleDelay = null;
      if (self._active) return;
      // v1.9.15 · 切回前再 check lipsync 鎖
      if (window.__sophieLipsyncActive || window.__sophieVisualMode === "lipsync") {
        self.pool._log("speaking stop deferred · lipsync 已接管");
        return;
      }
      if (self.pool.director && self.pool.director.playIdle) {
        self.pool.director.playIdle("/static/sophie-idle.mp4", "speaking-stop");
        window.__sophieVisualMode = "idle";
        self.pool.currentState = "idle";
        self.pool._log("speaking stop -> AvatarDirector idle");
        return;
      }
      // v2.x · 禁止直接 v.src · 改走 Compositor.dispatch
      try {
        if (window.__sophieAvatarCompositor && window.__sophieAvatarCompositor.dispatch) {
          window.__sophieAvatarCompositor.dispatch({
            type: "play_idle",
            src: "/static/sophie-idle.mp4",
            owner: "speakingCtrl-stop-fallback",
            reason: "speaking stop · no director path"
          });
          self.pool._log("speaking stop -> Compositor idle (fallback)");
        } else {
          self.pool._log("speaking stop FAIL · no Compositor available · refuse direct v.src write");
        }
      } catch (e) {
        self.pool._log("speaking stop Compositor fail: " + e.message);
      }
      window.__sophieVisualMode = "idle";
      self.pool.currentState = "idle";
    }, 250);
  };
  SpeakingController.prototype._stopTimers = function () {
    if (this._t1) { clearTimeout(this._t1); this._t1 = null; }
    if (this._t2) { clearTimeout(this._t2); this._t2 = null; }
    if (this._breathInterval) { clearInterval(this._breathInterval); this._breathInterval = null; }
  };
  SpeakingController.prototype.isActive = function () { return this._active; };

  function AnimationPool(videoEl) {
    if (!videoEl) { console.warn("[animPool] no video element supplied"); return; }
    // v1.2.0g · 砍 double buffer · 回單 video 簡潔架構
    this.video = videoEl;
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
    this._initIdle();
    this._installManualLoop();
    this._preloadCriticalActions();
    this._maybeFireGreeting();
  }

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
      this._analyser.connect(this._audioCtx.destination); // 連回 destination · 不然 audio 不出聲
      this._startBreathLoop();
      this._log("audio analyser attached · breath loop started");
    } catch (e) {
      this._log("attachAudioAnalyser fail: " + e.message);
    }
  };

  AnimationPool.prototype._startBreathLoop = function () {
    if (this._breathRAF) return;
    var self = this;
    var buf = new Uint8Array(this._analyser.frequencyBinCount);
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
    // v2.x · 禁止直接 v.src · 改走 Compositor.dispatch
    if (window.__sophieAvatarCompositor && window.__sophieAvatarCompositor.dispatch) {
      var mode2 = (IDLE_VARIANTS.indexOf(state) !== -1 || state === "idle") ? "play_idle" : "play_action";
      window.__sophieAvatarCompositor.dispatch({
        type: mode2,
        src: src,
        loop: !!loop,
        owner: "animation-pool-playRaw",
        label: state
      });
      this.currentState = state;
      return;
    }
    this._log("_playRaw FAIL · no Compositor available · refuse direct v.src write: " + state);
    return;
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
    // v2.x · 禁止直接 v.src · 改走 Compositor.dispatch
    if (window.__sophieAvatarCompositor && window.__sophieAvatarCompositor.dispatch) {
      window.__sophieAvatarCompositor.dispatch({
        type: "play_idle",
        src: src,
        owner: "animation-pool-initIdle"
      });
      this.currentState = idle;
      this._log("idle init OK via Compositor src=" + idle);
    } else {
      this._log("idle init SKIP · no Compositor · refuse direct v.src write src=" + idle);
    }
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
  AnimationPool.prototype.startPreCallRotation = function () {
    if (global.__sophieEnableAvatarIdleRotation !== true) {
      this._log("preCallRotation skipped · disabled for anti-flicker stable mode");
      return;
    }
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
      }, 14000 + Math.random() * 8000);  // v1.3.5 · 14-22s 隨機間隔 · 慢一點不密集切
    };
    schedule();
    this._log("preCallRotation start (rich pool · idle 65% / stroke-hair 15% / playful 12% / greeting 8%)");
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
