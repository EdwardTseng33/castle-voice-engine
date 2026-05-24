// ===== v0.7 P2.2 . MuseTalk fMP4 streaming player (calcifer 2026-05-24) =====
// Plays multipart/mixed chunked fMP4 from /brain/musetalk_generate_streaming via MediaSource.
// Toggle: window.castleUseStreaming (default false until Phase 3 measurement passes).
// Old endpoint /brain/musetalk_generate kept as fallback.
// Backend ref: castle/server/brain_endpoints.py L1257-1369
// ES5 only.

(function () {
  "use strict";

  var BOUNDARY = "castlefmp4";
  var MIME = "video/mp4; codecs=" + String.fromCharCode(34) + "avc1.42E01E,mp4a.40.2" + String.fromCharCode(34);
  var CRLF = String.fromCharCode(13) + String.fromCharCode(10);

  function canUseStreaming() {
    if (typeof window === "undefined") return false;
    if (!("MediaSource" in window)) return false;
    try {
      if (typeof window.MediaSource.isTypeSupported !== "function") return false;
      if (!window.MediaSource.isTypeSupported(MIME)) return false;
    } catch (e) { return false; }
    if (!("ReadableStream" in window)) return false;
    if (typeof TextDecoder === "undefined") return false;
    return true;
  }
  window.__sophieStreamingCapable = canUseStreaming();
  if (typeof window.castleUseStreaming === "undefined") {
    window.castleUseStreaming = false;
  }

  function bytesIndexOf(haystack, needle, fromIdx) {
    var hLen = haystack.length;
    var nLen = needle.length;
    if (nLen === 0) return fromIdx || 0;
    if (nLen > hLen) return -1;
    var start = fromIdx || 0;
    var end = hLen - nLen;
    for (var i = start; i <= end; i++) {
      var match = true;
      for (var j = 0; j < nLen; j++) {
        if (haystack[i + j] !== needle[j]) { match = false; break; }
      }
      if (match) return i;
    }
    return -1;
  }
  function concatBytes(a, b) {
    if (!a || a.length === 0) return b;
    if (!b || b.length === 0) return a;
    var out = new Uint8Array(a.length + b.length);
    out.set(a, 0);
    out.set(b, a.length);
    return out;
  }
  function asciiEncode(s) {
    var out = new Uint8Array(s.length);
    for (var i = 0; i < s.length; i++) out[i] = s.charCodeAt(i) & 0xff;
    return out;
  }
  function asciiDecode(bytes) {
    var s = "";
    for (var i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
    return s;
  }

  function createMultipartParser(onPart, onError, onEnd) {
    var buf = new Uint8Array(0);
    var done = false;
    var dashBoundary = asciiEncode("--" + BOUNDARY);
    var crlfBytes = asciiEncode(CRLF);
    var headerSepBytes = asciiEncode(CRLF + CRLF);

    function parseHeaders(headerStr) {
      var lines = headerStr.split(CRLF);
      var h = {};
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i];
        var sep = line.indexOf(":");
        if (sep > 0) {
          var key = line.substring(0, sep).trim().toLowerCase();
          var val = line.substring(sep + 1).trim();
          h[key] = val;
        }
      }
      return h;
    }

    function tryParse() {
      if (done) return;
      var bIdx = bytesIndexOf(buf, dashBoundary, 0);
      if (bIdx < 0) return;
      if (bIdx > 0) {
        buf = buf.slice(bIdx);
        bIdx = 0;
      }
      while (!done) {
        if (buf.length < dashBoundary.length + 2) return;
        var afterB = dashBoundary.length;
        if (buf[afterB] === 0x2d && buf[afterB + 1] === 0x2d) {
          done = true;
          if (onEnd) onEnd();
          return;
        }
        var headersStart = dashBoundary.length + crlfBytes.length;
        var headersEnd = bytesIndexOf(buf, headerSepBytes, headersStart);
        if (headersEnd < 0) return;
        var headerStr = asciiDecode(buf.slice(headersStart, headersEnd));
        var h = parseHeaders(headerStr);
        var contentLen = parseInt(h["content-length"] || "0", 10);
        if (!isFinite(contentLen) || contentLen < 0) {
          if (onError) onError(new Error("bad Content-Length: " + h["content-length"]));
          done = true;
          return;
        }
        var bodyStart = headersEnd + headerSepBytes.length;
        var bodyEnd = bodyStart + contentLen;
        if (buf.length < bodyEnd + crlfBytes.length) return;
        var body = buf.slice(bodyStart, bodyEnd);
        buf = buf.slice(bodyEnd + crlfBytes.length);

        var part = {
          contentType: h["content-type"] || "",
          isError: h["x-castle-error"] === "1",
          seq: parseInt(h["x-castle-seq"] || "-1", 10),
          frameCount: parseInt(h["x-castle-frame-count"] || "0", 10),
          isFirst: h["x-castle-is-first"] === "1",
          isLast: h["x-castle-is-last"] === "1",
          ptsOffsetS: parseFloat(h["x-castle-pts-offset-s"] || "0"),
          body: body
        };
        try { onPart(part); }
        catch (e) { if (onError) onError(e); }

        if (part.isError) {
          done = true;
          return;
        }

        var nextBIdx = bytesIndexOf(buf, dashBoundary, 0);
        if (nextBIdx < 0) return;
        if (nextBIdx > 0) buf = buf.slice(nextBIdx);
      }
    }

    return {
      push: function (chunk) {
        if (done) return;
        if (chunk && chunk.length) buf = concatBytes(buf, chunk);
        tryParse();
      },
      flush: function () { tryParse(); },
      isDone: function () { return done; }
    };
  }

  function MediaSourceSession(videoEl, opts) {
    this.video = videoEl;
    this.opts = opts || {};
    this.mediaSource = null;
    this.sourceBuffer = null;
    this.queue = [];
    this.appending = false;
    this.endRequested = false;
    this.aborted = false;
    this.objectUrl = null;
    this.firstAppended = false;
    this.partCount = 0;
    this.totalBytes = 0;
    this.startedAt = Date.now();
  }
  MediaSourceSession.prototype.start = function () {
    var self = this;
    var ms = new window.MediaSource();
    this.mediaSource = ms;
    this.objectUrl = URL.createObjectURL(ms);
    ms.addEventListener("sourceopen", function () {
      try {
        self.sourceBuffer = ms.addSourceBuffer(MIME);
        self.sourceBuffer.mode = "sequence";
        self.sourceBuffer.addEventListener("updateend", function () {
          self.appending = false;
          self._drain();
        });
        self.sourceBuffer.addEventListener("error", function (e) {
          console.warn("[sophie streaming] SourceBuffer error", e);
          if (self.opts.onError) self.opts.onError(new Error("SourceBuffer error"));
        });
        self._drain();
      } catch (e) {
        console.warn("[sophie streaming] addSourceBuffer fail", e);
        if (self.opts.onError) self.opts.onError(e);
      }
    });
    ms.addEventListener("sourceended", function () {
      if (self.opts.onEnded) self.opts.onEnded();
    });
    this.video.src = this.objectUrl;
    this.video.loop = false;
    this.video.muted = true;
    var p = this.video.play();
    if (p && p["catch"]) p["catch"](function (err) {
      console.warn("[sophie streaming] video.play fail", err && err.message);
    });
  };
  MediaSourceSession.prototype.appendChunk = function (bytes) {
    if (this.aborted) return;
    if (!bytes || bytes.length === 0) return;
    this.queue.push(bytes);
    this.totalBytes += bytes.length;
    this.partCount++;
    this._drain();
  };
  MediaSourceSession.prototype._drain = function () {
    if (this.aborted) return;
    if (!this.sourceBuffer) return;
    if (this.appending) return;
    if (this.sourceBuffer.updating) return;
    if (this.queue.length === 0) {
      if (this.endRequested && this.mediaSource && this.mediaSource.readyState === "open") {
        try { this.mediaSource.endOfStream(); } catch (e) {}
      }
      return;
    }
    var next = this.queue.shift();
    this.appending = true;
    try {
      this.sourceBuffer.appendBuffer(next);
      if (!this.firstAppended) {
        this.firstAppended = true;
        var firstLatencyMs = Date.now() - this.startedAt;
        if (this.opts.onFirstAppend) this.opts.onFirstAppend(firstLatencyMs);
      }
    } catch (e) {
      this.appending = false;
      console.warn("[sophie streaming] appendBuffer fail", e && e.message);
      if (this.opts.onError) this.opts.onError(e);
    }
  };
  MediaSourceSession.prototype.endStream = function () {
    this.endRequested = true;
    this._drain();
  };
  MediaSourceSession.prototype.abort = function () {
    this.aborted = true;
    try {
      if (this.sourceBuffer && this.mediaSource && this.mediaSource.readyState === "open") {
        this.mediaSource.removeSourceBuffer(this.sourceBuffer);
      }
    } catch (e) {}
    try {
      if (this.mediaSource && this.mediaSource.readyState === "open") {
        this.mediaSource.endOfStream();
      }
    } catch (e) {}
    try { if (this.objectUrl) URL.revokeObjectURL(this.objectUrl); } catch (e) {}
    this.queue = [];
  };

  function playMuseTalkStreaming(audioBlob, referenceState, options) {
    options = options || {};
    var refState = referenceState || "idle";
    var fps = options.fps || 25;
    var chunkFrames = options.chunkFrames || 12;
    var videoEl = options.videoEl || document.getElementById("liveVideo");

    if (!window.castleUseStreaming) {
      return playMuseTalkLegacyFallback(audioBlob, refState, options)
        .then(function (r) { return { ok: r && r.ok, fellBack: true, reason: "toggle-off" }; });
    }
    if (!window.__sophieStreamingCapable) {
      return playMuseTalkLegacyFallback(audioBlob, refState, options)
        .then(function (r) { return { ok: r && r.ok, fellBack: true, reason: "no-mediasource" }; });
    }
    if (!videoEl) {
      return Promise.resolve({ ok: false, fellBack: false, reason: "no-video-el" });
    }

    var sessionId = Date.now() + "-" + Math.random().toString(36).slice(2, 8);
    window.__sophieMuseTalkCurrentSession = sessionId;

    var sess = new MediaSourceSession(videoEl, {
      onFirstAppend: function (latencyMs) {
        console.log("[sophie streaming] first appendBuffer at " + latencyMs + "ms");
      },
      onError: function (e) {
        console.warn("[sophie streaming] MediaSource error", e && e.message);
      }
    });
    sess.start();

    var startedAt = Date.now();
    var partsReceived = 0;
    var firstByteAt = 0;

    function cancelIfSuperseded() {
      if (window.__sophieMuseTalkCurrentSession !== sessionId) {
        sess.abort();
        return true;
      }
      return false;
    }

    var parser = createMultipartParser(
      function onPart(part) {
        if (cancelIfSuperseded()) return;
        if (part.isError) {
          console.warn("[sophie streaming] backend chunk error: " + asciiDecode(part.body).slice(0, 200));
          return;
        }
        if (part.contentType && part.contentType.indexOf("video/mp4") >= 0 && part.body && part.body.length > 0) {
          partsReceived++;
          sess.appendChunk(part.body);
          if (part.isLast) {
            setTimeout(function () { sess.endStream(); }, 50);
          }
        }
      },
      function onParseError(err) {
        console.warn("[sophie streaming] parser error", err && err.message);
      },
      function onParseEnd() { sess.endStream(); }
    );

    var url = "/brain/musetalk_generate_streaming"
      + "?reference_state=" + encodeURIComponent(refState)
      + "&fps=" + encodeURIComponent(fps)
      + "&chunk_frames=" + encodeURIComponent(chunkFrames);

    return fetch(url, {
      method: "POST",
      body: audioBlob,
      credentials: "include",
      cache: "no-store",
      headers: { "Content-Type": "application/octet-stream" }
    }).then(function (resp) {
      if (!resp.ok) {
        return resp.text().then(function (errText) {
          sess.abort();
          console.warn("[sophie streaming] HTTP " + resp.status + " . falling back . " + errText.slice(0, 200));
          return playMuseTalkLegacyFallback(audioBlob, refState, options).then(function (r) {
            return { ok: r && r.ok, fellBack: true, reason: "http-" + resp.status };
          });
        });
      }
      if (!resp.body || !resp.body.getReader) {
        sess.abort();
        return playMuseTalkLegacyFallback(audioBlob, refState, options).then(function (r) {
          return { ok: r && r.ok, fellBack: true, reason: "no-stream-body" };
        });
      }
      var reader = resp.body.getReader();
      function pump() {
        return reader.read().then(function (res) {
          if (firstByteAt === 0) {
            firstByteAt = Date.now();
            console.log("[sophie streaming] first byte at " + (firstByteAt - startedAt) + "ms");
          }
          if (cancelIfSuperseded()) {
            try { reader.cancel(); } catch (e) {}
            return { ok: false, fellBack: false, reason: "superseded" };
          }
          if (res.done) {
            parser.flush();
            setTimeout(function () { sess.endStream(); }, 30);
            return { ok: true, fellBack: false, reason: "complete", parts: partsReceived };
          }
          parser.push(res.value);
          return pump();
        });
      }
      return pump();
    })["catch"](function (err) {
      console.warn("[sophie streaming] fetch fail, falling back", err && err.message);
      sess.abort();
      return playMuseTalkLegacyFallback(audioBlob, refState, options).then(function (r) {
        return { ok: r && r.ok, fellBack: true, reason: "fetch-error" };
      });
    });
  }

  function playMuseTalkLegacyFallback(audioBlob, referenceState, options) {
    var refState = referenceState || "idle";
    var videoEl = (options && options.videoEl) || document.getElementById("liveVideo");
    var url = "/brain/musetalk_generate?reference_state=" + encodeURIComponent(refState);
    return fetch(url, {
      method: "POST",
      body: audioBlob,
      credentials: "include",
      cache: "no-store",
      headers: { "Content-Type": "application/octet-stream" }
    }).then(function (resp) {
      if (!resp.ok) return { ok: false, reason: "legacy-http-" + resp.status };
      return resp.blob().then(function (mp4Blob) {
        if (!videoEl) return { ok: false, reason: "no-video-el" };
        try {
          var objUrl = URL.createObjectURL(mp4Blob);
          videoEl.src = objUrl;
          videoEl.loop = false;
          videoEl.muted = true;
          var p = videoEl.play();
          if (p && p["catch"]) p["catch"](function () {});
          return { ok: true, reason: "legacy-played" };
        } catch (e) {
          return { ok: false, reason: "legacy-play-fail: " + (e && e.message) };
        }
      });
    })["catch"](function (err) {
      return { ok: false, reason: "legacy-fetch-fail: " + (err && err.message) };
    });
  }

  window.__sophieMuseTalkStreaming = {
    play: playMuseTalkStreaming,
    legacyFallback: playMuseTalkLegacyFallback,
    capable: function () { return window.__sophieStreamingCapable === true; },
    toggle: function (on) { window.castleUseStreaming = !!on; return window.castleUseStreaming; },
    _internals: {
      createMultipartParser: createMultipartParser,
      MediaSourceSession: MediaSourceSession,
      BOUNDARY: BOUNDARY,
      MIME: MIME
    }
  };

  console.log("[sophie] MuseTalk streaming module ready . capable=" + window.__sophieStreamingCapable
    + " . toggle=" + window.castleUseStreaming);
}());
