// castle/static/avatar-director.js
// Voice Path v2.0.5 · single-owner avatar visual runtime.
(function (global) {
  "use strict";

  var PRIORITY = {
    idle: 10,
    action: 30,
    speaking: 40,
    lipsync: 90
  };

  function nowMs() { return Date.now ? Date.now() : new Date().getTime(); }

  function AvatarDirector(videoEl, opts) {
    opts = opts || {};
    this.video = videoEl;
    this.log = opts.log || function (msg) {
      try { console.log("[avatarDirector]", msg); } catch (e) {}
    };
    this.mode = "idle";
    this.owner = "boot";
    this.priority = PRIORITY.idle;
    this.src = "";
    this._seq = 0;
    this._endHandler = null;
    this._readyHandler = null;
    this._timeout = null;
    global.__sophieVisualMode = "idle";
    global.__sophieLipsyncActive = false;
  }

  AvatarDirector.prototype._cleanupHandlers = function () {
    if (!this.video) return;
    if (this._endHandler) {
      try { this.video.removeEventListener("ended", this._endHandler); } catch (e) {}
      this._endHandler = null;
    }
    if (this._readyHandler) {
      try { this.video.removeEventListener("canplay", this._readyHandler); } catch (e) {}
      this._readyHandler = null;
    }
    if (this._timeout) {
      clearTimeout(this._timeout);
      this._timeout = null;
    }
  };

  AvatarDirector.prototype.isLipsyncActive = function () {
    return this.mode === "lipsync" || !!global.__sophieLipsyncActive;
  };

  AvatarDirector.prototype.canPlay = function (mode, priority) {
    priority = typeof priority === "number" ? priority : (PRIORITY[mode] || 0);
    if (this.isLipsyncActive() && mode !== "lipsync" && priority < PRIORITY.lipsync) {
      return false;
    }
    return true;
  };

  AvatarDirector.prototype.play = function (req) {
    req = req || {};
    var mode = req.mode || "idle";
    var src = req.src || "";
    if (!this.video || !src) return false;

    var priority = typeof req.priority === "number" ? req.priority : (PRIORITY[mode] || 0);
    if (!this.canPlay(mode, priority)) {
      this.log("skip " + mode + " · locked by " + this.mode + " · src=" + src);
      return false;
    }

    var v = this.video;
    var seq = ++this._seq;
    var sameSrc = false;
    try {
      var current = v.currentSrc || v.src || "";
      sameSrc = current.indexOf(src) !== -1;
    } catch (e) {}

    this._cleanupHandlers();
    this.mode = mode;
    this.owner = req.owner || mode;
    this.priority = priority;
    this.src = src;
    global.__sophieVisualMode = mode;
    global.__sophieLipsyncActive = mode === "lipsync";

    try {
      if (!sameSrc) {
        v.classList.add("is-switching");
        v.src = src;
      }
      v.loop = !!req.loop;
      v.muted = req.muted !== false;
      v.autoplay = true;
      v.setAttribute("preload", "auto");

      if (typeof req.currentTime === "number" && req.currentTime > 0) {
        var seekOnMeta = function () {
          try {
            v.removeEventListener("loadedmetadata", seekOnMeta);
            if (seq !== this._seq) return;
            if (v.duration > 0) {
              v.currentTime = Math.min(req.currentTime, Math.max(0, v.duration - 0.3));
            }
          } catch (e) {}
        }.bind(this);
        v.addEventListener("loadedmetadata", seekOnMeta, { once: true });
      }

      this._readyHandler = function () {
        if (seq !== this._seq) return;
        try { v.classList.remove("is-switching"); } catch (e) {}
        if (typeof req.onReady === "function") req.onReady();
      }.bind(this);
      v.addEventListener("canplay", this._readyHandler, { once: true });
      this._timeout = setTimeout(function () {
        if (seq !== this._seq) return;
        try { v.classList.remove("is-switching"); } catch (e) {}
      }.bind(this), req.readyTimeout || 700);

      this._endHandler = function () {
        if (seq !== this._seq) return;
        if (mode === "lipsync") {
          global.__sophieLipsyncActive = false;
        }
        if (typeof req.onEnded === "function") req.onEnded();
      }.bind(this);
      v.addEventListener("ended", this._endHandler, { once: true });

      var p = v.play();
      if (p && p["catch"]) {
        p["catch"](function (err) {
          this.log("play fail " + mode + " · " + (err && err.message ? err.message : "unknown"));
        }.bind(this));
      }
      this.log("play " + mode + " · " + (req.label || src) + " · owner=" + this.owner + " · t=" + nowMs());
      return true;
    } catch (e) {
      try { v.classList.remove("is-switching"); } catch (ignore) {}
      this.log("play error " + mode + " · " + e.message);
      return false;
    }
  };

  AvatarDirector.prototype.playIdle = function (src, owner) {
    return this.play({ mode: "idle", src: src, loop: true, owner: owner || "idle" });
  };

  AvatarDirector.prototype.playSpeaking = function (src, owner) {
    return this.play({ mode: "speaking", src: src, loop: true, owner: owner || "speaking" });
  };

  AvatarDirector.prototype.playAction = function (src, label, onEnded) {
    return this.play({ mode: "action", src: src, loop: false, owner: "animation-pool", label: label, onEnded: onEnded });
  };

  AvatarDirector.prototype.playLipsync = function (src, label, currentTime, onEnded) {
    return this.play({
      mode: "lipsync",
      src: src,
      loop: false,
      owner: "lipsync",
      label: label,
      currentTime: currentTime || 0,
      priority: PRIORITY.lipsync,
      onEnded: onEnded
    });
  };

  AvatarDirector.prototype.getState = function () {
    return {
      mode: this.mode,
      owner: this.owner,
      src: this.src,
      priority: this.priority,
      lipsyncActive: this.isLipsyncActive()
    };
  };

  global.AvatarDirector = AvatarDirector;
})(window);
