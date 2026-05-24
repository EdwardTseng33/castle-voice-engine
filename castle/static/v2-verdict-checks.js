// castle/static/v2-verdict-checks.js
// V1.5 馬魯克 · 4 條 V2 驗收 metric 量化 detector
//
// 用途:
//   1. measureFlickerRate(durationMs)    · 切換次數/分鐘 · 目標 < 6
//   2. measureSpeakingAnimation()        · audio.done → timeupdate latency · 目標 < 2s
//   3. measureStateAlignment()           · compositor state vs actual src offset · 目標 < 500ms
//   4. measureFirstSentenceLatency()     · OpenAI session start → 首句 speaking · 目標 < 3s
//   5. collectMetrics(durationMs)        · 統一收集 4 條 + return verdict object
//
// ES5 only (Safari 13 compat).
// 依賴: window.__sophieAvatarCompositor (avatar-compositor.js 先載)
//       liveVideo element (id="live-video" 或 window.__sophieLiveVideo)
//
// 使用方式 (dev/cron):
//   window.__sophieV2Verdict.collectMetrics(60000).then(function(v){ console.log(v); });
//
(function (global) {
  "use strict";

  // ── 內部工具 ───────────────────────────────────────────
  function nowMs() { return Date.now ? Date.now() : new Date().getTime(); }

  function getVideo() {
    return global.__sophieLiveVideo ||
           document.getElementById("live-video") ||
           document.querySelector("video");
  }

  function getCompositor() {
    return global.__sophieAvatarCompositor || null;
  }

  function clampPositive(n) {
    return typeof n === "number" && isFinite(n) && n >= 0 ? n : 0;
  }

  // ── Metric 1 · FlickerRate ─────────────────────────────
  // 觀察 liveVideo.src 屬性變化次數 · MutationObserver 監聽 attribute 不能監 src
  // 改用 interval polling + Object.defineProperty setter 攔截
  function measureFlickerRate(durationMs) {
    return new Promise(function (resolve) {
      var video = getVideo();
      if (!video) {
        resolve({ metric: "flickerRate", value: -1, unit: "switches/min", pass: false, error: "no video element" });
        return;
      }

      var switchCount = 0;
      var startTs = nowMs();
      var safeDuration = clampPositive(durationMs) || 60000;

      // 用 compositor stats.srcSwitchTimestamps 最準確 (compositor 才是唯一寫 src 的 owner)
      var compositor = getCompositor();
      var baselineCount = 0;
      if (compositor && compositor.stats && compositor.stats.srcSwitchTimestamps) {
        baselineCount = compositor.stats.srcSwitchCount || 0;
      }

      // 也攔截 video.currentSrc 變化 (透過 timeupdate 觀察 src 不穩定 · 改用 canplay event)
      function onCanPlay() {
        switchCount++;
      }
      video.addEventListener("canplay", onCanPlay);

      setTimeout(function () {
        video.removeEventListener("canplay", onCanPlay);

        var compositorSwitches = 0;
        if (compositor && compositor.stats) {
          var totalNow = compositor.stats.srcSwitchCount || 0;
          compositorSwitches = Math.max(0, totalNow - baselineCount);
        }

        // 取較大值 (canplay count vs compositor diff)
        var observed = Math.max(switchCount, compositorSwitches);
        var durationMinutes = safeDuration / 60000;
        var rate = durationMinutes > 0 ? observed / durationMinutes : observed;
        var pass = rate < 6;

        resolve({
          metric: "flickerRate",
          value: Math.round(rate * 100) / 100,
          unit: "switches/min",
          target: "< 6",
          pass: pass,
          raw: { observed: observed, durationMs: safeDuration, compositorSwitches: compositorSwitches, canplaySwitches: switchCount }
        });
      }, safeDuration);
    });
  }

  // ── Metric 2 · SpeakingAnimation latency ──────────────
  // audio.done event 到 timeupdate (video 真在播) 的 latency
  // audio.done 在 DataChannel: response.audio.done
  // 由外部呼叫 __sophieV2Verdict.notifyAudioDone(ts) 注入 (index.html DC handler 調用)
  // 或由 simulate_realtime SSE sim.done 事件觸發
  var _audioDoneTs = null;
  var _speakingAnimationSamples = [];

  function notifyAudioDone(ts) {
    _audioDoneTs = typeof ts === "number" ? ts : nowMs();
  }

  function measureSpeakingAnimation() {
    return new Promise(function (resolve) {
      var video = getVideo();
      if (!video) {
        resolve({ metric: "speakingAnimLatency", value: -1, unit: "ms", pass: false, error: "no video element" });
        return;
      }

      if (_speakingAnimationSamples.length > 0) {
        var avg = 0;
        for (var i = 0; i < _speakingAnimationSamples.length; i++) avg += _speakingAnimationSamples[i];
        avg = avg / _speakingAnimationSamples.length;
        var pass = avg < 2000;
        resolve({
          metric: "speakingAnimLatency",
          value: Math.round(avg),
          unit: "ms",
          target: "< 2000ms",
          pass: pass,
          raw: { samples: _speakingAnimationSamples.slice() }
        });
        return;
      }

      // 沒有樣本 · 啟動觀察 · 等最多 10s
      var startWait = nowMs();
      var captured = false;

      function onTimeupdate() {
        if (captured) return;
        if (_audioDoneTs !== null) {
          var latency = nowMs() - _audioDoneTs;
          if (latency >= 0 && latency < 30000) {
            captured = true;
            _speakingAnimationSamples.push(latency);
            video.removeEventListener("timeupdate", onTimeupdate);
            var pass = latency < 2000;
            resolve({
              metric: "speakingAnimLatency",
              value: latency,
              unit: "ms",
              target: "< 2000ms",
              pass: pass,
              raw: { samples: [latency], note: "single sample" }
            });
          }
        }
      }
      video.addEventListener("timeupdate", onTimeupdate);

      setTimeout(function () {
        if (captured) return;
        video.removeEventListener("timeupdate", onTimeupdate);
        resolve({
          metric: "speakingAnimLatency",
          value: -1,
          unit: "ms",
          target: "< 2000ms",
          pass: false,
          error: "no audio.done signal received within 10s · call notifyAudioDone() from DC handler or sim endpoint"
        });
      }, 10000);
    });
  }

  // ── Metric 3 · StateAlignment ─────────────────────────
  // compositor.mode vs video.currentSrc 對應關係是否一致
  // 模式對應表:
  //   compositor.mode = "lipsync_cached" / "lipsync_realtime" → currentSrc 含 /lipsync/
  //   compositor.mode = "speaking"                           → currentSrc 含 sophie-speaking
  //   compositor.mode = "idle"                               → currentSrc 含 sophie-idle
  //   compositor.mode = "action"                             → 任何 /static/sophie-*.mp4

  var _stateAlignmentSamples = [];

  function _checkStateAlignmentOnce() {
    var compositor = getCompositor();
    var video = getVideo();
    if (!compositor || !video) return null;

    var state;
    try { state = compositor.getState(); } catch (e) { return null; }
    var mode = state.mode || "idle";
    var src = (video.currentSrc || video.src || "").toLowerCase();

    var aligned = false;
    if (mode === "lipsync_cached" || mode === "lipsync_realtime") {
      aligned = src.indexOf("/lipsync/") !== -1;
    } else if (mode === "speaking") {
      aligned = src.indexOf("sophie-speaking") !== -1;
    } else if (mode === "idle") {
      aligned = src.indexOf("sophie-idle") !== -1 || src.indexOf("sophie-poc-loop") !== -1;
    } else if (mode === "action") {
      aligned = src.indexOf("/static/sophie-") !== -1;
    } else {
      aligned = true; // unknown mode · 不判斷
    }

    return { mode: mode, src: src.slice(-60), aligned: aligned, ts: nowMs() };
  }

  function measureStateAlignment() {
    return new Promise(function (resolve) {
      var compositor = getCompositor();
      if (!compositor) {
        resolve({ metric: "stateAlignment", value: -1, unit: "offset_ms", pass: false, error: "no compositor" });
        return;
      }

      // 連續 10 次取樣、每 200ms 一次、累積最大 2s
      var samples = [];
      var MAX_SAMPLES = 10;
      var INTERVAL = 200;
      var count = 0;

      var timer = setInterval(function () {
        var sample = _checkStateAlignmentOnce();
        if (sample) samples.push(sample);
        count++;
        if (count >= MAX_SAMPLES) {
          clearInterval(timer);

          if (samples.length === 0) {
            resolve({ metric: "stateAlignment", value: -1, unit: "offset_ms", pass: false, error: "no samples" });
            return;
          }

          var misaligned = 0;
          for (var i = 0; i < samples.length; i++) {
            if (!samples[i].aligned) misaligned++;
          }
          // offset_ms 用 misaligned 比例換算 (INTERVAL * misaligned = 估計 misaligned 時間)
          var offsetMs = misaligned * INTERVAL;
          var pass = offsetMs < 500;

          resolve({
            metric: "stateAlignment",
            value: offsetMs,
            unit: "offset_ms",
            target: "< 500ms",
            pass: pass,
            raw: { total: samples.length, misaligned: misaligned, samples: samples }
          });
        }
      }, INTERVAL);
    });
  }

  // ── Metric 4 · FirstSentenceLatency ───────────────────
  // OpenAI session start (response.audio.delta first) → 首句 speaking visual
  // __sophieV2Verdict.notifySessionStart(ts) 由 DC handler 呼叫

  var _sessionStartTs = null;
  var _firstSpeakingTs = null;
  var _firstSentenceSamples = [];
  var _fsObserverActive = false;

  function notifySessionStart(ts) {
    _sessionStartTs = typeof ts === "number" ? ts : nowMs();
    _firstSpeakingTs = null;
    _startFirstSentenceObserver();
  }

  function _startFirstSentenceObserver() {
    if (_fsObserverActive) return;
    _fsObserverActive = true;
    var video = getVideo();
    if (!video) { _fsObserverActive = false; return; }

    function onPlay() {
      if (_sessionStartTs !== null && _firstSpeakingTs === null) {
        var latency = nowMs() - _sessionStartTs;
        if (latency >= 0 && latency < 30000) {
          _firstSpeakingTs = nowMs();
          _firstSentenceSamples.push(latency);
          video.removeEventListener("play", onPlay);
          _fsObserverActive = false;
        }
      }
    }
    video.addEventListener("play", onPlay);

    // 逾時清除
    setTimeout(function () {
      video.removeEventListener("play", onPlay);
      _fsObserverActive = false;
    }, 15000);
  }

  function measureFirstSentenceLatency() {
    return new Promise(function (resolve) {
      if (_firstSentenceSamples.length > 0) {
        var avg = 0;
        for (var i = 0; i < _firstSentenceSamples.length; i++) avg += _firstSentenceSamples[i];
        avg = avg / _firstSentenceSamples.length;
        var pass = avg < 3000;
        resolve({
          metric: "firstSentenceLatency",
          value: Math.round(avg),
          unit: "ms",
          target: "< 3000ms",
          pass: pass,
          raw: { samples: _firstSentenceSamples.slice() }
        });
        return;
      }

      // 等最多 15s 收一個樣本
      var timer = setInterval(function () {
        if (_firstSentenceSamples.length > 0) {
          clearInterval(timer);
          measureFirstSentenceLatency().then(resolve);
        }
      }, 500);

      setTimeout(function () {
        clearInterval(timer);
        resolve({
          metric: "firstSentenceLatency",
          value: -1,
          unit: "ms",
          target: "< 3000ms",
          pass: false,
          error: "no session start signal · call notifySessionStart() from DC handler"
        });
      }, 15000);
    });
  }

  // ── collectMetrics · 統一收集 4 條 ────────────────────
  // durationMs: FlickerRate 觀察視窗 (預設 60000)
  // 其他 3 條取樣時間固定 (< 15s)
  // 回傳 Promise<verdict_object>
  function collectMetrics(durationMs) {
    var flickerDuration = clampPositive(durationMs) || 60000;

    // Metric 2/3/4 先跑 (不等 flicker 觀察期)
    var p2 = measureSpeakingAnimation();
    var p3 = measureStateAlignment();
    var p4 = measureFirstSentenceLatency();
    // Metric 1 最後 (需等 durationMs)
    var p1 = measureFlickerRate(flickerDuration);

    return Promise.all([p1, p2, p3, p4]).then(function (results) {
      var flickerResult  = results[0];
      var speakingResult = results[1];
      var alignResult    = results[2];
      var latencyResult  = results[3];

      var allPass = flickerResult.pass && speakingResult.pass && alignResult.pass && latencyResult.pass;
      var ts = new Date().toISOString();

      return {
        verdict: allPass ? "PASS" : "FAIL",
        ts: ts,
        durationMs: flickerDuration,
        metrics: {
          flickerRate:           flickerResult,
          speakingAnimLatency:   speakingResult,
          stateAlignment:        alignResult,
          firstSentenceLatency:  latencyResult
        },
        summary: {
          flickerRate:          (flickerResult.pass   ? "PASS" : "FAIL") + " · " + flickerResult.value  + " " + flickerResult.unit,
          speakingAnimLatency:  (speakingResult.pass  ? "PASS" : "FAIL") + " · " + speakingResult.value + " " + speakingResult.unit,
          stateAlignment:       (alignResult.pass     ? "PASS" : "FAIL") + " · " + alignResult.value    + " " + alignResult.unit,
          firstSentenceLatency: (latencyResult.pass   ? "PASS" : "FAIL") + " · " + latencyResult.value  + " " + latencyResult.unit
        }
      };
    });
  }

  // ── 公開 API ──────────────────────────────────────────
  global.__sophieV2Verdict = {
    measureFlickerRate: measureFlickerRate,
    measureSpeakingAnimation: measureSpeakingAnimation,
    measureStateAlignment: measureStateAlignment,
    measureFirstSentenceLatency: measureFirstSentenceLatency,
    collectMetrics: collectMetrics,
    // hooks · DC handler 呼叫
    notifyAudioDone: notifyAudioDone,
    notifySessionStart: notifySessionStart,
    // 內部狀態 · 測試用
    _getSamples: function () {
      return {
        speakingAnimationSamples: _speakingAnimationSamples.slice(),
        firstSentenceSamples: _firstSentenceSamples.slice(),
        stateAlignmentSamples: _stateAlignmentSamples.slice(),
        audioDoneTs: _audioDoneTs,
        sessionStartTs: _sessionStartTs
      };
    },
    _reset: function () {
      _audioDoneTs = null;
      _sessionStartTs = null;
      _firstSpeakingTs = null;
      _speakingAnimationSamples = [];
      _firstSentenceSamples = [];
      _stateAlignmentSamples = [];
      _fsObserverActive = false;
    }
  };

  try {
    console.log("[sophieV2Verdict] loaded · 4 metrics ready (flickerRate / speakingAnimLatency / stateAlignment / firstSentenceLatency)");
  } catch (e) {}

})(window);
