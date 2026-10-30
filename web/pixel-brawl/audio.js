// 音效全部用 WebAudio 现场合成（照 games/brawl/tools/sfx.py 的配方缩成实时版），不带音频文件。
(function () {
  'use strict';
  const KEY = 'pixel-brawl-muted';
  class Audio {
    constructor() {
      this.muted = false;
      try { this.muted = localStorage.getItem(KEY) === '1'; } catch (_) { /* private mode */ }
    }
    unlock() {
      try {
        if (!this.ctx) {
          const Context = window.AudioContext || window.webkitAudioContext;
          if (!Context) return;
          this.ctx = new Context();
          this.master = this.ctx.createGain();
          this.master.gain.value = this.muted ? 0 : 0.6;
          const limiter = this.ctx.createDynamicsCompressor();
          limiter.threshold.value = -10; limiter.ratio.value = 12;
          this.master.connect(limiter).connect(this.ctx.destination);
          this.noiseBuf = this.ctx.createBuffer(1, this.ctx.sampleRate, this.ctx.sampleRate);
          const d = this.noiseBuf.getChannelData(0);
          for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
        }
        this.ctx.resume().catch(() => {});
      } catch (_) { /* audio is optional */ }
    }
    toggle() {
      this.muted = !this.muted;
      this.unlock();
      if (this.master) this.master.gain.setTargetAtTime(this.muted ? 0 : 0.6, this.ctx.currentTime, 0.01);
      try { localStorage.setItem(KEY, this.muted ? '1' : '0'); } catch (_) { /* private mode */ }
    }
    live() { return this.ctx && !this.muted && this.ctx.state === 'running'; }
    tone(freq, end, duration, gain = 0.12, delay = 0, type = 'square') {
      if (!this.live()) return;
      const t = this.ctx.currentTime + delay, osc = this.ctx.createOscillator(), env = this.ctx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, t);
      osc.frequency.exponentialRampToValueAtTime(Math.max(end, 1), t + duration);
      env.gain.setValueAtTime(0, t);
      env.gain.linearRampToValueAtTime(gain, t + 0.003);
      env.gain.exponentialRampToValueAtTime(0.001, t + duration);
      osc.connect(env).connect(this.master);
      osc.start(t); osc.stop(t + duration + 0.02);
      osc.onended = () => { osc.disconnect(); env.disconnect(); };
    }
    noise(duration, gain, freq = 1500, delay = 0, type = 'lowpass', swell = false) {
      if (!this.live()) return;
      const t = this.ctx.currentTime + delay;
      const src = this.ctx.createBufferSource(), env = this.ctx.createGain(), filter = this.ctx.createBiquadFilter();
      src.buffer = this.noiseBuf; filter.type = type; filter.frequency.value = freq;
      if (swell) { env.gain.setValueAtTime(0.001, t); env.gain.linearRampToValueAtTime(gain, t + duration / 2); env.gain.linearRampToValueAtTime(0.001, t + duration); }
      else { env.gain.setValueAtTime(gain, t); env.gain.exponentialRampToValueAtTime(0.001, t + duration); }
      src.connect(filter).connect(env).connect(this.master);
      src.start(t, Math.random() * 0.5); src.stop(t + duration + 0.02);
      src.onended = () => { src.disconnect(); filter.disconnect(); env.disconnect(); };
    }
    punch(big, delay = 0) {
      this.noise(big ? 0.16 : 0.09, big ? 0.55 : 0.35, big ? 1400 : 2600, delay);
      this.tone(big ? 180 : 260, 50, big ? 0.16 : 0.08, big ? 0.6 : 0.36, delay, 'sine');
    }
    block() { this.noise(0.05, 0.3, 2200, 0, 'highpass'); this.tone(1800, 1700, 0.05, 0.08, 0, 'sine'); }
    whoosh(delay = 0) { this.noise(0.22, 0.3, 900, delay, 'lowpass', true); }
    rise() {
      [72, 76, 79, 84, 88].forEach((m, k) => this.tone(440 * 2 ** ((m - 69) / 12), 440 * 2 ** ((m - 69) / 12), 0.09, 0.1, k * 0.06));
      this.whoosh(0.3);
    }
    slam(delay = 0) { this.punch(true, delay); this.noise(0.5, 0.7, 380, delay); }
    ko() {
      this.slam();
      [60, 55, 48].forEach((m, k) => this.tone(440 * 2 ** ((m - 69) / 12), 440 * 2 ** ((m - 70) / 12), 0.34, 0.16, 0.15 + k * 0.22));
    }
    blip() { this.tone(880, 1320, 0.06, 0.07); }
    events(events) {
      if (!this.live()) return;
      let hit = 0, big = false;
      for (const e of events) {
        const k = e.type;
        if (k === 'hit') { hit++; big = big || e.big || e.counter; }
        else if (k === 'block') this.block();
        else if (k === 'special') this.whoosh();
        else if (k === 'super' || k === 'fight') this.rise();
        else if (k === 'throw') { this.whoosh(); this.slam(0.45); }
        else if (k === 'armor') { this.punch(true); this.block(); }
        else if (k === 'crush' || k === 'clash') { this.block(); this.punch(true); }
        else if (k === 'round') this.ko();
      }
      if (hit) this.punch(big);
    }
    victory() { [523, 659, 784, 1046].forEach((f, i) => this.tone(f, f, 0.22, 0.13, i * 0.11)); }
  }
  window.BBAudio = Audio;
})();
