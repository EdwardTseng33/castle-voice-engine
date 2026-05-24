// castle/static/speech-state.js
// Voice Path V1 Stable Presence - Speech State Reducer
//
// Reduces OpenAI Realtime dataChannel events into a single speechState:
//   listening | thinking | speaking | interrupted | idle
//
// Then dispatches { type: "speech_state", state, sid, text } intents to
// the AvatarCompositor. This is the SOLE bridge from OpenAI events to
// the visual avatar. v2.0.6 used to call animPool.startSpeaking() directly;
// in V1 Compositor we route everything through here.
//
// State transitions:
//   idle -> listening      (user starts speaking · input_audio_buffer.speech_started)
//   listening -> thinking  (response.created)
//   thinking -> speaking   (first response.audio.delta arrives)
//   speaking -> idle       (response.audio.done OR response.done after audio finished)
//   any -> interrupted     (response.cancelled OR client interrupts)
//   interrupted -> idle    (auto · 200ms cooldown)
//
// ES5 only.
(function (global) {
  "use strict";

  var STATES = {
    IDLE: "idle",
    LISTENING: "listening",
    THINKING: "thinking",
    SPEAKING: "speaking",
    INTERRUPTED: "interrupted"
  };

  function nowMs() { return Date.now ? Date.now() : new Date().getTime(); }

  function SpeechStateReducer(compositor, opts) {
    if (!compositor || typeof compositor.dispatch !== "function") {
      throw new Error("[speechState] compositor with dispatch() required");
    }
    opts = opts || {};
    this.compositor = compositor;
    this.log = opts.log || function (msg) {
      try { console.log("[speechState]", msg); } catch (e) {}
    };
    this.state = STATES.IDLE;
    this.currentSid = null;
    this.responseStartedTs = 0;
    this.audioDeltaFirstTs = 0;
    this.audioDoneTs = 0;
    this._interruptCooldownTimer = null;
    this._latencyHistory = []; // { responseId, latencyMs }
  }

  SpeechStateReducer.prototype.STATES = STATES;

  SpeechStateReducer.prototype._transition = function (newState, extra) {
    extra = extra || {};
    if (this.state === newState) return;
    var prev = this.state;
    this.state = newState;
    var sid = extra.sid || this.currentSid;
    this.log("transition " + prev + " -> " + newState + " sid=" + (sid || "-"));
    try {
      this.compositor.dispatch({
        type: "speech_state",
        state: newState,
        sid: sid,
        text: extra.text || ""
      });
    } catch (e) {
      this.log("compositor dispatch fail: " + e.message);
    }

    // emit DOM event for other listeners (debug-panel etc.)
    try {
      var ev = new CustomEvent("sophie:speechState", {
        detail: { prev: prev, state: newState, sid: sid, ts: nowMs() }
      });
      global.dispatchEvent(ev);
    } catch (e) {}
  };

  // ===== Public API =====
  // Wire this up where index.html now listens to OpenAI events (around L2598).
  // Pass the parsed JSON message object straight in.
  SpeechStateReducer.prototype.handleOpenAIEvent = function (data) {
    if (!data || !data.type) return;
    var t = data.type;

    // response.created -> new sid begins
    if (t === "response.created") {
      this.currentSid = data.response && data.response.id ? data.response.id : ("r-" + nowMs());
      this.responseStartedTs = nowMs();
      this.audioDeltaFirstTs = 0;
      this.audioDoneTs = 0;
      this._transition(STATES.THINKING, { sid: this.currentSid });
      return;
    }

    // first audio delta arrives -> speaking
    if (t === "response.audio.delta" || t === "response.output_audio.delta") {
      if (this.audioDeltaFirstTs === 0) {
        this.audioDeltaFirstTs = nowMs();
        var lat = this.responseStartedTs > 0 ? this.audioDeltaFirstTs - this.responseStartedTs : 0;
        if (this.currentSid) {
          this._latencyHistory.push({ sid: this.currentSid, latencyMs: lat });
          if (this._latencyHistory.length > 20) this._latencyHistory.shift();
        }
        this._transition(STATES.SPEAKING, { sid: this.currentSid });
      }
      return;
    }

    // audio done -> return to idle (V1 simple model, no post-audio gap)
    if (t === "response.audio.done" || t === "response.output_audio.done") {
      this.audioDoneTs = nowMs();
      this._transition(STATES.IDLE, { sid: this.currentSid });
      return;
    }

    // response.done after audio.done = clean wrap (already idle)
    // response.done before audio.done = abnormal but treat as idle
    if (t === "response.done") {
      if (this.state !== STATES.IDLE) {
        this._transition(STATES.IDLE, { sid: this.currentSid });
      }
      return;
    }

    // user interruption / cancel
    if (t === "response.cancelled" || t === "response.canceled") {
      this._enterInterrupted();
      return;
    }

    // user starts speaking (server-VAD detected)
    if (t === "input_audio_buffer.speech_started") {
      if (this.state === STATES.IDLE || this.state === STATES.LISTENING) {
        this._transition(STATES.LISTENING, {});
      } else if (this.state === STATES.SPEAKING) {
        // barge-in scenario · user speaks while Sophie speaks
        this._enterInterrupted();
      }
      return;
    }

    // user stops speaking
    if (t === "input_audio_buffer.speech_stopped") {
      if (this.state === STATES.LISTENING) {
        // hold listening until response.created arrives
      }
      return;
    }
  };

  SpeechStateReducer.prototype._enterInterrupted = function () {
    var self = this;
    this._transition(STATES.INTERRUPTED, { sid: this.currentSid });
    if (this._interruptCooldownTimer) clearTimeout(this._interruptCooldownTimer);
    this._interruptCooldownTimer = setTimeout(function () {
      self._transition(STATES.IDLE, {});
      self._interruptCooldownTimer = null;
    }, 200);
  };

  // Force a state (escape hatch · used by call-start / explicit reset)
  SpeechStateReducer.prototype.force = function (state, reason) {
    if (!STATES[state.toUpperCase()] && !STATES[state]) {
      // state could be value form
    }
    var target = (typeof state === "string" && STATES[state.toUpperCase()]) ? STATES[state.toUpperCase()] : state;
    this.log("force " + target + " reason=" + (reason || "-"));
    this._transition(target, {});
  };

  SpeechStateReducer.prototype.getState = function () {
    return {
      state: this.state,
      currentSid: this.currentSid,
      lastResponseStartedTs: this.responseStartedTs,
      lastAudioDeltaTs: this.audioDeltaFirstTs,
      lastAudioDoneTs: this.audioDoneTs,
      lastLatencyMs: this.audioDeltaFirstTs && this.responseStartedTs
        ? this.audioDeltaFirstTs - this.responseStartedTs : 0,
      latencyHistoryCount: this._latencyHistory.length
    };
  };

  global.SpeechStateReducer = SpeechStateReducer;
  global.SOPHIE_SPEECH_STATES = STATES;
})(window);
