// 键盘 + 手机按钮。sample() 每帧取一次：{h, v, press}。
// h、v 是按住的绝对方向（右 +1、上 +1），press 是自上次取样以来新按下的键（攻击键或 dash+/dash-）。
// 朝向换算、攻击键缓冲都在 driver.py 里做，这里只管人手。
(function (root) {
  'use strict';
  const MOVE = { ArrowLeft: 'left', KeyA: 'left', ArrowRight: 'right', KeyD: 'right',
    ArrowUp: 'up', KeyW: 'up', ArrowDown: 'down', KeyS: 'down' };
  const BUTTON = { KeyJ: 'p', KeyK: 'h', KeyL: 'k', KeyU: 's', KeyI: 't', Space: 'z', KeyO: 'a', KeyP: 'x' };
  const DOUBLE_TAP_MS = 260;
  class Input {
    constructor(clock = () => (typeof performance !== 'undefined' ? performance.now() : Date.now())) {
      this.clock = clock; this.clear();
    }
    clear() {
      this.held = new Map(); this.order = 0; this.presses = []; this.lastTap = { dir: 0, at: -1e9 }; this.pad = { h: 0, v: 0 };
    }
    hold(token, dir) {
      if (this.held.has(token)) return;
      this.held.set(token, { dir, order: ++this.order });
      if (dir === 'left' || dir === 'right') this.tap(dir === 'right' ? 1 : -1);
    }
    release(token) { this.held.delete(token); }
    // 同一方向连按两下 = 冲刺（朝前）或后撤步（朝后），由驱动按朝向决定
    tap(h) {
      const now = this.clock();
      if (this.lastTap.dir === h && now - this.lastTap.at <= DOUBLE_TAP_MS) {
        this.press(h > 0 ? 'dash+' : 'dash-');
        this.lastTap = { dir: 0, at: -1e9 };
      } else this.lastTap = { dir: h, at: now };
    }
    press(key) { if (this.presses.length < 8) this.presses.push(key); }
    axis() {
      const held = [...this.held.values()].sort((a, b) => b.order - a.order);
      const pick = (a, b) => { const d = held.find(k => k.dir === a || k.dir === b); return d ? (d.dir === a ? 1 : -1) : 0; };
      const h = pick('right', 'left') || this.pad.h, v = pick('up', 'down') || this.pad.v;
      return { h, v };
    }
    sample() {
      const out = { ...this.axis(), press: this.presses };
      this.presses = [];
      return out;
    }
    setPad(h, v) {
      if (h && h !== this.pad.h) this.tap(h);
      this.pad = { h, v };
    }
    mount(element, active) {
      window.addEventListener('keydown', event => {
        const code = event.code;
        if (!active() || (!MOVE[code] && !BUTTON[code])) return;
        event.preventDefault();
        if (event.repeat) return;
        if (MOVE[code]) this.hold(code, MOVE[code]);
        else this.press(BUTTON[code]);
      });
      window.addEventListener('keyup', event => {
        this.release(event.code);
        if (active() && (MOVE[event.code] || BUTTON[event.code])) event.preventDefault();
      });
      window.addEventListener('blur', () => this.clear());
      // 摇杆：按住拖动，八个方向；中间一小圈是不动
      const pad = element.querySelector('[data-pad]');
      if (pad) {
        const knob = pad.querySelector('i');
        const move = event => {
          const r = pad.getBoundingClientRect(), dx = event.clientX - (r.left + r.width / 2), dy = event.clientY - (r.top + r.height / 2);
          const dead = r.width * 0.16, len = Math.hypot(dx, dy);
          let h = 0, v = 0;
          if (len > dead) {
            const ang = Math.atan2(-dy, dx), oct = Math.round(ang / (Math.PI / 4));
            h = [1, 1, 0, -1, -1, -1, 0, 1][(oct + 8) % 8];
            v = [0, 1, 1, 1, 0, -1, -1, -1][(oct + 8) % 8];
          }
          this.setPad(h, v);
          const k = Math.min(1, len / (r.width * 0.36));
          if (knob) knob.style.transform = `translate(${len ? dx / len * k * r.width * 0.28 : 0}px, ${len ? dy / len * k * r.width * 0.28 : 0}px)`;
          pad.dataset.dir = `${h},${v}`;
        };
        pad.addEventListener('pointerdown', event => {
          if (!active()) return;
          event.preventDefault(); pad.setPointerCapture(event.pointerId); pad.classList.add('pressed'); move(event);
        });
        pad.addEventListener('pointermove', event => { if (pad.hasPointerCapture(event.pointerId)) move(event); });
        const end = () => { this.setPad(0, 0); pad.classList.remove('pressed'); pad.dataset.dir = '0,0'; if (knob) knob.style.transform = ''; };
        ['pointerup', 'pointercancel', 'lostpointercapture'].forEach(type => pad.addEventListener(type, end));
      }
      element.querySelectorAll('[data-btn]').forEach(button => {
        button.addEventListener('pointerdown', event => {
          if (!active()) return;
          event.preventDefault();
          this.press(button.dataset.btn);
          button.classList.add('pressed');
        });
        const up = () => button.classList.remove('pressed');
        ['pointerup', 'pointercancel', 'pointerleave'].forEach(type => button.addEventListener(type, up));
        button.addEventListener('contextmenu', event => event.preventDefault());
      });
    }
  }
  Input.MOVE = MOVE; Input.BUTTON = BUTTON;
  root.BBInput = Input;
  if (typeof module !== 'undefined') module.exports = Input;
})(globalThis);
