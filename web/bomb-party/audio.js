(function () {
  'use strict';
  class Audio {
    constructor() {
      this.muted = false;
      try { this.muted = localStorage.getItem('bomb-party-muted') === '1'; } catch (_) { /* private mode */ }
    }
    unlock() {
      try {
        if (!this.ctx) {
          const Context = window.AudioContext || window.webkitAudioContext;
          if (!Context) return;
          this.ctx = new Context();
          this.master = this.ctx.createGain();
          this.master.gain.value = this.muted ? 0 : 0.55;
          const limiter = this.ctx.createDynamicsCompressor();
          limiter.threshold.value = -12;
          limiter.ratio.value = 12;
          this.master.connect(limiter).connect(this.ctx.destination);
        }
        this.ctx.resume().catch(() => {});
      } catch (_) { /* audio is optional */ }
    }
    toggle() {
      this.muted = !this.muted;
      this.unlock();
      if (this.master) this.master.gain.setTargetAtTime(this.muted ? 0 : 0.55, this.ctx.currentTime, 0.01);
      try { localStorage.setItem('bomb-party-muted', this.muted ? '1' : '0'); } catch (_) { /* private mode */ }
    }
    tone(freq, end, duration, gain = 0.12, delay = 0, type = 'square') {
      if (!this.ctx || this.muted) return;
      const t = this.ctx.currentTime + delay, osc = this.ctx.createOscillator(), env = this.ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, t);
      osc.frequency.exponentialRampToValueAtTime(Math.max(end, 1), t + duration);
      env.gain.setValueAtTime(0, t);
      env.gain.linearRampToValueAtTime(gain, t + 0.004);
      env.gain.exponentialRampToValueAtTime(0.001, t + duration);
      osc.connect(env).connect(this.master);
      osc.start(t); osc.stop(t + duration + 0.01);
      osc.onended = () => { osc.disconnect(); env.disconnect(); };
    }
    noise(duration, gain, low = 1500) {
      if (!this.ctx || this.muted) return;
      const buffer = this.ctx.createBuffer(1, Math.ceil(duration * this.ctx.sampleRate), this.ctx.sampleRate);
      const data = buffer.getChannelData(0);
      for (let i = 0; i < data.length; i++) data[i] = (Math.random() * 2 - 1) * Math.exp(-6 * i / data.length);
      const source = this.ctx.createBufferSource(), env = this.ctx.createGain(), filter = this.ctx.createBiquadFilter();
      source.buffer = buffer; filter.type = 'lowpass'; filter.frequency.value = low; env.gain.value = gain;
      source.connect(filter).connect(env).connect(this.master); source.start();
      source.onended = () => { source.disconnect(); filter.disconnect(); env.disconnect(); };
    }
    events(events) {
      if (!this.ctx || this.muted) return;
      const count = type => events.filter(e => e.type === type && !e.cancelled).length;
      if (count('bomb')) this.tone(780, 420, 0.065);
      if (count('explode')) {
        const strength = Math.min(1.1, 0.48 + 0.16 * (count('explode') - 1));
        this.noise(0.38, strength, 700);
        this.tone(120, 32, 0.24, strength * 0.45, 0, 'sine');
      }
      if (count('brick')) this.noise(0.12, Math.min(0.4, 0.12 + count('brick') * 0.025), 5500);
      if (count('pickup')) [1046, 1318, 1568].forEach((f, i) => this.tone(f, f, 0.07, 0.12, i * 0.045));
      if (count('kick')) { this.noise(0.1, 0.18, 900); this.tone(230, 400, 0.08, 0.09); }
      if (count('crush')) this.tone(110, 40, 0.16, 0.32, 0, 'sine');
      if (count('die')) [523, 392, 330, 262].forEach((f, i) => this.tone(f, f * 0.9, 0.13, 0.1, i * 0.09));
    }
    victory() { [523, 659, 784, 1046].forEach((f, i) => this.tone(f, f, 0.21, 0.15, i * 0.11)); }
  }
  window.BPAudio = Audio;
})();
