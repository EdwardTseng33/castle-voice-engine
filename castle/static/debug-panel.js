// castle/static/debug-panel.js
// Voice Path V1 Stable Presence - Avatar Debug Panel (dev/cron overlay)
//
// Right-top overlay showing live Compositor + SpeechState + latency + cache stats.
// Render is read-only · panel never dispatches intents itself.
//
// Toggle rules (per design book v2 §2.5):
//   - prod default OFF
//   - URL param ?debug=1 turns ON
//   - localhost auto ON
//   - cron acceptance forces ON via window.__sophieDebugForceOn = true (before init)
//
// Public API:
//   var panel = new AvatarDebugPanel(compositor, speechStateReducer, opts);
//   panel.show() / panel.hide() / panel.toggle()
//   panel.getMetrics()  -> consumable by /dev/verdict_collect cron
//
// ES5 only.
(function (global) {
  "use strict";

  function nowMs() { return Date.now ? Date.now() : new Date().getTime(); }

  function shouldAutoEnable() {
    if (global.__sophieDebugForceOn === true) return true;
    try {
      var u = new URL(global.location.href);
      if (u.searchParams.get("debug") === "1") return true;
      if (u.hostname === "localhost" || u.hostname === "127.0.0.1") return true;
    } catch (e) {}
    return false;
  }

  function el(tag, attrs, text) {
    var n = document.createElement(tag);
    if (attrs) {
      for (var k in attrs) {
        if (Object.prototype.hasOwnProperty.call(attrs, k)) {
          if (k === "style") n.setAttribute("style", attrs[k]);
          else n.setAttribute(k, attrs[k]);
        }
      }
    }
    if (text !== undefined) n.textContent = text;
    return n;
  }

  function AvatarDebugPanel(compositor, speechState, opts) {
    opts = opts || {};
    this.compositor = compositor;
    this.speechState = speechState;
    this.videoEl = (compositor && compositor.video) || null;

    this.enabled = (typeof opts.enabled === "boolean") ? opts.enabled : shouldAutoEnable();
    this.refreshMs = opts.refreshMs || 250;

    this.root = null;
    this.lines = {};
    this._tick = null;

    // Acceptance metrics (cron uses these)
    this._timeupdateLast = 0;
    this._timeupdateCountByWindow = []; // {ts, count}
    this._audioDoneTs = 0;
    this._firstSendTs = 0;
    this._firstVideoTimeupdateAfterSendTs = 0;

    this._installVideoListeners();
    this._installSpeechStateListener();

    if (this.enabled) this._render();
  }

  AvatarDebugPanel.prototype._installVideoListeners = function () {
    if (!this.videoEl) return;
    var self = this;
    this.videoEl.addEventListener("timeupdate", function () {
      self._timeupdateLast = nowMs();
      // track count per second
      var bucket = Math.floor(self._timeupdateLast / 1000);
      var last = self._timeupdateCountByWindow.length
        ? self._timeupdateCountByWindow[self._timeupdateCountByWindow.length - 1]
        : null;
      if (last && last.bucket === bucket) last.count++;
      else self._timeupdateCountByWindow.push({ bucket: bucket, count: 1 });
      // keep last 120 buckets (2 min)
      while (self._timeupdateCountByWindow.length > 120) self._timeupdateCountByWindow.shift();

      // first timeupdate after send mark (acceptance metric 4)
      if (self._firstSendTs > 0 && self._firstVideoTimeupdateAfterSendTs === 0) {
        self._firstVideoTimeupdateAfterSendTs = self._timeupdateLast;
      }
    });
  };

  AvatarDebugPanel.prototype._installSpeechStateListener = function () {
    var self = this;
    global.addEventListener("sophie:speechState", function (e) {
      if (!e || !e.detail) return;
      if (e.detail.state === "speaking" && self._firstSendTs > 0 && self._firstVideoTimeupdateAfterSendTs === 0) {
        // 對齊 acceptance metric 2: audio.done 後 0.5s 內 timeupdate
        // 也可以用 speaking transition 作為「audio 開始輸出」近似標
      }
    });
  };

  // Called by external code when client sends mic chunk to OpenAI (mark t0)
  AvatarDebugPanel.prototype.markFirstSend = function () {
    if (this._firstSendTs === 0) this._firstSendTs = nowMs();
  };
  AvatarDebugPanel.prototype.markAudioDone = function () {
    this._audioDoneTs = nowMs();
  };
  AvatarDebugPanel.prototype.resetMarks = function () {
    this._firstSendTs = 0;
    this._firstVideoTimeupdateAfterSendTs = 0;
    this._audioDoneTs = 0;
  };

  AvatarDebugPanel.prototype._render = function () {
    if (this.root) return;
    var self = this;
    var root = el("div", {
      id: "sophie-debug-panel",
      style: [
        "position:fixed",
        "top:8px",
        "right:8px",
        "z-index:99999",
        "width:280px",
        "background:rgba(0,0,0,0.78)",
        "color:#cfeaff",
        "font:11px ui-monospace, Menlo, Consolas, monospace",
        "padding:10px 12px",
        "border-radius:6px",
        "border:1px solid #224",
        "box-shadow:0 4px 16px rgba(0,0,0,0.4)",
        "line-height:1.5",
        "pointer-events:auto",
        "user-select:none"
      ].join(";")
    });

    var title = el("div", {
      style: "color:#fff;font-weight:600;margin-bottom:4px;display:flex;justify-content:space-between"
    });
    title.appendChild(el("span", null, "[Compositor]"));
    var close = el("span", { style: "cursor:pointer;color:#888" }, "x");
    close.addEventListener("click", function () { self.hide(); });
    title.appendChild(close);
    root.appendChild(title);

    var rows = [
      "mode", "owner", "speechState", "src",
      "switches", "rejected",
      "lipsync", "latency", "audioDone", "timeupdate"
    ];
    for (var i = 0; i < rows.length; i++) {
      var key = rows[i];
      var line = el("div", { style: "white-space:nowrap;overflow:hidden;text-overflow:ellipsis" });
      var lbl = el("span", { style: "color:#789;display:inline-block;width:84px" }, key);
      var val = el("span", { style: "color:#cfeaff" }, "-");
      line.appendChild(lbl);
      line.appendChild(val);
      root.appendChild(line);
      this.lines[key] = val;
    }

    document.body.appendChild(root);
    this.root = root;

    this._tick = setInterval(function () { self._refresh(); }, this.refreshMs);
  };

  AvatarDebugPanel.prototype._refresh = function () {
    if (!this.root || !this.compositor) return;
    var s = this.compositor.getState();
    var ss = this.speechState ? this.speechState.getState() : null;

    this._setLine("mode", s.mode + " p=" + s.priority);
    this._setLine("owner", s.owner || "-");
    this._setLine("speechState", ss ? ss.state : "-");
    this._setLine("src", this._shortSrc(s.src));
    this._setLine("switches", s.srcSwitchCount + " (60s: " + s.switchesLast60s + ")");
    this._setLine("rejected", String(s.rejectedIntents));

    var lipsyncTxt = s.lipsyncActive ? "ACTIVE (" + s.mode + ")" : "off";
    this._setLine("lipsync", lipsyncTxt + " · cached:" + s.pendingCachedSids);

    var latTxt = ss && ss.lastLatencyMs > 0 ? (ss.lastLatencyMs + "ms") : "-";
    this._setLine("latency", latTxt);

    var audioDoneTxt = this._audioDoneTs > 0 ? ((nowMs() - this._audioDoneTs) + "ms ago") : "-";
    this._setLine("audioDone", audioDoneTxt);

    var tu = this._timeupdateLast > 0 ? ((nowMs() - this._timeupdateLast) + "ms ago") : "-";
    this._setLine("timeupdate", tu);
  };

  AvatarDebugPanel.prototype._setLine = function (key, val) {
    var node = this.lines[key];
    if (node) node.textContent = val;
  };

  AvatarDebugPanel.prototype._shortSrc = function (src) {
    if (!src) return "-";
    var idx = src.lastIndexOf("/");
    return idx >= 0 ? src.substring(idx + 1) : src;
  };

  AvatarDebugPanel.prototype.show = function () {
    this.enabled = true;
    this._render();
  };
  AvatarDebugPanel.prototype.hide = function () {
    if (this.root) {
      try { document.body.removeChild(this.root); } catch (e) {}
      this.root = null;
    }
    if (this._tick) { clearInterval(this._tick); this._tick = null; }
  };
  AvatarDebugPanel.prototype.toggle = function () {
    if (this.root) this.hide();
    else this.show();
  };

  // Acceptance cron consumes this · returns 4 metrics defined in design book §3.1
  AvatarDebugPanel.prototype.getMetrics = function () {
    var s = this.compositor ? this.compositor.getState() : {};
    var ss = this.speechState ? this.speechState.getState() : {};

    var timeupdateCountAfterAudioDone = 0;
    if (this._audioDoneTs > 0) {
      // count timeupdate buckets in the 500ms after audioDone
      var startBucket = Math.floor(this._audioDoneTs / 1000);
      for (var i = 0; i < this._timeupdateCountByWindow.length; i++) {
        var entry = this._timeupdateCountByWindow[i];
        if (entry.bucket >= startBucket && entry.bucket <= startBucket + 1) {
          timeupdateCountAfterAudioDone += entry.count;
        }
      }
    }

    var firstSendToTimeupdateMs = this._firstSendTs > 0 && this._firstVideoTimeupdateAfterSendTs > 0
      ? (this._firstVideoTimeupdateAfterSendTs - this._firstSendTs) : null;

    return {
      // Metric 1: 不閃 (switches in last 60s < 6)
      metric_1_switchesLast60s: s.switchesLast60s || 0,
      metric_1_pass: (s.switchesLast60s || 0) < 6,

      // Metric 2: 講話有動 (audio.done 後 0.5s 內 timeupdate >= 5)
      metric_2_timeupdatesAfterAudioDone: timeupdateCountAfterAudioDone,
      metric_2_pass: timeupdateCountAfterAudioDone >= 5,

      // Metric 3: 狀態正確 (mode + speechState 一致 · 同步快照)
      metric_3_modeAlignsSpeech: alignsState(s.mode, ss.state),
      metric_3_pass: alignsState(s.mode, ss.state),

      // Metric 4: 延遲達標 (首句 send -> timeupdate < 2.0s)
      metric_4_firstSendToTimeupdateMs: firstSendToTimeupdateMs,
      metric_4_pass: firstSendToTimeupdateMs !== null && firstSendToTimeupdateMs < 2000,

      // raw
      rawCompositor: s,
      rawSpeechState: ss
    };
  };

  function alignsState(mode, speechState) {
    if (mode === "speaking" && (speechState === "speaking" || speechState === "thinking")) return true;
    if (mode === "idle" && (speechState === "idle" || speechState === "listening" || speechState === "interrupted")) return true;
    if (mode === "lipsync_cached" || mode === "lipsync_realtime") return speechState === "speaking";
    if (mode === "action") return true; // action is transient · cannot conflict
    return false;
  }

  global.AvatarDebugPanel = AvatarDebugPanel;
})(window);
