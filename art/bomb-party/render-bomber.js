// 炸弹人新画面（试做）：只看回放的逐回合快照，按小数回合号插值画（可 seek）。
// window.ART 是切好的精灵（Image），window.STAGE 是 1920×1080 的场地背景。
(function () {
  'use strict';
  const COLORS = { opus: '#FF9838', astra: '#1FC77E', gemini: '#A57BFF', deepseek: '#4567FF', kimi: '#F2F2F2',
                   doubao: '#2FD3E6', qwen: '#F05BC9', glm: '#FFDD3C', minimax: '#FF4B4B', grok: '#9BE23A', baseline: '#C8CCD6' };
  const NAMES = { opus: 'Claude', astra: 'GPT', gemini: 'Gemini', deepseek: 'DeepSeek', kimi: 'Kimi', doubao: '豆包',
                  qwen: '千问', glm: 'GLM', minimax: 'MiniMax', grok: 'Grok', baseline: '陪练',
                  aggressive: '陪练·激进', farmer: '陪练·发育', kicker: '陪练·踢弹' };
  COLORS.aggressive = '#FF4B4B'; COLORS.farmer = '#FFDD3C'; COLORS.kicker = '#A57BFF'; COLORS.baseline = '#2FD3E6';
  const ITEM = { fire: 'pu_fire', bomb: 'pu_bomb', kick: 'pu_kick' }, ITEM_TXT = { fire: '火力+1', bomb: '炸弹+1', kick: '学会踢弹' };
  const HERO = ['down', 'down_walk', 'up', 'up_walk', 'right', 'right_walk', 'place', 'victory', 'dizzy', 'ko', 'wave', 'thumb'];

  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  // Image 要加载完才能画；canvas（换色后的缓存）总是可用
  const ready = (im) => !!im && (im instanceof HTMLCanvasElement || (im.complete && im.naturalWidth > 0));
  const ease = (k) => k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
  function rgb2hsl(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), l = (mx + mn) / 2;
    if (mx === mn) return [0, 0, l];
    const d = mx - mn, s = l > 0.5 ? d / (2 - mx - mn) : d / (mx + mn);
    let h = mx === r ? (g - b) / d + (g < b ? 6 : 0) : mx === g ? (b - r) / d + 2 : (r - g) / d + 4;
    return [h * 60, s, l];
  }
  function hsl2rgb(h, s, l) {
    const f = (n) => { const k = (n + h / 30) % 12, a = s * Math.min(l, 1 - l); return 255 * (l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1))); };
    return [f(0), f(8), f(4)];
  }
  // 把机器人身上的青色（队伍色）换成选手的颜色
  const tinted = {};
  function heroFor(seat, pose, color) {
    const key = seat + '|' + pose + (color ? '|' + color : '');
    if (tinted[key]) return tinted[key];
    const img = window.ART['hero_' + pose];
    // 图还没加载完就先不画、不缓存：getImageData 遇到 0 宽会抛错，HyperFrames 一遇页面报错就整片放弃（10/28 第 8 集）
    if (!ready(img)) return null;
    const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
    const g = c.getContext('2d'); g.drawImage(img, 0, 0);
    const d = g.getImageData(0, 0, c.width, c.height), px = d.data;
    const hex = color || COLORS[seat] || '#C8CCD6';
    const [th, ts, tl] = rgb2hsl(parseInt(hex.slice(1, 3), 16), parseInt(hex.slice(3, 5), 16), parseInt(hex.slice(5, 7), 16));
    for (let i = 0; i < px.length; i += 4) {
      if (!px[i + 3]) continue;
      const [h, s, l] = rgb2hsl(px[i], px[i + 1], px[i + 2]);
      if (h > 160 && h < 205 && s > 0.3 && l > 0.15) {
        const nl = clamp(l + (tl - 0.5) * 0.6, 0.08, 0.95);
        const [r, gg, b] = hsl2rgb(th, ts < 0.05 ? 0 : Math.max(ts, 0.55), nl);
        px[i] = r; px[i + 1] = gg; px[i + 2] = b;
      }
    }
    g.putImageData(d, 0, 0);
    return (tinted[key] = c);
  }

  function geom(G) {
    const cell = G.w <= 15 ? 64 : 32, bw = G.w * cell;
    return { cell, ox: Math.round(960 - bw / 2), oy: Math.round(540 - bw / 2) + 4 };
  }
  function at(G, t) { return G.frames[clamp(t, 0, G.frames.length - 1)]; }
  function sprite(ctx, img, cx, by, scale, opt = {}) {
    // cx 横向中心，by 底边；scale 是原生像素到屏幕的倍数
    if (!ready(img)) return;
    const w = img.width * scale, h = img.height * scale;
    ctx.save();
    if (opt.alpha !== undefined) ctx.globalAlpha = opt.alpha;
    ctx.translate(Math.round(cx), Math.round(by - h / 2));
    if (opt.rot) ctx.rotate(opt.rot);
    if (opt.flip) ctx.scale(-1, 1);
    ctx.drawImage(img, Math.round(-w / 2), Math.round(-h / 2), Math.round(w), Math.round(h));
    ctx.restore();
  }
  function facing(G, i, t) {
    for (let k = t; k > Math.max(0, t - 40); k--) {
      const a = at(G, k - 1).players[i], b = at(G, k).players[i];
      if (a.x !== b.x || a.y !== b.y) return [Math.sign(b.x - a.x), Math.sign(b.y - a.y)];
    }
    return [0, 1];
  }
  function flamePieces(G, t) {
    const F = at(G, t), prev = at(G, t - 1), set = new Set(F.flames.map(([x, y]) => x + ',' + y));
    const centers = new Set();
    for (const b of prev.bombs.filter(b => !F.bombs.some(q => q.id === b.id))) {
      centers.add(b.x + ',' + b.y);
      if (b.sliding && b.direction) { const d = { up: [0, -1], down: [0, 1], left: [-1, 0], right: [1, 0] }[b.direction] || [0, 0]; centers.add((b.x + d[0]) + ',' + (b.y + d[1])); }
    }
    const out = [];
    for (const [x, y] of F.flames) {
      const k = x + ',' + y;
      if (centers.has(k)) { out.push([x, y, 'fire_c', 0]); continue; }
      const L = set.has((x - 1) + ',' + y), R = set.has((x + 1) + ',' + y), U = set.has(x + ',' + (y - 1)), D = set.has(x + ',' + (y + 1));
      if (L && R) out.push([x, y, 'fire_h', 0]);
      else if (U && D) out.push([x, y, 'fire_h', Math.PI / 2]);
      else if (L) out.push([x, y, 'fire_end', 0]);
      else if (R) out.push([x, y, 'fire_end', Math.PI]);
      else if (U) out.push([x, y, 'fire_end', Math.PI / 2]);
      else if (D) out.push([x, y, 'fire_end', -Math.PI / 2]);
      else out.push([x, y, 'fire_c', 0]);
    }
    return out;
  }

  window.drawBomber = function (ctx, G, tf, opt = {}) {
    const A = window.ART, t = clamp(Math.floor(tf), 0, G.frames.length - 1), k = clamp(tf - t, 0, 0.999);
    const F = at(G, t), N = at(G, t + 1), P = at(G, t - 1), over = t >= G.frames.length - 1;
    const { cell, ox, oy } = geom(G), sc = cell / 32;
    ctx.imageSmoothingEnabled = false;
    if (ready(window.STAGE)) ctx.drawImage(window.STAGE, 0, 0, 1920, 1080);
    ctx.fillStyle = 'rgba(0,0,0,.45)'; ctx.fillRect(ox - 10, oy - 6, G.w * cell + 20, G.h * cell + 22);
    // 地面
    for (let y = 0; y < G.h; y++) for (let x = 0; x < G.w; x++) {
      if (ready(A.floor)) ctx.drawImage(A.floor, ox + x * cell, oy + y * cell, cell, cell);
      if ((x + y) % 2) { ctx.fillStyle = 'rgba(0,40,0,.10)'; ctx.fillRect(ox + x * cell, oy + y * cell, cell, cell); }
    }
    const Z = F.zone || [0, 0, G.w - 1, G.h - 1], PZ = P.zone || Z;
    const [zx0, zy0, zx1, zy1] = Z, [px0, py0, px1, py1] = PZ;
    const crushed = new Set((F.crushed || []).map(([x, y]) => x + ',' + y));
    const warn = (N.next_crush || F.next_crush || []).filter(c => c.turn > F.turn && c.turn - F.turn <= 5);
    // 按行从上往下画，墙、炸弹、人按所在行排前后
    const people = [];
    for (const [i, p] of F.players.entries()) {
      const seat = G.seats[i];
      const q = N.players[i];
      const dying = p.alive && !q.alive && t + 1 < G.frames.length;
      const justDied = !p.alive && p.death_turn === t;
      const recentlyDead = !p.alive && t - p.death_turn <= 3;
      if (!p.alive && !recentlyDead) continue;
      let x = p.x, y = p.y, pose = 'down', flip = false, alpha = 1;
      if (p.alive) {
        const e = ease(k);
        x = p.x + (q.x - p.x) * e; y = p.y + (q.y - p.y) * e;
        const moving = q.x !== p.x || q.y !== p.y;
        const [fx, fy] = moving ? [Math.sign(q.x - p.x), Math.sign(q.y - p.y)] : facing(G, i, t);
        const base = fy < 0 ? 'up' : fy > 0 ? 'down' : 'right';
        flip = fx < 0;
        pose = moving && k > 0.2 && k < 0.8 ? base + '_walk' : base;
        const placed = N.bombs.some(b => b.owner === i && !F.bombs.some(c => c.id === b.id));
        if (placed && k < 0.6) pose = 'place';
        if (over || (opt.winners && opt.winners.includes(i) && t >= G.frames.length - 2)) pose = 'victory';
      } else {
        const age = t - p.death_turn + k;
        pose = age < 0.8 ? 'dizzy' : 'ko';
        alpha = clamp(1.4 - age / 3, 0, 1);
      }
      people.push({ i, seat, x, y, pose, flip, alpha, dying });
    }
    const bombs = F.bombs.map(b => ({ b, y: b.y }));
    for (let y = 0; y < G.h; y++) {
      for (let x = 0; x < G.w; x++) {
        const X = ox + x * cell + cell / 2, Y = oy + (y + 1) * cell, tile = F.grid[y][x];
        const out = x < zx0 || x > zx1 || y < zy0 || y > zy1, wasOut = x < px0 || x > px1 || y < py0 || y > py1;
        if (tile === '@' || out) {
          const fresh = (out && !wasOut && tile !== '@') || (tile === '@' && P.grid[y][x] !== '@');
          const drop = fresh ? Math.max(0, 1 - k * 2.2) : 0;
          sprite(ctx, A.pillar, X, Y - drop * cell * 3, sc);
          if (crushed.has(x + ',' + y)) { ctx.fillStyle = 'rgba(120,20,30,.28)'; ctx.fillRect(X - cell / 2, Y - cell, cell, cell); }
        } else if (tile === '#') sprite(ctx, A.crate, X, Y, sc);
        else if (P.grid[y][x] === '#' && k < 0.8) sprite(ctx, A.crate_break, X, Y, sc, { alpha: 1 - k / 0.8 });
      }
      for (const it of (F.items || []).filter(o => o.y === y)) {
        const bob = Math.sin((tf * 1.5 + it.x) * Math.PI) * 2 * sc;
        sprite(ctx, A[ITEM[it.kind]], ox + it.x * cell + cell / 2, oy + (it.y + 1) * cell - 4 * sc + bob, sc * 0.8);
      }
      for (const { b } of bombs.filter(o => o.y === y)) {
        const pulse = 1 + Math.sin((tf * 2 + b.id) * Math.PI) * 0.06 + (b.fuse <= 1 ? 0.1 : 0);
        const nb = N.bombs.find(q => q.id === b.id), e = ease(k);
        const bx = nb ? b.x + (nb.x - b.x) * e : b.x, byy = nb ? b.y + (nb.y - b.y) * e : b.y;
        const spin = nb && (nb.x !== b.x || nb.y !== b.y) ? Math.sin(tf * 9) * 0.25 : 0;
        sprite(ctx, b.fuse <= 1 ? A.bomb_hot : A.bomb, ox + bx * cell + cell / 2, oy + (byy + 1) * cell - 2 * sc, sc * 0.9 * pulse, { rot: spin });
      }
      for (const m of people.filter(o => Math.round(o.y) === y)) {
        const img = heroFor(m.seat, m.pose, opt.colors && opt.colors[m.i]);
        const bob = m.pose.endsWith('_walk') ? -2 * sc : 0;
        sprite(ctx, img, ox + m.x * cell + cell / 2, oy + (m.y + 1) * cell - 2 * sc + bob, sc * 1.05, { flip: m.flip, alpha: m.alpha });
      }
    }
    warn.forEach((c, j) => {
      const blink = j === 0 ? 0.55 + 0.35 * Math.sin(tf * Math.PI * 4) : 0.35;
      ctx.strokeStyle = `rgba(255,70,60,${blink})`; ctx.lineWidth = Math.max(2, 3 * sc);
      ctx.strokeRect(ox + c.x * cell + 3, oy + c.y * cell + 3, cell - 6, cell - 6);
      if (j === 0) { ctx.fillStyle = `rgba(0,0,0,${0.15 + 0.3 * k})`; ctx.beginPath(); ctx.ellipse(ox + c.x * cell + cell / 2, oy + c.y * cell + cell * 0.6, cell * 0.38 * (0.5 + k * 0.5), cell * 0.18, 0, 0, Math.PI * 2); ctx.fill(); }
    });
    // 火焰：本回合爆炸，先窜出来再熄
    if (k < 0.85) {
      const grow = k < 0.15 ? 0.6 + k / 0.15 * 0.5 : 1.1 - (k - 0.15) * 0.25, a = k < 0.6 ? 1 : 1 - (k - 0.6) / 0.25;
      for (const [x, y, nm, rot] of flamePieces(G, t)) {
        const X = ox + x * cell + cell / 2, Y = oy + y * cell + cell / 2;
        ctx.save(); ctx.globalAlpha = clamp(a, 0, 1); ctx.translate(X, Y); ctx.rotate(rot);
        const img = A[nm], s = sc * grow * (nm === 'fire_c' ? 1.15 : 1);
        if (ready(img)) ctx.drawImage(img, -img.width * s / 2, -img.height * s / 2, img.width * s, img.height * s); ctx.restore();
      }
    }
    // 名牌
    for (const m of people) {
      if (m.alpha < 0.5) continue;
      const X = ox + m.x * cell + cell / 2, Y = oy + m.y * cell - 26 * sc;
      const nm = (opt.names && opt.names[m.i]) || NAMES[m.seat] || m.seat;
      ctx.font = `bold ${Math.round(13 * sc)}px "PingFang SC", sans-serif`; ctx.textAlign = 'center';
      const w = ctx.measureText(nm).width + 14 * sc;
      ctx.fillStyle = 'rgba(10,14,30,.8)'; ctx.fillRect(Math.round(X - w / 2), Math.round(Y - 13 * sc), Math.round(w), Math.round(18 * sc));
      ctx.fillStyle = (opt.colors && opt.colors[m.i]) || COLORS[m.seat] || '#fff'; ctx.fillText(nm, X, Y);
    }
    for (const ev of (G.events || [])) {
      if (ev.type !== 'pickup' || ev.t > t || t + k - ev.t > 1.6) continue;
      const age = t + k - ev.t, X = ox + ev.at[0] * cell + cell / 2, Y = oy + ev.at[1] * cell - 30 * sc - age * 14 * sc;
      ctx.save(); ctx.globalAlpha = clamp(1.6 - age, 0, 1); ctx.font = `900 ${Math.round(15 * sc)}px "PingFang SC", sans-serif`; ctx.textAlign = 'center';
      ctx.lineWidth = 5 * sc; ctx.strokeStyle = '#000'; ctx.strokeText(ITEM_TXT[ev.kind], X, Y); ctx.fillStyle = '#ffe14a'; ctx.fillText(ITEM_TXT[ev.kind], X, Y); ctx.restore();
    }
    hud(ctx, G, t, tf, opt);
  };

  function hud(ctx, G, t, tf, opt) {
    const F = at(G, t);
    ctx.save();
    // 顶部回合牌
    ctx.fillStyle = 'rgba(10,14,30,.85)'; ctx.fillRect(820, 18, 280, 70);
    ctx.font = 'bold 40px "PingFang SC", sans-serif'; ctx.textAlign = 'center'; ctx.fillStyle = '#fff';
    ctx.fillText(`第 ${F.turn} 回合`, 960, 68);
    const P = at(G, t - 1);
    const crushing = F.crushed && F.crushed.length && (P.crushed || []).length === 0;
    if ((F.zone && P.zone && F.zone[0] !== P.zone[0] && tf - t < 0.9) || (crushing && tf - t < 0.9)) {
      ctx.font = '900 64px "PingFang SC", sans-serif'; ctx.lineWidth = 10; ctx.strokeStyle = '#000';
      const msg = F.zone ? '缩圈！' : '开始压墙！';
      ctx.strokeText(msg, 960, 160); ctx.fillStyle = '#ff5a4a'; ctx.fillText(msg, 960, 160);
    }
    // 两侧选手牌
    F.players.forEach((p, i) => {
      const left = i < Math.ceil(G.n / 2), row = left ? i : i - Math.ceil(G.n / 2);
      const X = left ? 40 : 1920 - 40 - 330, Y = 230 + row * 170, seat = G.seats[i];
      ctx.globalAlpha = p.alive ? 1 : 0.55;
      ctx.fillStyle = "rgba(10,14,30,.86)"; ctx.fillRect(X, Y, 330, 150);
      ctx.fillStyle = (opt.colors && opt.colors[i]) || COLORS[seat] || '#fff'; ctx.fillRect(X, Y, 8, 140);
      ctx.imageSmoothingEnabled = false;
      const img = heroFor(seat, p.alive ? 'down' : 'ko', opt.colors && opt.colors[i]);
      if (img) ctx.drawImage(img, X + 22, Y + 20, img.width * 2.2, img.height * 2.2);
      ctx.textAlign = 'left'; ctx.fillStyle = '#fff'; ctx.font = 'bold 38px "PingFang SC", sans-serif';
      ctx.fillText((opt.names && opt.names[i]) || NAMES[seat] || seat, X + 118, Y + 58);
      ctx.font = 'bold 26px "PingFang SC", sans-serif'; ctx.fillStyle = p.alive ? '#9fe7a8' : '#ff8a7a';
      ctx.fillText(p.alive ? `存活 · 击杀 ${p.kills}` : `第 ${p.death_turn} 回合${p.death_cause === 'crush' ? '被墙压' : '出局'}`, X + 118, Y + 104);
      if (p.radius !== undefined && p.alive) {
        const A = window.ART; let ix = X + 118;
        for (const [img, n] of [[A.pu_fire, p.radius], [A.pu_bomb, p.bomb_limit]]) {
          if (ready(img)) ctx.drawImage(img, ix, Y + 112, 22, 22); ctx.font = 'bold 22px "PingFang SC", sans-serif'; ctx.fillStyle = '#fff'; ctx.fillText(String(n), ix + 26, Y + 131); ix += 62;
        }
        if (p.can_kick && ready(A.pu_kick)) ctx.drawImage(A.pu_kick, ix, Y + 112, 22, 22);
      }
      ctx.globalAlpha = 1;
    });
    ctx.restore();
  }
})();
