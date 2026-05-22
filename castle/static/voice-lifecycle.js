// castle/static/voice-lifecycle.js
// Voice Path v0.7 · 6-state machine 瀏覽器層 lifecycle
// State: hibernate -> waking -> pre-call -> in-call -> soft-prompt -> semi-idle -> hibernate
// 不直接接 GPU · 不直接 spawn Modal · 透過 backend endpoints 跟雲端通訊

(function () {
  'use strict';

  var STATES = {
    HIBERNATE:   'hibernate',
    WAKING:      'waking',
    PRE_CALL:    'pre-call',
    IN_CALL:     'in-call',
    SOFT_PROMPT: 'soft-prompt',
    SEMI_IDLE:   'semi-idle'
  };

  var TIMERS = {
    SOFT_PROMPT_AFTER_MS: 30000,   // in-call · 30s 無對話 → soft-prompt
    SEMI_IDLE_AFTER_MS:   60000,   // soft-prompt · 60s 無對話 + 鏡頭無人 → semi-idle
    HIBERNATE_AFTER_MS:   300000   // semi-idle · 5 min 無喚醒 → hibernate
  };

  function VoiceLifecycle(opts) {
    opts = opts || {};
    this.state = STATES.HIBERNATE;
    this.shell = opts.shell || document.getElementById('shell');
    this.onTransition = opts.onTransition || function () {};
    this.lastVoiceMs = 0;
    this.lastFaceMs = 0;
    this.transitionLocked = false;
    this.tickIntervalId = null;
    this._applyState();
  }

  VoiceLifecycle.prototype.STATES = STATES;

  VoiceLifecycle.prototype.start = function () {
    if (this.tickIntervalId) return;
    var self = this;
    this.tickIntervalId = setInterval(function () { self.tick(); }, 1000);
  };

  VoiceLifecycle.prototype.stop = function () {
    if (this.tickIntervalId) {
      clearInterval(this.tickIntervalId);
      this.tickIntervalId = null;
    }
  };

  VoiceLifecycle.prototype._applyState = function () {
    if (this.shell) {
      this.shell.setAttribute('data-state', this.state);
    }
  };

  VoiceLifecycle.prototype.transitionTo = function (newState) {
    if (this.transitionLocked) return false;
    if (this.state === newState) return false;
    var validStates = Object.keys(STATES).map(function (k) { return STATES[k]; });
    if (validStates.indexOf(newState) === -1) {
      console.warn('[VoiceLifecycle] invalid state:', newState);
      return false;
    }
    var oldState = this.state;
    this.transitionLocked = true;
    this.state = newState;
    this._applyState();
    try {
      this.onTransition(oldState, newState);
    } catch (e) {
      console.error('[VoiceLifecycle] onTransition err:', e);
    }
    // 過渡途中鎖 400ms (對齊 CSS --motion-smooth) 不接受新 state change
    var self = this;
    setTimeout(function () { self.transitionLocked = false; }, 400);
    console.log('[VoiceLifecycle]', oldState, '→', newState);
    return true;
  };

  VoiceLifecycle.prototype.markVoice = function () {
    this.lastVoiceMs = Date.now();
  };

  VoiceLifecycle.prototype.markFace = function () {
    this.lastFaceMs = Date.now();
  };

  VoiceLifecycle.prototype.tick = function () {
    var now = Date.now();
    var silenceMs = this.lastVoiceMs ? (now - this.lastVoiceMs) : Infinity;
    var faceAbsentMs = this.lastFaceMs ? (now - this.lastFaceMs) : Infinity;

    switch (this.state) {
      case STATES.IN_CALL:
        if (silenceMs > TIMERS.SOFT_PROMPT_AFTER_MS) {
          this.transitionTo(STATES.SOFT_PROMPT);
        }
        break;

      case STATES.SOFT_PROMPT:
        if (silenceMs > TIMERS.SEMI_IDLE_AFTER_MS && faceAbsentMs > 30000) {
          this.transitionTo(STATES.SEMI_IDLE);
        }
        break;

      case STATES.SEMI_IDLE:
        if (silenceMs > TIMERS.HIBERNATE_AFTER_MS && faceAbsentMs > TIMERS.HIBERNATE_AFTER_MS) {
          this.transitionTo(STATES.HIBERNATE);
          this._notifySleep();
        }
        break;
    }
  };

  VoiceLifecycle.prototype._notifySleep = function () {
    // 通知 backend Modal scale-to-zero (best-effort · 不卡 UI)
    try {
      fetch('/voice/sleep', { method: 'POST' }).catch(function () {});
    } catch (e) {}
  };

  VoiceLifecycle.prototype.wake = function () {
    if (this.state === STATES.HIBERNATE || this.state === STATES.SEMI_IDLE) {
      this.transitionTo(STATES.WAKING);
      // 後台呼叫 /voice/wake 通知 Modal warm-up
      var self = this;
      try {
        fetch('/voice/wake', { method: 'POST' })
          .then(function (r) { return r.ok ? r.json() : null; })
          .then(function (j) {
            if (self.state === STATES.WAKING) {
              self.transitionTo(STATES.PRE_CALL);
            }
          })
          .catch(function () {
            // 雲端不通也讓 user 看到 pre-call 介面 (graceful)
            if (self.state === STATES.WAKING) {
              self.transitionTo(STATES.PRE_CALL);
            }
          });
      } catch (e) {
        if (this.state === STATES.WAKING) this.transitionTo(STATES.PRE_CALL);
      }
    }
  };

  VoiceLifecycle.prototype.startCall = function () {
    if (this.state === STATES.PRE_CALL) {
      this.transitionTo(STATES.IN_CALL);
      this.markVoice();
    }
  };

  VoiceLifecycle.prototype.endCall = function () {
    if (this.state === STATES.IN_CALL || this.state === STATES.SOFT_PROMPT) {
      this.transitionTo(STATES.PRE_CALL);
    }
  };

  // expose
  window.VoiceLifecycle = VoiceLifecycle;
  window.VoiceLifecycleStates = STATES;
})();
