// castle/static/avatar-compositor.js
// Voice Path V1 Stable Presence - Avatar Compositor (single owner of video.src)
//
// Canonical intent shape (aligned with V1.5 markl):
//   {
//     type:        play_speaking | play_idle | play_action |
//                  play_lipsync_cached | play_lipsync_realtime |
//                  speech_state,
//     src:         <url>,
//     priority:    <0-100 number>,
//     owner:       <string>,
//     reason:      <string>,
//     state:       listening|thinking|speaking|interrupted|idle (speech_state only),
//     loop:        <bool>,
//     currentTime: <number>,
//     onEnded:     <function>,
//     onReady:     <function>,
//     sid:         <string>,
//     label:       <string>
//   }
//
// ES5 only (Safari 13 compat).
(function (global) {
  "use strict";

  var PRIORITY = {
    idle: 10,
    action: 30,
    speaking: 40,
    lipsync_cached: 80,
    lipsync_realtime: 90
  };

  var TYPE_MAP = {
    play_idle:             { mode: "idle",             defaultPriority: PRIORITY.idle,             defaultLoop: true,  muted: true },
    play_speaking:         { mode: "speaking",         defaultPriority: PRIORITY.speaking,         defaultLoop: true,  muted: true },
    play_action:           { mode: "action",           defaultPriority: PRIORITY.action,           defaultLoop: false, muted: true },
    play_lipsync_cached:   { mode: "lipsync_cached",   defaultPriority: PRIORITY.lipsync_cached,   defaultLoop: false, muted: true },
    play_lipsync_realtime: { mode: "lipsync_realtime", defaultPriority: PRIORITY.lipsync_realtime, defaultLoop: false, muted: true }
  };

  function nowMs() { return Date.now ? Date.now() : new Date().getTime(); }

  function Stats() {
    this.srcSwitchCount = 0;
    this.srcSwitchTimestamps = [];
    this.rejectedIntents = 0;
    this.lastIntent = null;
    this.lastRejectReason = "";
    this.intentCount = {};
  }
  Stats.prototype.recordSwitch = function () {
    this.srcSwitchCount++;
    var t = nowMs();
    this.srcSwitchTimestamps.push(t);
    var cutoff = t - 60000;
    while (this.srcSwitchTimestamps.length && this.srcSwitchTimestamps[0] < cutoff) {
      this.srcSwitchTimestamps.shift();
    }
  };
  Stats.prototype.switchesInLast = function (ms) {
    var t = nowMs() - ms;
    var n = 0;
    for (var i = 0; i < this.srcSwitchTimestamps.length; i++) {
      if (this.srcSwitchTimestamps[i] >= t) n++;
    }
    return n;
  };
  Stats.prototype.recordIntent = function (type) {
    this.intentCount[type] = (this.intentCount[type] || 0) + 1;
  };
  Stats.prototype.recordReject = function (reason) {
    this.rejectedIntents++;
    this.lastRejectReason = reason;
  };

  function AvatarCompositor(videoEl, opts) {
    if (!videoEl) throw new Error("[avatarCompositor] no video element supplied");
    opts = opts || {};
    this.video = videoEl;
    this.log = opts.log || function (msg) {
      try { console.log("[avatarCompositor]", msg); } catch (e) {}
    };
    this.defaultIdleSrc = opts.defaultIdleSrc || "/static/sophie-idle.mp4";
    this.defaultSpeakingSrc = opts.defaultSpeakingSrc || "/static/sophie-speaking.mp4";

    this.mode = "idle";
    this.owner = "boot";
    this.priority = 0;
    this.src = "";
    this.speechState = "idle";
    this.stats = new Stats();

    this._seq = 0;
    this._endHandler = null;
    this._readyHandler = null;
    this._timeoutTimer = null;
    this._endTimeoutTimer = null;

    this._cachedLipsyncForSid = {};
    this._allowSrcWrite = false;

    global.__sophieVisualMode = "idle";
    global.__sophieLipsyncActive = false;
  }

  AvatarCompositor.prototype.dispatch = function (intent) {
    if (!intent || typeof intent !== "object") {
      this.stats.recordReject("invalid intent");
      return false;
    }
    this.stats.recordIntent(intent.type || "unknown");
    this.stats.lastIntent = intent;

    if (intent.type === "speech_state") return this._handleSpeechState(intent);
    if (TYPE_MAP[intent.type]) return this._playIntent(intent, TYPE_MAP[intent.type]);

    this.stats.recordReject("unknown type: " + intent.type);
    this.log("dispatch reject - unknown type: " + intent.type);
    return false;
  };

  AvatarCompositor.prototype.registerCachedLipsync = function (sid, mp4Url) {
    if (!sid || !mp4Url) return;
    this._cachedLipsyncForSid[sid] = mp4Url;
  };
  AvatarCompositor.prototype.getCachedLipsync = function (sid) {
    return this._cachedLipsyncForSid[sid] || null;
  };
  AvatarCompositor.prototype.clearCachedLipsync = function (sid) {
    if (sid && this._cachedLipsyncForSid[sid]) delete this._cachedLipsyncForSid[sid];
  };

  AvatarCompositor.prototype._handleSpeechState = function (intent) {
    var newState = intent.state;
    if (!newState) return false;
    var prev = this.speechState;
    this.speechState = newState;
    this.log("speechState " + prev + " -> " + newState + " sid=" + (intent.sid || "-"));

    if (newState === "speaking") {
      var cached = intent.sid ? this._cachedLipsyncForSid[intent.sid] : null;
      if (cached) {
        return this._playIntent({
          type: "play_lipsync_cached",
          src: cached,
          owner: "speech-state-cache-hit",
          reason: "lipsync cache hit sid=" + intent.sid,
          sid: intent.sid
        }, TYPE_MAP.play_lipsync_cached);
      }
      return this._playIntent({
        type: "play_speaking",
        src: this.defaultSpeakingSrc,
        owner: "speech-state",
        reason: "speech_state speaking",
        sid: intent.sid
      }, TYPE_MAP.play_speaking);
    }

    if (newState === "idle" || newState === "listening") {
      if (this._isLipsyncActive()) {
        this.log("speech_state idle requested but lipsync active - defer");
        return true;
      }
      return this._playIntent({
        type: "play_idle",
        src: this.defaultIdleSrc,
        owner: "speech-state",
        reason: "speech_state " + newState
      }, TYPE_MAP.play_idle);
    }

    if (newState === "thinking") {
      this.log("speech_state thinking - V1 hold no switch");
      return true;
    }

    if (newState === "interrupted") {
      this._cleanupHandlers();
      return this._playIntent({
        type: "play_idle",
        src: this.defaultIdleSrc,
        owner: "speech-state-interrupted",
        reason: "interrupted by user"
      }, TYPE_MAP.play_idle);
    }

    return true;
  };

  AvatarCompositor.prototype._isLipsyncActive = function () {
    return this.mode === "lipsync_cached" || this.mode === "lipsync_realtime";
  };

  AvatarCompositor.prototype._playIntent = function (intent, typeMeta) {
    var mode = typeMeta.mode;
    var src = intent.src;
    if (!src) {
      this.stats.recordReject("no src for " + intent.type);
      return false;
    }

    var priority = typeof intent.priority === "number" ? intent.priority : typeMeta.defaultPriority;

    if (this._isLipsyncActive() && priority < this.priority) {
      this.stats.recordReject("locked by lipsync: " + intent.type);
      this.log("reject " + intent.type + " - locked by " + this.mode);
      return false;
    }

    var v = this.video;
    var sameSrc = false;
    try {
      var current = v.currentSrc || v.src || "";
      sameSrc = current.indexOf(src) !== -1;
    } catch (e) {}

    if (sameSrc && mode === this.mode && priority <= this.priority) {
      this.log("noop " + intent.type + " - same src+mode");
      return true;
    }

    var seq = ++this._seq;
    var loop = (typeof intent.loop === "boolean") ? intent.loop : typeMeta.defaultLoop;
    var muted = (typeof intent.muted === "boolean") ? intent.muted : typeMeta.muted;
    var self = this;

    this._cleanupHandlers();
    this.mode = mode;
    this.owner = intent.owner || intent.type;
    this.priority = priority;
    this.src = src;
    global.__sophieVisualMode = (mode === "lipsync_cached" || mode === "lipsync_realtime") ? "lipsync" : mode;
    global.__sophieLipsyncActive = this._isLipsyncActive();

    try {
      if (!sameSrc) {
        v.classList.add("is-switching");
        self._writeSrcInternal(src);
        this.stats.recordSwitch();
      }
      v.loop = !!loop;
      v.muted = muted !== false;
      v.autoplay = true;
      v.setAttribute("preload", "auto");

      if (sameSrc && (mode === "lipsync_cached" || mode === "lipsync_realtime")) {
        try { v.currentTime = Math.max(0, intent.currentTime || 0); } catch (e) {}
      }

      if (typeof intent.currentTime === "number" && intent.currentTime > 0 && !sameSrc) {
        var seekOnMeta = function () {
          try {
            v.removeEventListener("loadedmetadata", seekOnMeta);
            if (seq !== self._seq) return;
            if (v.duration > 0) {
              v.currentTime = Math.min(intent.currentTime, Math.max(0, v.duration - 0.3));
            }
          } catch (e) {}
        };
        v.addEventListener("loadedmetadata", seekOnMeta, { once: true });
      }

      var finished = false;
      var finishPlayback = function (source) {
        if (finished || seq !== self._seq) return;
        finished = true;
        if (self._endTimeoutTimer) {
          clearTimeout(self._endTimeoutTimer);
          self._endTimeoutTimer = null;
        }
        if (mode === "lipsync_cached" || mode === "lipsync_realtime") {
          global.__sophieLipsyncActive = false;
          if (self.mode === mode) {
            if (self.speechState === "speaking") {
              self._playIntent({
                type: "play_speaking",
                src: self.defaultSpeakingSrc,
                owner: "lipsync-ended"
              }, TYPE_MAP.play_speaking);
            } else {
              self._playIntent({
                type: "play_idle",
                src: self.defaultIdleSrc,
                owner: "lipsync-ended"
              }, TYPE_MAP.play_idle);
            }
          }
        }
        self.log("end " + mode + " - " + (intent.label || src) + " via=" + source);
        if (typeof intent.onEnded === "function") {
          try { intent.onEnded(); } catch (e) {}
        }
      };

      if (mode === "lipsync_cached" || mode === "lipsync_realtime") {
        var armLipsyncEndTimeout = function () {
          if (seq !== self._seq) return;
          if (self._endTimeoutTimer) clearTimeout(self._endTimeoutTimer);
          var dur = 0, cur = 0;
          try {
            dur = isFinite(v.duration) ? v.duration : 0;
            cur = isFinite(v.currentTime) ? v.currentTime : 0;
          } catch (e) {}
          var ms = dur > 0 ? Math.max(900, Math.ceil((dur - cur) * 1000) + 600) : 3500;
          self._endTimeoutTimer = setTimeout(function () {
            finishPlayback("timeout");
          }, ms);
        };
        if (v.readyState >= 1) setTimeout(armLipsyncEndTimeout, 0);
        else v.addEventListener("loadedmetadata", armLipsyncEndTimeout, { once: true });
      }

      this._readyHandler = function () {
        if (seq !== self._seq) return;
        try { v.classList.remove("is-switching"); } catch (e) {}
        if (typeof intent.onReady === "function") {
          try { intent.onReady(); } catch (e) {}
        }
      };
      v.addEventListener("canplay", this._readyHandler, { once: true });
      this._timeoutTimer = setTimeout(function () {
        if (seq !== self._seq) return;
        try { v.classList.remove("is-switching"); } catch (e) {}
      }, intent.readyTimeout || 700);

      this._endHandler = function () {
        if (seq !== self._seq) return;
        finishPlayback("ended");
      };
      v.addEventListener("ended", this._endHandler, { once: true });

      var p = v.play();
      if (p && p["catch"]) {
        p["catch"](function (err) {
          self.log("play fail " + mode + " - " + (err && err.message ? err.message : "unknown"));
        });
      }
      this.log("play " + mode + " - " + (intent.label || intent.reason || src) + " owner=" + this.owner + " p=" + priority);
      return true;
    } catch (e) {
      try { v.classList.remove("is-switching"); } catch (ignore) {}
      this.log("play error " + mode + " - " + e.message);
      return false;
    }
  };

  AvatarCompositor.prototype._cleanupHandlers = function () {
    if (!this.video) return;
    if (this._endHandler) {
      try { this.video.removeEventListener("ended", this._endHandler); } catch (e) {}
      this._endHandler = null;
    }
    if (this._readyHandler) {
      try { this.video.removeEventListener("canplay", this._readyHandler); } catch (e) {}
      this._readyHandler = null;
    }
    if (this._timeoutTimer) { clearTimeout(this._timeoutTimer); this._timeoutTimer = null; }
    if (this._endTimeoutTimer) { clearTimeout(this._endTimeoutTimer); this._endTimeoutTimer = null; }
  };

  // src URL scheme + prefix allowlist | Suliman Tier B Seg 4 P1 patch
  // Allowed:
  //   1. /static/...mp4     (relative same-origin static asset)
  //   2. /lipsync/...mp4    (relative same-origin lipsync cache)
  //   3. blob:...           (runtime generated lipsync · WebRTC / MediaSource)
  //   4. <origin>/static/... or <origin>/lipsync/... (absolute same-origin)
  //   5. https://edwardt0303--castle-voice-engine-fastapi-app.modal.run/... (modal prod absolute)
  // Rejected: javascript: | data: | cross-origin http(s) | empty | non-string
  var _ALLOWED_SAME_ORIGIN_PREFIXES = ["/static/", "/lipsync/"];
  var _ALLOWED_ABS_ORIGIN = "https://edwardt0303--castle-voice-engine-fastapi-app.modal.run";
  function _validateSrc(src) {
    if (typeof src !== "string" || src.length === 0) {
      return { ok: false, reason: "empty or non-string src" };
    }
    if (src.indexOf("blob:") === 0) return { ok: true };
    for (var i = 0; i < _ALLOWED_SAME_ORIGIN_PREFIXES.length; i++) {
      if (src.indexOf(_ALLOWED_SAME_ORIGIN_PREFIXES[i]) === 0) return { ok: true };
    }
    try {
      var pageOrigin = (global.location && global.location.origin) || "";
      if (pageOrigin && src.indexOf(pageOrigin + "/static/") === 0) return { ok: true };
      if (pageOrigin && src.indexOf(pageOrigin + "/lipsync/") === 0) return { ok: true };
    } catch (e) {}
    if (src.indexOf(_ALLOWED_ABS_ORIGIN + "/static/") === 0) return { ok: true };
    if (src.indexOf(_ALLOWED_ABS_ORIGIN + "/lipsync/") === 0) return { ok: true };
    return { ok: false, reason: "disallowed src scheme/origin: " + src.slice(0, 60) };
  }

  AvatarCompositor.prototype._writeSrcInternal = function (src) {
    var v = _validateSrc(src);
    if (!v.ok) {
      this.stats.recordReject(v.reason);
      try { console.error("[avatarCompositor] src allowlist REJECT | " + v.reason); } catch (e) {}
      return;
    }
    this._allowSrcWrite = true;
    try { this.video.src = src; } finally { this._allowSrcWrite = false; }
  };

  // Test hook | expose validator for compositor-test.html unit test
  AvatarCompositor._validateSrcForTest = _validateSrc;

  // Dev/test only: forcibly clear lipsync lock and reset to idle.
  // Production never calls this; lipsync naturally ends via clip onEnded.
  AvatarCompositor.prototype.forceReset = function (reason) {
    this._cleanupHandlers();
    this.mode = "idle";
    this.owner = "force-reset";
    this.priority = 0;
    this.speechState = "idle";
    global.__sophieVisualMode = "idle";
    global.__sophieLipsyncActive = false;
    this.log("forceReset reason=" + (reason || "-"));
  };

  AvatarCompositor.prototype.getState = function () {
    return {
      mode: this.mode,
      owner: this.owner,
      src: this.src,
      priority: this.priority,
      speechState: this.speechState,
      lipsyncActive: this._isLipsyncActive(),
      srcSwitchCount: this.stats.srcSwitchCount,
      switchesLast60s: this.stats.switchesInLast(60000),
      rejectedIntents: this.stats.rejectedIntents,
      lastRejectReason: this.stats.lastRejectReason,
      intentCount: this.stats.intentCount,
      pendingCachedSids: Object.keys(this._cachedLipsyncForSid).length
    };
  };

  // Back-compat shims (let v2.0.6 callers keep working unchanged)
  AvatarCompositor.prototype.playIdle = function (src, owner) {
    return this.dispatch({
      type: "play_idle",
      src: src || this.defaultIdleSrc,
      owner: owner || "compat-playIdle"
    });
  };
  AvatarCompositor.prototype.playSpeaking = function (src, owner) {
    return this.dispatch({
      type: "play_speaking",
      src: src || this.defaultSpeakingSrc,
      owner: owner || "compat-playSpeaking"
    });
  };
  AvatarCompositor.prototype.playAction = function (src, label, onEnded) {
    return this.dispatch({
      type: "play_action",
      src: src,
      owner: "compat-playAction",
      label: label,
      onEnded: onEnded
    });
  };
  AvatarCompositor.prototype.playLipsync = function (src, label, currentTime, onEnded) {
    return this.dispatch({
      type: "play_lipsync_cached",
      src: src,
      owner: "compat-playLipsync",
      label: label,
      currentTime: currentTime || 0,
      onEnded: onEnded
    });
  };
  AvatarCompositor.prototype.isLipsyncActive = function () {
    return this._isLipsyncActive();
  };
  AvatarCompositor.prototype.canPlay = function () { return true; };
  AvatarCompositor.prototype.play = function (req) {
    if (!req || !req.mode) return false;
    var map = {
      idle: "play_idle",
      speaking: "play_speaking",
      action: "play_action",
      lipsync: "play_lipsync_cached"
    };
    var type = map[req.mode];
    if (!type) return false;
    return this.dispatch({
      type: type,
      src: req.src,
      owner: req.owner,
      label: req.label,
      currentTime: req.currentTime,
      loop: req.loop,
      onEnded: req.onEnded,
      onReady: req.onReady,
      priority: req.priority
    });
  };

  // Runtime guard: detect illegal direct video.src writes
  // Default = tolerant (warn only). Strict mode (dev) blocks the write.
  AvatarCompositor.installSrcGuard = function (videoEl, compositor, opts) {
    opts = opts || {};
    if (!videoEl || videoEl.__sophieGuardInstalled) return;
    videoEl.__sophieGuardInstalled = true;

    var proto = HTMLMediaElement.prototype;
    var nativeDesc = Object.getOwnPropertyDescriptor(proto, "src");
    if (!nativeDesc || !nativeDesc.set) {
      console.warn("[avatarCompositor] src guard skipped - no native descriptor");
      return;
    }
    var nativeSet = nativeDesc.set;
    var nativeGet = nativeDesc.get;

    Object.defineProperty(videoEl, "src", {
      configurable: true,
      get: function () { return nativeGet.call(this); },
      set: function (value) {
        var allowed = (compositor && compositor._allowSrcWrite === true);
        if (!allowed) {
          var msg = "[avatarCompositor] ILLEGAL direct video.src write - value=" + value;
          try { console.warn(msg); } catch (e) {}
          if (compositor && compositor.stats) {
            compositor.stats.recordReject("illegal direct src write: " + value);
          }
          if (opts.strict === true) return;
        }
        nativeSet.call(this, value);
      }
    });
  };

  global.AvatarCompositor = AvatarCompositor;
  if (!global.AvatarDirector) global.AvatarDirector = AvatarCompositor;
})(window);
