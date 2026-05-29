// castle/static/avatar-stage.js
// Voice Path · AvatarStage · 單一管家 (single owner) for the <video> element.
//
// 為什麼有這支:
//   舊架構有 6 段程式各自搶同一個 <video> (AvatarDirector / animation-pool idle rotator /
//   pre-call rotator / cold-start watchdog / preroll greeting / speaking-lipsync)。
//   冷開機 / 慢網路時撞在一起 → play() interrupted → 卡死 / 黑屏 / 招呼被蓋。
//
//   AvatarStage = 唯一能碰 video.src / .play() 的程式。所有要轉台的人跟它「下單」、
//   每個請求拿一張號碼牌 (序號)，只有最新號碼牌能動 video、舊的自動作廢 →
//   不可能再互相打斷。
//
// 啟用方式: 只有 ?controller=new 時 index.html 才用 AvatarStage。
//   預設 / ?controller=old 完全不碰這支、走現狀 (今天止血的陽春版)。
//
// 本輪 (階段 1) 只開一個門: showIdle()。招呼 / 講話 / 嘴對齊留階段 2-3。
(function (global) {
  "use strict";

  function nowMs() { return Date.now ? Date.now() : new Date().getTime(); }

  // 手機輕量偵測 (沿用既有 pattern · 階段 1 暫不分流、保留 flag 給後續階段用)
  var IS_MOBILE = false;
  try {
    IS_MOBILE = /Mobi|Android|iPhone|iPad|iPod/i.test(global.navigator && global.navigator.userAgent || "");
  } catch (e) {}

  function AvatarStage(videoEl, opts) {
    opts = opts || {};
    this.video = videoEl;
    this.log = opts.log || function (msg) {
      try { console.log("[AvatarStage]", msg); } catch (e) {}
    };
    this.isMobile = IS_MOBILE;
    this.mode = "boot";          // boot → idle (階段 2-3 再加 greeting / speaking / lipsync)
    this.owner = "boot";
    this.src = "";
    this._seq = 0;               // 號碼牌計數器 · 只有最新號碼牌能動 video
    this._readyHandler = null;
    this._switchTimer = null;
    this.log("init · isMobile=" + this.isMobile);
  }

  // 拿一張新號碼牌、作廢之前所有未完成的 handler。回傳這次的序號。
  AvatarStage.prototype._takeTicket = function () {
    var seq = ++this._seq;
    if (this._readyHandler && this.video) {
      try { this.video.removeEventListener("canplay", this._readyHandler); } catch (e) {}
      this._readyHandler = null;
    }
    if (this._switchTimer) {
      clearTimeout(this._switchTimer);
      this._switchTimer = null;
    }
    return seq;
  };

  // 內部統一切換入口 · 唯一碰 video.src / .play() 的地方。
  //   req: { mode, src, loop, muted, owner, readyTimeout, onReady }
  AvatarStage.prototype._apply = function (req) {
    req = req || {};
    var v = this.video;
    var src = req.src || "";
    if (!v || !src) {
      this.log("apply skip · no video or src");
      return false;
    }

    var seq = this._takeTicket();
    var self = this;

    var current = "";
    try { current = v.currentSrc || v.src || ""; } catch (e) {}
    var sameSrc = current.indexOf(src) !== -1;

    this.mode = req.mode || this.mode;
    this.owner = req.owner || this.mode;
    this.src = src;

    try {
      v.loop = req.loop !== false;       // 待機預設 loop
      v.muted = req.muted !== false;     // 待機預設 muted
      v.autoplay = true;
      v.setAttribute("playsinline", "");

      if (!sameSrc) {
        try { v.classList.add("is-switching"); } catch (e) {}
        v.src = src;
        try { v.load(); } catch (e) {}
      }

      // ready handler · 只有最新號碼牌能生效
      this._readyHandler = function () {
        if (seq !== self._seq) return;          // 舊號碼牌 · 作廢
        try { v.classList.remove("is-switching"); } catch (e) {}
        if (typeof req.onReady === "function") {
          try { req.onReady(); } catch (e) {}
        }
      };
      v.addEventListener("canplay", this._readyHandler, { once: true });

      // 保險 timer · readyTimeout 後即使沒 canplay 也清 is-switching (避免卡半透明)
      this._switchTimer = setTimeout(function () {
        if (seq !== self._seq) return;
        try { v.classList.remove("is-switching"); } catch (e) {}
      }, req.readyTimeout || 700);

      // 只在「換了 src」或「video 目前停住」時才主動 play()。
      //   sameSrc 且已在播 = native autoplay / 上一個 showIdle 已接手 → 不重複 play()
      //   (重複 play() 在 readyState 未到時會 race → play() interrupted by new load request)。
      var needPlay = !sameSrc || v.paused;
      if (needPlay) {
        var p = v.play();
        if (p && p["catch"]) {
          p["catch"](function (err) {
            if (seq !== self._seq) return;       // 舊號碼牌的 play reject · 不嚇人
            // readyState 未到時的 interrupted 屬已知無害 (native autoplay 仍接手) · 降級為 debug 不嚇人
            self.log("play deferred " + req.mode + " · " + (err && err.message ? err.message : "unknown"));
          });
        }
      }
      this.log("apply " + req.mode + " · owner=" + this.owner + " · src=" + src + " · seq=" + seq + " · t=" + nowMs());
      return true;
    } catch (e) {
      try { v.classList.remove("is-switching"); } catch (ignore) {}
      this.log("apply error " + req.mode + " · " + e.message);
      return false;
    }
  };

  // ===== 對外的門 (階段 1 只開 showIdle) =====

  // 待機 = 單支 idle loop · muted · loop。再呼叫同 src 不重切 (sameSrc 判斷)。
  AvatarStage.prototype.showIdle = function (src) {
    return this._apply({
      mode: "idle",
      src: src || "/static/sophie-idle.mp4",
      loop: true,
      muted: true,
      owner: "idle"
    });
  };

  // freeze · 停在當前畫面 (階段 2+ 用 · 先放著、本輪不依賴)
  AvatarStage.prototype.freeze = function () {
    var seq = this._takeTicket();
    this.mode = "freeze";
    this.owner = "freeze";
    try { if (this.video) this.video.pause(); } catch (e) {}
    this.log("freeze · seq=" + seq);
    return true;
  };

  AvatarStage.prototype.getState = function () {
    return {
      mode: this.mode,
      owner: this.owner,
      src: this.src,
      seq: this._seq,
      isMobile: this.isMobile
    };
  };

  global.AvatarStage = AvatarStage;
})(window);
