(function (root) {
  'use strict';
  class Input {
    constructor() { this.clear(); }
    clear() { this.held = new Map(); this.order = 0; this.bombQueued = false; this.tapped = null; }
    press(token, action) {
      if (this.held.has(token)) return;
      this.held.set(token, { action, order: ++this.order });
      if (action === 'bomb') this.bombQueued = true;
      else this.tapped = action;   // 两次取样之间按下又松开的方向（手机上点一下）也要走一格
    }
    release(token) { this.held.delete(token); }
    sample() {
      const held = [...this.held.values()];
      if (this.bombQueued || held.some(key => key.action === 'bomb')) {
        this.bombQueued = false;
        return 'bomb';
      }
      const dir = held.filter(key => key.action !== 'bomb').sort((a, b) => b.order - a.order)[0]?.action;
      const tap = this.tapped;
      this.tapped = null;
      return dir || tap || 'stay';
    }
    mount(element, active) {
      const keys = { ArrowUp: 'up', KeyW: 'up', ArrowDown: 'down', KeyS: 'down',
        ArrowLeft: 'left', KeyA: 'left', ArrowRight: 'right', KeyD: 'right', Space: 'bomb', KeyJ: 'bomb' };
      window.addEventListener('keydown', event => {
        if (!active() || !keys[event.code]) return;
        event.preventDefault();
        this.press(event.code, keys[event.code]);
      });
      window.addEventListener('keyup', event => {
        this.release(event.code);
        if (active() && keys[event.code]) event.preventDefault();
      });
      window.addEventListener('blur', () => this.clear());
      element.querySelectorAll('[data-action]').forEach(button => {
        button.addEventListener('pointerdown', event => {
          if (!active()) return;
          event.preventDefault();
          button.setPointerCapture(event.pointerId);
          this.press(`pointer:${event.pointerId}`, button.dataset.action);
          button.classList.add('pressed');
        });
        const release = event => {
          this.release(`pointer:${event.pointerId}`);
          button.classList.remove('pressed');
        };
        ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(type => button.addEventListener(type, release));
        button.addEventListener('contextmenu', event => event.preventDefault());
      });
    }
  }
  root.BPInput = Input;
  if (typeof module !== 'undefined') module.exports = Input;
})(globalThis);
