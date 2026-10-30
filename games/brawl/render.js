// 像素拳斗画法：每一帧只看回放里的冻结快照，任意帧号都能直接画（可 seek）。
// 场地是 1920×1080 的高清图；人物、特效在 384×216 原生像素画布上画，再整数放大 5 倍叠上去；血条和字在大画布上画。
// 需要 window.SPR（角色精灵，每张带 img）、window.FX（特效帧）、window.STAGE（场地图），都由 sprites.js 准备；
// 图没加载好时只画能画的，不抛错（HyperFrames 渲染遇到页面报错会整片放弃）。
(function () {
  'use strict';
  const NW = 384, NH = 216, K = 5, GY = 178;
  const CHAR = {
    lie: { name: '阿烈', z: '烈波', a: '升龙拳', x: '超必杀·烈风连拳', col: '#ff6a3a' },
    tie: { name: '铁山', z: '铁山摔', a: '铁头槌', x: '超必杀·山崩大摔', col: '#4fd17a' },
    yan: { name: '飞燕', z: '飞燕膝', a: '倒翻踢', x: '超必杀·燕返连环腿', col: '#6cd6ff' },
    rei: { name: '雷娜', z: '雷球', a: '落雷柱', x: '超必杀·雷霆光束', col: '#c88bff' },
  };
  // 招式帧数（起手、判定、收招），只用来挑姿势；和 engine.py 的招式表一致
  const MOVES = {
    lie: { p: [3, 2, 6], h: [7, 3, 14], k: [6, 3, 14], s: [7, 3, 18], t: [2, 1, 20], z: [12, 1, 24], a: [4, 8, 26], x: [6, 15, 30], air: [4, 10, 0] },
    tie: { p: [4, 2, 7], h: [9, 4, 17], k: [7, 3, 14], s: [8, 3, 20], t: [2, 1, 20], z: [5, 2, 30], a: [5, 6, 34], x: [3, 3, 48], air: [5, 9, 0] },
    yan: { p: [3, 2, 5], h: [6, 3, 13], k: [5, 3, 14], s: [6, 3, 15], t: [2, 1, 20], z: [6, 9, 18], a: [3, 7, 24], x: [5, 18, 28], air: [3, 10, 0] },
    rei: { p: [3, 2, 7], h: [9, 3, 16], k: [7, 3, 15], s: [8, 3, 19], t: [2, 1, 20], z: [14, 1, 22], a: [6, 8, 24], x: [10, 1, 34], air: [5, 8, 0] },
  };
  const ok = (im) => im && im.complete && im.naturalWidth > 0;
  const ready = () => window.SPR && Object.values(window.SPR).every(c => Object.values(c).every(p => ok(p.img)));

  // ---------- 姿势 ----------
  // 返回 [精灵名, 旋转角度, 竖直偏移]
  function spriteOf(f, t) {
    const c = f.char, mv = f.mv, mt = mv ? MOVES[c][mv] : null;
    const s = mt ? mt[0] : 0, a = mt ? mt[1] : 0, r = mt ? mt[2] : 0;
    const hitPh = f.mf > s && f.mf <= s + a + Math.ceil(r / 2);
    switch (f.st) {
      case 'stand': return ['stance', 0, Math.floor(t / 12) % 2];
      case 'walk': return [Math.floor(t / 7) % 2 ? 'walk' : 'stance', 0, 0];
      case 'crouch': case 'prejump': case 'land': case 'wake': return ['crouch', 0, 0];
      case 'air':
        if (f.mv === 'air' && f.mf > s) return [c === 'tie' ? 'heavy' : 'kick', c === 'tie' ? 20 : 22, 0];
        return ['jump', 0, 0];
      case 'dash': return ['walk', 0, 0];
      case 'backdash': return ['block', 0, 0];
      case 'blockstun': return [f.low ? 'crouch' : 'block', 0, 0];
      case 'hitstun': return ['hit', 0, 0];
      case 'knock': return f.y > 2 ? ['hit', -40 - Math.min(40, f.y), 0] : ['lying', 0, 0];
      case 'ko': return ['lying', 0, 0];
      case 'win': return ['win', 0, 0];
      case 'thrown': return ['hit', -Math.min(1, f.mf / 16) * 200, 0];
      case 'throw':
        if (c === 'tie') {
          if (mv === 't') return [f.mf < 9 ? 'grab' : 'super', 0, 0];
          return [f.mf < 4 ? 'grab' : (f.mf < 12 ? 'upper' : 'super'), 0, 0];
        }
        return [f.mf < 9 ? 'grab' : 'heavy', 0, 0];
      case 'attack': {
        if (mv === 'p') return [hitPh ? 'jab' : 'stance', 0, 0];
        if (mv === 'h') return [hitPh ? 'heavy' : 'stance', 0, 0];
        if (mv === 'k') return [hitPh ? 'kick' : 'stance', 0, 0];
        if (mv === 's') return [hitPh ? 'sweep' : 'crouch', 0, 0];
        if (mv === 't') return [f.mf > s ? 'grab' : 'stance', 0, 0];
        if (mv === 'z') {
          if (c === 'tie') return [f.mf > s - 2 ? 'grab' : 'stance', 0, 0];
          if (c === 'yan') return [f.mf > 2 && f.mf <= s + a + 4 ? 'special' : 'crouch', 0, 0];
          return [f.mf > 3 ? 'special' : 'stance', 0, 0];
        }
        if (mv === 'a') {
          if (c === 'tie') return [f.mf > s ? 'special' : 'block', 0, 0];
          if (c === 'rei') return [f.mf > 2 ? 'upper' : 'crouch', 0, 0];
          return [f.mf <= s ? 'crouch' : (f.y > 0 || f.mf <= s + a ? 'upper' : 'crouch'), 0, 0];
        }
        if (mv === 'x') {
          if (c === 'tie') return [f.mf > 1 ? 'grab' : 'stance', 0, 0];
          if (c === 'rei') return [f.mf > 3 ? 'super' : 'stance', 0, 0];
          if (f.mf <= s) return ['stance', 0, 0];
          if (f.mf <= s + a) return [Math.floor(f.mf / 3) % 2 ? 'super' : (c === 'yan' ? 'kick' : 'jab'), 0, 0];
          return ['stance', 0, 0];
        }
      }
    }
    return ['stance', 0, 0];
  }

  const tintCache = new Map();
  function tinted(img, col) {
    const key = img.src.slice(-48) + img.width + col;
    if (tintCache.has(key)) return tintCache.get(key);
    const c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0); g.globalCompositeOperation = 'source-in'; g.fillStyle = col; g.fillRect(0, 0, c.width, c.height);
    tintCache.set(key, c);
    return c;
  }
  // 同角色对打时 2P 换一套衣服颜色：只转角色招牌色附近、饱和度高的像素（衣服），肤色不动
  const ALT = { lie: [8, 22, 215], tie: [125, 30, 350], yan: [195, 25, 45], rei: [280, 25, 140] };   // [招牌色相, 半宽, 换成的色相]
  const altCache = new Map();
  function altImg(img, ch) {
    const key = img.src.length + ':' + img.src.slice(-40) + ch;
    if (altCache.has(key)) return altCache.get(key);
    const c = document.createElement('canvas'); c.width = img.naturalWidth; c.height = img.naturalHeight;
    const x = c.getContext('2d'); x.drawImage(img, 0, 0);
    const d = x.getImageData(0, 0, c.width, c.height), a = d.data, [hc, hw, to] = ALT[ch];
    for (let i = 0; i < a.length; i += 4) {
      if (!a[i + 3]) continue;
      const r = a[i] / 255, gg = a[i + 1] / 255, b = a[i + 2] / 255, mx = Math.max(r, gg, b), mn = Math.min(r, gg, b), l = (mx + mn) / 2, dd = mx - mn;
      if (dd < 0.12) continue;
      const sat = dd / (1 - Math.abs(2 * l - 1));
      let h = mx === r ? ((gg - b) / dd) % 6 : mx === gg ? (b - r) / dd + 2 : (r - gg) / dd + 4;
      h = (h * 60 + 360) % 360;
      if (sat < 0.4 || Math.min(Math.abs(h - hc), 360 - Math.abs(h - hc)) > hw) continue;
      const H = to / 60, C = dd, X = C * (1 - Math.abs(H % 2 - 1)), m = l - C / 2;
      const [R1, G1, B1] = H < 1 ? [C, X, 0] : H < 2 ? [X, C, 0] : H < 3 ? [0, C, X] : H < 4 ? [0, X, C] : H < 5 ? [X, 0, C] : [C, 0, X];
      a[i] = (R1 + m) * 255; a[i + 1] = (G1 + m) * 255; a[i + 2] = (B1 + m) * 255;
    }
    x.putImageData(d, 0, 0);
    altCache.set(key, c);
    return c;
  }

  function drawFighter(g, f, t, tint, alpha) {
    const [name, rot, dy] = spriteOf(f, t);
    const sp = window.SPR?.[f.char]?.[name];
    if (!sp || !ok(sp.img)) return;
    const img = tint ? tinted(sp.img, tint) : (f.alt ? altImg(sp.img, f.char) : sp.img);
    g.save();
    if (alpha != null) g.globalAlpha = alpha;
    if (rot) {
      g.translate(Math.round(f.x), Math.round(GY - f.y - sp.h * 0.45));
      g.scale(f.face, 1); g.rotate(rot * Math.PI / 180);
      g.drawImage(img, -Math.round(sp.ax), Math.round(-sp.h * 0.55 + dy));
    } else {
      g.translate(Math.round(f.x), 0); g.scale(f.face, 1);
      g.drawImage(img, -Math.round(sp.ax), Math.round(GY - f.y - sp.h + dy));
    }
    g.restore();
  }

  // ---------- 原生画布上的特效 ----------
  const disc = {};
  function spans(r) {
    const key = r.toFixed(1);
    if (disc[key]) return disc[key];
    const out = [], R = Math.ceil(r);
    for (let y = -R; y <= R; y++) { const w = Math.floor(Math.sqrt(Math.max(0, r * r - y * y)) + 0.35); out.push([y, w]); }
    return (disc[key] = out);
  }
  function stamp(g, x, y, r, col) {
    g.fillStyle = col;
    const X = Math.round(x), Y = Math.round(y);
    for (const [dy, w] of spans(r)) g.fillRect(X - w, Y + dy, w * 2 + 1, 1);
  }
  function seg(g, a, b, r, col) {
    const n = Math.max(1, Math.ceil(Math.hypot(b[0] - a[0], b[1] - a[1]) * 1.5));
    for (let i = 0; i <= n; i++) stamp(g, a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n, r, col);
  }
  function drawProj(g, p, t) {
    const x = Math.round(p.x), y = GY - p.y, dir = p.vx > 0 ? 1 : -1;
    if (p.look === 'beam') {
      // 光束：从发射者一路连到弹头，抖动的紫白色带
      const len = 150, x0 = x - dir * len;
      for (let k = 0; k < 3; k++) {
        const hw = [16, 10, 4][k] + Math.sin(t * 1.7 + k) * 1.5, col = ['#5a2a9a', '#b77bff', '#f4e9ff'][k];
        g.fillStyle = col; g.fillRect(Math.min(x0, x), Math.round(y - hw / 2 - 20), Math.abs(x - x0), Math.round(hw));
      }
      stamp(g, x, y - 20, 13 + Math.sin(t) * 1.5, '#b77bff'); stamp(g, x, y - 20, 8, '#f4e9ff');
      for (let i = 0; i < 6; i++) {
        const xx = x0 + dir * ((t * 9 + i * 29) % len);
        seg(g, [xx, y - 20], [xx + dir * 8, y - 20 + ((i % 2) ? 12 : -12)], 0.6, '#ffffff');
      }
      return;
    }
    const key = p.look === 'bolt' ? 'zap' : 'ki';
    const fr = window.FX?.[`${key}_${Math.floor(t / 3) % 3}`];
    if (fr && ok(fr.img)) {
      // 拖尾
      for (let i = 3; i >= 1; i--) stamp(g, x - dir * i * 6, y + Math.sin(t * 0.7 + i), 4 - i, key === 'zap' ? '#8a4ad8' : '#ff9a3a');
      g.save(); g.translate(x, Math.round(y)); g.scale(dir, 1);
      g.drawImage(fr.img, -Math.round(fr.ax), -Math.round(fr.ay)); g.restore();
    } else {
      stamp(g, x, y, 7, key === 'zap' ? '#b77bff' : '#ff9a3a'); stamp(g, x, y, 4, '#fff');
    }
  }
  function pillar(g, f, t) {
    // 雷娜的落雷柱：判定区（身前 16–52）上方劈下来的闪电
    const m = MOVES.rei.a, k = f.mf - m[0];
    if (k < -2 || k > m[1] + 3) return;
    const x0 = f.x + f.face * 34, top = 0, bot = GY;
    const w = k < 0 ? 2 : (k <= m[1] ? 9 : 4);
    g.fillStyle = k < 0 ? 'rgba(200,140,255,.5)' : '#b77bff'; g.fillRect(Math.round(x0 - w), top, w * 2, bot);
    g.fillStyle = '#f4e9ff'; g.fillRect(Math.round(x0 - w / 3), top, Math.max(1, Math.round(w * 2 / 3)), bot);
    let px = x0, py = 0;
    for (let i = 0; i < 8; i++) { const nx = x0 + ((i * 37 + t * 13) % 21) - 10, ny = py + bot / 8; seg(g, [px, py], [nx, ny], 0.6, '#ffffff'); px = nx; py = ny; }
    stamp(g, x0, GY - 2, 6 + (t % 3), '#e4cfff');
  }
  function spark(g, e, age, kind) {
    const x = e.x, y = GY - e.y, big = e.big || e.counter;
    const n = kind === 'block' ? 6 : 10, R = (kind === 'block' ? 7 : big ? 16 : 10) * (0.4 + age / 6);
    const col = kind === 'block' ? ['#d8f2ff', '#4fa3ff'] : kind === 'armor' ? ['#ffffff', '#ff4a4a'] : ['#fff7c2', big ? '#ff6a2a' : '#ffc23a'];
    for (let i = 0; i < n; i++) {
      const ang = i / n * Math.PI * 2 + (e.t % 7);
      seg(g, [x + Math.cos(ang) * R * 0.3, y + Math.sin(ang) * R * 0.3], [x + Math.cos(ang) * R, y + Math.sin(ang) * R], age < 3 ? 1.3 : 0.6, col[i % 2]);
    }
    if (age < 3) stamp(g, x, y, big ? 6 : 3, '#ffffff');
  }
  function dust(g, x, age) {
    for (let i = 0; i < 5; i++) stamp(g, x + (i - 2) * (4 + age), GY - 2 - age * 0.6 - (i % 2) * 2, Math.max(0.5, 3 - age * 0.3), 'rgba(230,210,180,.7)');
  }

  // ---------- 大画布上的血条、计时、能量和字 ----------
  function txt(ctx, s, x, y, size, col, align, stroke) {
    ctx.font = `900 ${size}px "PingFang SC", "Noto Sans CJK SC", sans-serif`;
    ctx.textAlign = align || 'center';
    ctx.lineJoin = 'round'; ctx.lineWidth = stroke ?? size / 5.5; ctx.strokeStyle = '#000';
    ctx.strokeText(s, x, y); ctx.fillStyle = col; ctx.fillText(s, x, y);
  }
  function hud(ctx, R, idx, opt) {
    const fr = R.frames[idx], names = opt.names || R.seats || ['1P', '2P'];
    const trail = [0, 1].map(i => { let h = fr.f[i].hp; for (let k = 1; k <= 24; k++) { const q = R.frames[Math.max(0, idx - k)]; if (q.f[i] && q.round === fr.round) h = Math.max(h, q.f[i].hp); } return h; });
    const W = 720, H = 42, Y = 48;
    ctx.save();
    for (const i of [0, 1]) {
      const f = fr.f[i], x0 = i ? 1920 - 110 - W : 110, hp = f.hp / f.max_hp, tr = trail[i] / f.max_hp;
      ctx.fillStyle = '#000'; ctx.fillRect(x0 - 6, Y - 6, W + 12, H + 12);
      ctx.fillStyle = '#3a0d12'; ctx.fillRect(x0, Y, W, H);
      const fill = (k, col) => { ctx.fillStyle = col; const w = Math.round(W * Math.max(0, k)); ctx.fillRect(i ? x0 + W - w : x0, Y, w, H); };
      fill(tr, '#e8402e');
      fill(hp, hp < 0.3 ? (Math.floor(fr.t / 6) % 2 ? '#ffe14a' : '#ff9a2e') : '#ffd23a');
      ctx.fillStyle = 'rgba(255,255,255,.35)'; ctx.fillRect(x0, Y + 5, W, 7);
      const lx = i ? x0 + W : x0;
      txt(ctx, names[i], lx, Y + H + 54, 44, '#ffffff', i ? 'right' : 'left', 9);
      ctx.font = '900 44px "PingFang SC", sans-serif';
      const nw = ctx.measureText(names[i]).width;
      txt(ctx, CHAR[f.char].name, i ? lx - nw - 18 : lx + nw + 18, Y + H + 52, 34, CHAR[f.char].col, i ? 'right' : 'left', 8);
      for (let k = 0; k < 2; k++) {
        const bx = i ? 960 + 88 + k * 34 : 960 - 112 - k * 34;
        ctx.fillStyle = '#000'; ctx.fillRect(bx - 3, Y + H + 14, 28, 28);
        ctx.fillStyle = fr.wins[i] > k ? '#ffd23a' : '#3b3b4a'; ctx.fillRect(bx, Y + H + 17, 22, 22);
      }
      const m = f.meter, gx = i ? 1920 - 110 - 480 : 110, gy = 1080 - 82;
      ctx.fillStyle = '#000'; ctx.fillRect(gx - 5, gy - 5, 490, 34);
      for (let k = 0; k < 3; k++) {
        const v = Math.max(0, Math.min(1, (m - k * 100) / 100));
        ctx.fillStyle = '#1b2440'; ctx.fillRect(gx + k * 162, gy, 156, 24);
        ctx.fillStyle = v >= 1 ? (Math.floor(fr.t / 5) % 2 ? '#7cf3ff' : '#3fb7ff') : '#2a6fd6';
        const w = Math.round(156 * v); ctx.fillRect(i ? gx + k * 162 + 156 - w : gx + k * 162, gy, w, 24);
      }
      const stocks = Math.floor(m / 100);
      txt(ctx, `气 ${stocks}`, i ? gx + 480 : gx, gy - 14, 32, stocks ? '#7cf3ff' : '#cfd7ff', i ? 'right' : 'left', 7);
    }
    ctx.fillStyle = '#000'; ctx.fillRect(960 - 62, 26, 124, 96);
    ctx.fillStyle = '#20182e'; ctx.fillRect(960 - 56, 32, 112, 84);
    ctx.font = 'bold 72px "Menlo", monospace'; ctx.textAlign = 'center'; ctx.fillStyle = fr.timer <= 10 ? '#ff5a4a' : '#ffffff';
    ctx.fillText(String(Math.max(0, fr.timer)).padStart(2, '0'), 960, 100);
    ctx.restore();
  }
  function bigText(ctx, s, y, size, col, k) {
    ctx.save(); ctx.globalAlpha = Math.max(0, Math.min(1, k)); txt(ctx, s, 960, y, size, col); ctx.restore();
  }

  function natCanvas() {
    if (!window.__brawlNat) { const c = document.createElement('canvas'); c.width = NW; c.height = NH; window.__brawlNat = c; }
    return window.__brawlNat;
  }

  // ---------- 一帧 ----------
  window.drawFight = function (ctx, R, idx, opt = {}) {
    idx = Math.max(0, Math.min(R.frames.length - 1, Math.floor(idx)));
    const fr = R.frames[idx], t = fr.t;
    ctx.save();
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = '#120c1c'; ctx.fillRect(0, 0, 1920, 1080);
    const recent = [];
    for (let k = 0; k <= 40; k++) { const q = R.frames[idx - k]; if (!q) break; for (const e of q.ev) recent.push([e, k]); }
    let shake = 0;
    for (const [e, age] of recent) if (age < 7 && ((e.type === 'hit' && e.big) || e.type === 'throw' || e.type === 'crush')) shake = Math.max(shake, 7 - age);
    const sx = shake ? Math.round(Math.sin(t * 2.3) * shake * 0.7) * K : 0, sy = shake ? Math.round(Math.cos(t * 3.1) * shake * 0.5) * K : 0;
    if (ok(window.STAGE)) { ctx.imageSmoothingEnabled = true; ctx.drawImage(window.STAGE, sx - 20, sy - 12, 1960, 1104); ctx.imageSmoothingEnabled = false; }
    if (!fr.f.length || !ready()) {
      bigText(ctx, '选择角色', 560, 140, '#ffffff', 1);
      ctx.restore();
      return;
    }
    const nat = natCanvas(), g = nat.getContext('2d');
    g.clearRect(0, 0, NW, NH);
    g.imageSmoothingEnabled = false;
    // 超必杀定格：暗场
    if (fr.flash) { ctx.fillStyle = 'rgba(8,4,20,0.68)'; ctx.fillRect(0, 0, 1920, 1080); }
    for (const f of fr.f) { g.fillStyle = 'rgba(0,0,0,0.38)'; const w = 30 - Math.min(12, f.y / 5); g.fillRect(Math.round(f.x - w / 2), GY - 1, Math.round(w), 3); }
    // 冲刺、超必杀残影
    for (const [i, f] of fr.f.entries()) {
      const fast = f.st === 'dash' || (f.st === 'attack' && ((f.mv === 'x' && f.char !== 'rei' && f.char !== 'tie') || (f.mv === 'z' && f.char === 'yan')));
      if (fast) for (let k = 3; k >= 1; k--) { const q = R.frames[idx - k * 2]; if (q && q.f[i]) drawFighter(g, q.f[i], t, k === 1 ? CHAR[f.char].col : '#5a2a6a', 0.55 - k * 0.12); }
    }
    for (const [i, f] of fr.f.entries()) if (f.st === 'attack' && f.mv === 'a' && f.char === 'rei') pillar(g, f, t);
    const mirror = fr.f[0].char === fr.f[1].char;
    const order = [0, 1].sort((a, b) => (/attack|throw/.test(fr.f[a].st) ? 1 : 0) - (/attack|throw/.test(fr.f[b].st) ? 1 : 0));
    for (const i of order) {
      const f = { ...fr.f[i], alt: mirror && i === 1 };
      if (f.st === 'blockstun') { f.low = false; for (let k = 1; k < 24; k++) { const q = R.frames[idx - k]; if (!q || !q.f[i]) break; if (q.f[i].st !== 'blockstun') { f.low = q.f[i].st === 'crouch'; break; } } }
      const o = fr.f[1 - i];
      if (f.st === 'thrown' && o.st === 'throw' && o.char === 'tie' && o.mv !== 't') {
        // 铁山的指令投：先举过头顶，再砸到身前
        const up = Math.min(1, f.mf / 9), down = f.mf >= 12 ? Math.min(1, (f.mf - 12) / 6) : 0;
        f.x = o.x + o.face * (4 + 26 * down); f.y = 74 * up * (1 - down); f.face = -o.face;
        drawFighterRot(g, f, t, -90 - 90 * down);
        continue;
      }
      drawFighter(g, f, t, null);
      const superOn = fr.flash && recent.some(([e, a]) => e.type === 'super' && e.id === i && a < 20);
      if (superOn && Math.floor(t / 3) % 2) drawFighter(g, f, t, '#fff4c0', 0.35);
      if (f.st === 'hitstun' && f.stun > 0 && recent.some(([e, a]) => e.type === 'hit' && e.id === i && a < 2)) drawFighter(g, f, t, '#ffffff', 0.6);
    }
    for (const p of fr.proj) drawProj(g, p, t);
    for (const [e, age] of recent) {
      if ((e.type === 'hit' || e.type === 'block' || e.type === 'armor') && age < 8) spark(g, e, age, e.type);
      if (e.type === 'clash' && age < 9) spark(g, { x: e.x, y: 47, t: e.t, big: true }, age, 'block');
      if (e.type === 'throw' && age >= 18 && age < 30) dust(g, fr.f[e.id].x, age - 18);
    }
    ctx.drawImage(nat, sx, sy, NW * K, NH * K);
    hud(ctx, R, idx, opt);
    // 字：招式名、连击、反击、破防、K.O.
    for (const i of [0, 1]) {
      let combo = 0, age = 99;
      for (const [e, a] of recent) if (e.type === 'hit' && e.by === i && a < age) { combo = e.combo; age = a; }
      if (combo >= 2 && age < 40) txt(ctx, `${combo} 连击`, i ? 1840 : 80, 330, 76, '#ffd23a', i ? 'right' : 'left');
    }
    for (const [e, age] of recent) {
      const side = (id) => [id ? 1840 : 80, id ? 'right' : 'left'];
      if (e.type === 'hit' && e.counter && age < 24) { const [x, al] = side(e.by); txt(ctx, '反击！', x, 410, 54, '#ff5a4a', al); }
      if (e.type === 'armor' && age < 24) { const [x, al] = side(e.id); txt(ctx, '硬吃！', x, 410, 58, '#ff8a4a', al); }
      if (e.type === 'crush' && age < 30) bigText(ctx, '破防！', 300, 110, '#7cf3ff', 1 - age / 30);
      if (e.type === 'tech' && age < 20) bigText(ctx, '拆投', 300, 90, '#ffffff', 1 - age / 20);
      if (e.type === 'throw' && e.cmd && !e.super && age < 26) { const [x, al] = side(e.by); txt(ctx, CHAR[fr.f[e.by].char].z, x, 250, 56, '#ffffff', al); }
      if (e.type === 'special' && age < 22) {
        const ch = fr.f[e.id].char;
        if (!(ch === 'tie' && e.mv === 'z')) { const [x, al] = side(e.id); txt(ctx, CHAR[ch][e.mv], x, 250, 52, '#ffffff', al); }
      }
    }
    for (const [e, age] of recent) if (e.type === 'super' && age < 40) {
      const k = Math.min(1, age / 4);
      ctx.save(); ctx.fillStyle = `rgba(0,0,0,${0.6 * (1 - age / 40)})`; ctx.fillRect(0, 470, 1920, 150);
      txt(ctx, CHAR[fr.f[e.id].char].x, e.id ? 1920 - 960 * k : 960 * k, 580, 96, '#ffe14a'); ctx.restore();
    }
    for (const [e, age] of recent) if (e.type === 'round' && age < 40) {
      const s = e.reason === 'time' ? '时间到' : (e.reason === 'double_ko' ? '双倒' : 'K.O.');
      bigText(ctx, s, 420, 240, e.reason === 'time' ? '#ffffff' : '#ff3a3a', age < 3 ? age / 3 : 1);
    }
    const names = opt.names || R.seats || ['1P', '2P'];
    if (fr.phase === 'end' && !recent.some(([e, a]) => e.type === 'round' && a < 40)) {
      let w;
      for (let k = 0; k < 200 && R.frames[idx - k]; k++) { const e = R.frames[idx - k].ev.find(x => x.type === 'round'); if (e) { w = e.win[0]; break; } }
      bigText(ctx, w !== undefined ? `${names[w]} 胜` : '平局', 400, 130, '#ffffff', 1);
    }
    if (fr.phase === 'over') {
      const w = fr.wins[0] === fr.wins[1] ? -1 : (fr.wins[0] > fr.wins[1] ? 0 : 1);
      bigText(ctx, w >= 0 ? `${names[w]} 赢下比赛` : '平局', 400, 120, '#ffd23a', 1);
    }
    if (fr.phase === 'intro') bigText(ctx, fr.round >= 3 && fr.wins[0] === fr.wins[1] ? '决胜局' : `第 ${fr.round} 回合`, 400, 140, '#ffffff', 1);
    for (const [e, age] of recent) if (e.type === 'fight' && age < 20) bigText(ctx, '开打！', 400, 190, '#ffd23a', 1 - age / 20);
    ctx.restore();
  };
  function drawFighterRot(g, f, t, deg) {
    const sp = window.SPR?.[f.char]?.hit;
    if (!sp || !ok(sp.img)) return;
    g.save(); g.translate(Math.round(f.x), Math.round(GY - f.y - sp.h * 0.45)); g.scale(f.face, 1); g.rotate(deg * Math.PI / 180);
    g.drawImage(f.alt ? altImg(sp.img, f.char) : sp.img, -Math.round(sp.ax), Math.round(-sp.h * 0.55)); g.restore();
  }
  window.brawlChars = CHAR;
})();
// 正片模板（video/template.html 的整屏场景）按 drawBoard(ctx, G, 帧号, {names}) 调用，这里接到 drawFight。
window.drawBoard = window.drawBoard || function (ctx, G, turn, opt) { window.drawFight(ctx, G, turn, { names: opt && opt.names }); };
window.drawBoardRing = window.drawBoardRing || function () {};
