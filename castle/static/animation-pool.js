/*!
 * Voice Path v0.8 · Animation Pool
 *
 * 4 state animation pool · idle (loop autoplay) + 3 action loops
 *  - idle:         /static/sophie-idle.mp4         (永遠 autoplay loop muted)
 *  - speaking:     /static/sophie-speaking.mp4     (GPT 講話時 · 跑完回 idle)
 *  - task-received:/static/sophie-task-received.mp4 (用戶剛講完 · 跑完回 idle)
 *  - task-handoff: /static/sophie-task-handoff.mp4 (對話結束 · 跑完回 idle)
 *
 * 缺的狀態 (thinking/happy/impressed/yawn) = silent fallback 到 idle、不報錯
 *
 * 首偵 = 尾偵紀律：每個 action mp4 都過 SSIM check、跑完無縫接回 idle 第 1 偵
 *
 * Spec: docs/v0.8-multi-state-animation-spec.md § 4.2
 */
(function (global) {
  "use strict";

  var ANIMATION_POOL = {
    "idle":          "/static/sophie-idle.mp4",
    "speaking":      "/static/sophie-speaking.mp4",
    "task-received": "/static/sophie-task-received.mp4",
    "task-handoff":  "/static/sophie-task-handoff.mp4"
    // thinking / happy / impressed / yawn = 缺、fallback 到 idle silent
  };

  var ACTION_STATES = ["speaking", "task-received", "task-handoff"];
  var IDLE_SRC = ANIMATION_POOL["idle"];

  function AnimationPool(videoEl) {
    if (!videoEl) {
      console.warn("[animPool] no video element supplied");
      return;
    }
    this.video = videoEl;
    this.currentState = "idle";
    this._preloaders = {};
    this._endHandler = null;
    this._initIdle();
    this._preloadActions();
  }

  AnimationPool.prototype._initIdle = function () {
    // 預設 idle autoplay loop muted
    try {
      if (this.video.getAttribute("src") !== IDLE_SRC) {
        this.video.src = IDLE_SRC;
      }
    } catch (e) {}
    this.video.loop = true;
    this.video.muted = true;
    this.video.autoplay = true;
    this.video.setAttribute("preload", "auto");
    var p = this.video.play();
    if (p && p.then) { p.catch(function () {}); }
    this._log("idle init OK src=" + IDLE_SRC);
  };

  // 預載 3 個 action mp4 (HEAD-style fetch via hidden <video preload="auto">)
  // 避免切 src 時等下載卡頓
  AnimationPool.prototype._preloadActions = function () {
    var self = this;
    ACTION_STATES.forEach(function (state) {
      var src = ANIMATION_POOL[state];
      var pre = document.createElement("video");
      pre.preload = "auto";
      pre.muted = true;
      pre.src = src;
      pre.style.display = "none";
      // 不 attach 到 DOM、純當 cache primer
      try { pre.load(); } catch (e) {}
      self._preloaders[state] = pre;
    });
    this._log("preload primed for " + ACTION_STATES.length + " action states");
  };

  // 觸發單次 action loop · 跑完自動回 idle
  AnimationPool.prototype.playAction = function (state) {
    if (state === "idle") return; // idle 永遠跑、不必觸發
    if (ACTION_STATES.indexOf(state) === -1) {
      // 缺的狀態 = silent fallback 到 idle (不報錯不切換)
      this._log("playAction fallback (state not in pool): " + state);
      return;
    }
    var self = this;
    var src = ANIMATION_POOL[state];
    if (!src) return;

    // 移除前一個 onended (避免疊加)
    if (this._endHandler) {
      this.video.removeEventListener("ended", this._endHandler);
      this._endHandler = null;
    }

    // 切到 action mp4 · loop=false · 跑一次
    try {
      this.video.src = src;
    } catch (e) {
      this._log("set src fail: " + e.message);
      this._returnToIdle();
      return;
    }
    this.video.loop = false;
    this.video.muted = true;
    var p = this.video.play();
    if (p && p.then) { p.catch(function (err) { self._log("play fail: " + err.message); }); }
    this.currentState = state;
    this._log("playAction -> " + state);

    // 動畫結束自動回 idle
    this._endHandler = function () {
      self._returnToIdle();
    };
    this.video.addEventListener("ended", this._endHandler, { once: true });
  };

  AnimationPool.prototype._returnToIdle = function () {
    try {
      this.video.src = IDLE_SRC;
    } catch (e) {}
    this.video.loop = true;
    this.video.muted = true;
    var p = this.video.play();
    if (p && p.then) { p.catch(function () {}); }
    this.currentState = "idle";
    if (this._endHandler) {
      this.video.removeEventListener("ended", this._endHandler);
      this._endHandler = null;
    }
    this._log("returnToIdle OK");
  };

  AnimationPool.prototype.getState = function () {
    return this.currentState;
  };

  AnimationPool.prototype._log = function (msg) {
    try { console.log("[animPool]", msg); } catch (e) {}
    // bridge 給 index.html 的 log() 若可用
    if (global.__sophie && typeof global.__sophie.log === "function") {
      try { global.__sophie.log("[animPool] " + msg); } catch (e) {}
    }
  };

  // 暴露 constructor (index.html 內手動 new)
  global.AnimationPool = AnimationPool;
  global.ANIMATION_POOL_STATES = ACTION_STATES.concat(["idle"]);
})(window);
