(async function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const FPS = 30, FRAME_MS = 1000 / FPS, MAX_BATCH = 6, END_HOLD_MS = 2200;
  const CHARS = [
    { key: 'lie', name: '阿烈', style: '均衡', line: '烈波、升龙拳，什么距离都能打。', col: '#ff6a3a' },
    { key: 'tie', name: '铁山', style: '投技', line: '血最厚，贴身一抓就是大半管。', col: '#4fd17a' },
    { key: 'yan', name: '飞燕', style: '速度', line: '走得最快，飞膝一下冲到脸上。', col: '#6cd6ff' },
    { key: 'rei', name: '雷娜', style: '远程', line: '雷球压场，超必杀光束横扫全屏。', col: '#c88bff' },
  ];
  const audio = new window.BBAudio(), input = new window.BBInput();
  let manifest, worker, ready = false, artReady = false, sequence = 0, generation = 0;
  let current = null, lastConfig = null, pausedAt = null;
  let pick = 'lie', seatA = null, seatB = null;
  const pending = new Map();
  const mode = () => document.querySelector('input[name="mode"]:checked').value;
  const context = $('canvas').getContext('2d');
  const bot = slug => manifest.cast.find(c => c.slug === slug);

  function muteLabel() {
    $('mute').textContent = audio.muted ? '声音：关' : '声音：开';
    $('mute').setAttribute('aria-pressed', String(audio.muted));
  }
  $('mute').onclick = () => { audio.toggle(); muteLabel(); };
  muteLabel();

  // ---------- 选角画面 ----------
  const ok = im => im && im.complete && im.naturalWidth > 0;
  function sprite(char, pose) { const s = window.SPR && window.SPR[char] && window.SPR[char][pose]; return s && ok(s.img) ? s : null; }
  const silhouettes = new Map();
  function silhouette(sp, col) {
    const key = sp.img.src.slice(-40) + col;
    if (!silhouettes.has(key)) {
      const c = document.createElement('canvas'); c.width = sp.img.naturalWidth; c.height = sp.img.naturalHeight;
      const g = c.getContext('2d'); g.drawImage(sp.img, 0, 0); g.globalCompositeOperation = 'source-in';
      g.fillStyle = col; g.fillRect(0, 0, c.width, c.height); silhouettes.set(key, c);
    }
    return silhouettes.get(key);
  }
  function drawSprite(g, sp, x, groundY, scale, face, image) {
    g.save(); g.translate(Math.round(x), 0); g.scale(face, 1);
    g.drawImage(image || sp.img, -Math.round(sp.ax * scale), Math.round(groundY - sp.h * scale), Math.round(sp.w * scale), Math.round(sp.h * scale));
    g.restore();
  }
  function portrait(canvas, char, pose) {
    const g = canvas.getContext('2d'), sp = sprite(char, pose) || sprite(char, 'stance');
    g.clearRect(0, 0, canvas.width, canvas.height);
    if (!sp) return;
    g.imageSmoothingEnabled = false;
    const scale = Math.floor(Math.min((canvas.height - 8) / sp.h, (canvas.width - 8) / sp.w) * 2) / 2;
    g.save(); g.translate(canvas.width / 2 - (sp.w / 2 - sp.ax) * scale, 0);
    drawSprite(g, sp, 0, canvas.height - 4, scale, 1);
    g.restore();
  }
  function heroFrame(now) {
    if (!$('setup').hidden && artReady) {
      const cv = $('preview'), g = cv.getContext('2d'), K = 2.5, GY = 178 * K;
      g.imageSmoothingEnabled = true;
      if (ok(window.STAGE)) g.drawImage(window.STAGE, 0, 0, cv.width, cv.height);
      g.fillStyle = 'rgba(16,8,30,.35)'; g.fillRect(0, 0, cv.width, cv.height);
      g.imageSmoothingEnabled = false;
      const bob = Math.floor(now / 400) % 2, watching = mode() === 'watch';
      const sides = [[196 * K, 1, watching ? null : pick, watching ? seatA : null], [300 * K, -1, null, watching ? seatB : seatA]];
      for (const [x, face, char, slug] of sides) {
        g.fillStyle = 'rgba(0,0,0,.4)'; g.fillRect(x - 40, GY - 3, 80, 8);
        if (char) {
          const sp = sprite(char, 'stance'); if (sp) drawSprite(g, sp, x, GY + bob, K, face);
        } else {
          // AI 还没选角：画一个带它颜色的影子和问号
          const shadowChar = ['lie', 'tie', 'yan', 'rei'][(slug || '').length % 4];
          const sp = sprite(shadowChar, 'stance');
          const col = (slug && bot(slug)) ? bot(slug).color : '#888888';
          if (sp) {
            g.save(); g.globalAlpha = 0.9; drawSprite(g, sp, x, GY + bob, K, face, silhouette(sp, '#120a20')); g.restore();
            g.save(); g.globalAlpha = 0.55; drawSprite(g, sp, x + face * 3, GY + bob, K, face, silhouette(sp, col)); g.restore();
            g.save(); g.globalAlpha = 1; drawSprite(g, sp, x, GY + bob, K, face, silhouette(sp, '#1a1030')); g.restore();
          }
          g.font = '900 86px "PingFang SC", sans-serif'; g.textAlign = 'center'; g.lineWidth = 10; g.strokeStyle = '#000';
          g.strokeText('?', x, GY - 80); g.fillStyle = col; g.fillText('?', x, GY - 80);
        }
      }
    }
    requestAnimationFrame(heroFrame);
  }
  function roster() {
    $('roster').replaceChildren();
    for (const c of CHARS) {
      const label = document.createElement('label');
      label.className = 'fighter'; label.style.setProperty('--c', c.col);
      const radio = document.createElement('input'); radio.type = 'radio'; radio.name = 'char'; radio.value = c.key; radio.checked = c.key === pick;
      const art = document.createElement('canvas'); art.width = 120; art.height = 150; art.setAttribute('aria-hidden', 'true');
      const text = document.createElement('span');
      const name = document.createElement('b'); name.textContent = c.name;
      const tag = document.createElement('em'); tag.textContent = c.style;
      const line = document.createElement('small'); line.textContent = c.line;
      text.append(name, tag, line);
      label.append(radio, art, text);
      radio.onchange = () => { pick = c.key; paintRoster(); audio.unlock(); audio.blip(); };
      $('roster').append(label);
    }
    paintRoster();
  }
  function paintRoster() {
    document.querySelectorAll('#roster .fighter').forEach(label => {
      const key = label.querySelector('input').value;
      portrait(label.querySelector('canvas'), key, key === pick ? 'win' : 'stance');
    });
  }
  function chips(container, selected, onpick) {
    container.replaceChildren();
    for (const c of manifest.cast) {
      const label = document.createElement('label'); label.className = 'chip'; label.dataset.slug = c.slug;
      const radio = document.createElement('input'); radio.type = 'radio'; radio.name = container.id; radio.value = c.slug; radio.checked = c.slug === selected;
      const dot = document.createElement('i'); const name = document.createElement('span'); name.textContent = c.name;
      label.append(radio, dot, name);
      radio.onchange = () => onpick(c.slug);
      container.append(label);
    }
  }
  function choices() {
    const watching = mode() === 'watch';
    $('pick-block').hidden = watching;
    $('seat-b-wrap').hidden = !watching;
    $('opp-step').textContent = watching ? '1' : '2';
    $('opp-title').textContent = watching ? '挑两家 AI' : '挑一家 AI 当对手';
    $('seat-a').setAttribute('aria-label', watching ? '左边的 AI' : '对手');
    $('seat-a').classList.toggle('left-seat', watching);
    if (watching && seatB === seatA && manifest.cast.length > 1) seatB = manifest.cast.find(c => c.slug !== seatA).slug;
    chips($('seat-a'), seatA, slug => { seatA = slug; });
    chips($('seat-b'), seatB, slug => { seatB = slug; });
    available();
  }
  function available() {
    $('start').disabled = !ready || !artReady;
    $('start').textContent = ready && artReady ? (mode() === 'play' ? '开打 →' : '开场，看 AI 对打 →') : '准备中…';
    if (ready && artReady) $('loading').textContent = '准备好了。';
  }

  // ---------- Worker ----------
  function stop() {
    generation++;
    current = null; pausedAt = null; input.clear();
    document.body.classList.remove('playing');
    $('pause-overlay').hidden = true;
    $('pause').textContent = '暂停';
  }
  function fail(error) {
    stop();
    $('game').hidden = true; $('setup').hidden = false;
    $('error').hidden = false;
    $('error').textContent = `这一局没打完：${error.message || error}。可以重新开场；还不行就刷新页面。`;
    available();
  }
  function rejectRequests(message) {
    for (const job of pending.values()) { clearTimeout(job.timer); job.reject(new Error(message)); }
    pending.clear();
  }
  function bootWorker() {
    ready = false; available();
    if (worker) worker.terminate();
    rejectRequests('运行环境已重置');
    worker = new Worker(`worker.js?v=${manifest.version}`);
    worker.onmessage = ({ data }) => {
      if (data.type === 'progress') $('loading').textContent = data.stage;
      else if (data.type === 'ready') { ready = true; available(); }
      else if (data.type === 'fatal') { ready = false; available(); fail(new Error(data.message)); }
      else if (data.type === 'reply') {
        const job = pending.get(data.id);
        if (!job) return;
        clearTimeout(job.timer); pending.delete(data.id);
        if (data.ok) job.resolve(Object.assign(data.data, { workerMs: data.ms }));
        else job.reject(new Error(data.error));
      }
    };
    worker.onerror = error => { ready = false; available(); rejectRequests('Worker 运行失败'); fail(new Error(error.message || 'Worker 运行失败')); };
  }
  function rpc(cmd, args) {
    return new Promise((resolve, reject) => {
      const id = ++sequence;
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error('AI 程序长时间没有回应，运行环境已重置'));
        bootWorker(); // 原生调用里卡住的程序 sys.settrace 打断不了，只能整个换掉
      }, 8000);
      pending.set(id, { resolve, reject, timer });
      worker.postMessage({ id, cmd, args });
    });
  }

  // ---------- 一局 ----------
  function config() {
    const watching = mode() === 'watch';
    const a = bot(seatA), b = bot(seatB);
    const seats = watching ? [a, b] : [{ slug: 'human', name: '你', color: '#ffd23a' }, a];
    return { mode: mode(), human: watching ? null : 0, pick, seats: seats.map(s => s.slug), names: seats.map(s => s.name), colors: seats.map(s => s.color) };
  }
  async function start(settings) {
    if (!ready || !artReady) return;
    audio.unlock(); // 必须在点击里同步调用
    stop();
    const token = generation;
    $('start').disabled = true; $('again').disabled = true;
    $('error').hidden = true; $('result').hidden = true; $('setup').hidden = true; $('game').hidden = false;
    $('controls').hidden = settings.human === null;
    $('game-hint').hidden = settings.human === null;
    $('pause').disabled = false;
    $('game-status').textContent = '选手入场…';
    document.body.classList.add('playing');
    window.scrollTo(0, 0);
    try {
      const random = new Uint32Array(1); crypto.getRandomValues(random);
      const reply = await rpc('start', { seats: settings.seats, human: settings.human, pick: settings.pick, seed: random[0] });
      if (token !== generation) return;
      lastConfig = settings;
      current = { ...settings, R: { frames: [reply.frame], seats: settings.names }, t0: performance.now(), shown: -1,
        inflight: false, over: false, result: null, endAt: null, finished: false, token, broken: reply.broken,
        warned: [false, false], seed: reply.seed, workerMs: [], frameMs: [] };
      current.broken.forEach((b, i) => { if (b) current.warned[i] = true; });
      if (reply.broken.some(Boolean)) $('game-status').textContent = `${settings.names[reply.broken.indexOf(true)]} 的程序没能加载，这局它会站着不动。`;
      if (document.hidden) pause(true);
    } catch (error) { if (token === generation) fail(error); }
    finally { $('again').disabled = false; available(); }
  }
  function request(game, n) {
    game.inflight = true;
    const first = game.human === 0 ? input.sample() : {};
    const inputs = [first];
    for (let k = 1; k < n; k++) inputs.push(game.human === 0 ? { h: first.h, v: first.v } : {});
    const sent = performance.now();
    rpc('step', { inputs }).then(reply => {
      if (current !== game) return;
      game.inflight = false;
      game.R.frames.push(...reply.frames);
      game.workerMs.push(reply.workerMs / Math.max(1, reply.frames.length));
      game.frameMs.push((performance.now() - sent) / Math.max(1, reply.frames.length));
      if (game.workerMs.length > 300) { game.workerMs.shift(); game.frameMs.shift(); }
      reply.broken.forEach((b, i) => {
        if (b && !game.warned[i]) { game.warned[i] = true; $('game-status').textContent = `${game.names[i]} 的程序出错或太慢，这局后面它站着不动。`; }
      });
      if (reply.over) { game.over = true; game.result = reply.result; }
    }).catch(error => { if (current === game) fail(error); });
  }
  function status(game, fr) {
    if (!fr.f.length) return;
    const [a, b] = game.names;
    for (const e of fr.ev) {
      if (e.type === 'fight') $('game-status').textContent = `第 ${e.round} 回合 · ${a} ${fr.wins[0]} : ${fr.wins[1]} ${b}`;
      if (e.type === 'pick' && e.id !== game.human) {
        const c = CHARS.find(x => x.key === e.char);
        $('game-status').textContent = `${game.names[e.id]} 选了${c ? c.name : e.char}${e.drawn ? '（随机）' : ''}`;
      }
      if (e.type === 'round') {
        const who = e.win.length ? game.names[e.win[0]] : null;
        $('game-status').textContent = who ? `${who} 拿下第 ${e.round} 回合` : `第 ${e.round} 回合打平`;
      }
    }
  }
  function tick(now) {
    const game = current;
    if (game && !game.finished && pausedAt === null) {
      const have = game.R.frames.length - 1;
      let target = Math.floor((now - game.t0) / FRAME_MS);
      // 算得慢就让整场放慢，不跳帧：时钟最多领先已算好的帧 2 帧
      if (target > have + 2 && !game.over) { game.t0 += (target - have - 2) * FRAME_MS; target = have + 2; }
      // 人在打：只提前算 1 帧，输入延迟最小；看 AI 打：提前算 10 帧，吸收程序偶尔一帧算得慢
      const lead = game.human === null ? 10 : 1;
      if (!game.inflight && !game.over && have < target + lead) request(game, Math.min(MAX_BATCH, target + lead - have));
      const show = Math.min(have, Math.max(0, target));
      if (show !== game.shown) {
        for (let k = game.shown + 1; k <= show; k++) {
          const fr = game.R.frames[k];
          if (fr.ev && fr.ev.length) { audio.events(fr.ev); status(game, fr); }
        }
        game.shown = show;
        window.drawFight(context, game.R, show, { names: game.names });
      }
      if (game.over && show === have) {
        if (game.endAt === null) game.endAt = now;
        else if (now - game.endAt > END_HOLD_MS) finish(game);
      }
    }
    requestAnimationFrame(tick);
  }
  function finish(game) {
    if (game.finished) return;
    game.finished = true;
    input.clear();
    document.body.classList.remove('playing');
    $('controls').hidden = true;
    $('pause').disabled = true;
    const r = game.result, [a, b] = game.names;
    const charName = k => (CHARS.find(c => c.key === k) || { name: k }).name;
    const winner = r.place[0] === r.place[1] ? -1 : (r.place[0] === 1 ? 0 : 1);
    if (game.human === 0) {
      $('result-eyebrow').textContent = winner === 0 ? '漂亮' : (winner === 1 ? '再来一次？' : '势均力敌');
      $('result-title').textContent = winner === 0 ? `你赢了 ${b}！` : (winner === 1 ? `输给了 ${b}` : '平局');
    } else {
      $('result-eyebrow').textContent = '比赛结束';
      $('result-title').textContent = winner >= 0 ? `${game.names[winner]} 赢了` : '平局';
    }
    $('result-title').dataset.win = String(winner === 0 && game.human === 0);
    $('result-score').textContent = `${a}（${charName(r.chars[0])}） ${r.wins[0]} : ${r.wins[1]} ${b}（${charName(r.chars[1])}）`;
    $('col-a').textContent = a; $('col-b').textContent = b;
    const rows = [['造成伤害', 'dmg'], ['命中', 'hits'], ['最长连击', 'max_combo'], ['投', 'throws'], ['超必杀', 'supers']];
    $('stats').replaceChildren(...rows.map(([label, key]) => {
      const tr = document.createElement('tr');
      for (const value of [label, r.play[0][key] ?? 0, r.play[1][key] ?? 0]) { const td = document.createElement('td'); td.textContent = String(value); tr.append(td); }
      return tr;
    }));
    const secs = Math.round(r.turns / FPS);
    const faults = game.warned.map((w, i) => w && i !== game.human ? game.names[i] : null).filter(Boolean);
    $('result-detail').textContent = `打了 ${r.rounds} 回合，${secs >= 60 ? `${Math.floor(secs / 60)} 分 ` : ''}${secs % 60} 秒。` + (faults.length ? `${faults.join('、')} 的程序中途出错停了手。` : '');
    $('result').hidden = false;
    $('game-status').textContent = '比赛结束';
    if (winner === 0 || game.human === null) audio.victory();
    $('again').focus({ preventScroll: true });
  }
  function pause(value = pausedAt === null) {
    if (!current || current.finished) return;
    if (value && pausedAt === null) { pausedAt = performance.now(); input.clear(); }
    else if (!value && pausedAt !== null) {
      const delta = performance.now() - pausedAt;
      current.t0 += delta;
      if (current.endAt !== null) current.endAt += delta;
      pausedAt = null; audio.unlock();
    }
    $('pause-overlay').hidden = pausedAt === null;
    $('pause').textContent = pausedAt === null ? '暂停' : '继续';
  }
  function setup() {
    stop();
    $('game').hidden = true; $('setup').hidden = false; $('result').hidden = true;
    available();
    $('start').focus({ preventScroll: true });
  }
  input.mount($('controls'), () => current && !current.finished && current.human === 0 && pausedAt === null);
  $('settings').onsubmit = event => { event.preventDefault(); start(config()); };
  $('again').onclick = () => start(lastConfig);
  $('leave').onclick = setup; $('change').onclick = setup;
  $('pause').onclick = () => pause(); $('resume').onclick = () => pause(false);
  window.addEventListener('keydown', event => {
    if (event.code === 'Escape' && current && !current.finished) { event.preventDefault(); pause(); }
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) pause(true); });
  window.addEventListener('blur', () => pause(true));
  ['touchmove', 'gesturestart', 'dblclick', 'contextmenu'].forEach(type => document.addEventListener(type, e => {
    if (document.body.classList.contains('playing')) e.preventDefault();
  }, { passive: false }));
  window.__brawl = { get game() { return current; }, pause, start: () => start(config()) }; // 给本地验收脚本读帧耗时
  requestAnimationFrame(tick);
  requestAnimationFrame(heroFrame);
  try {
    const response = await fetch('manifest.json', { cache: 'no-store' });
    if (!response.ok) throw new Error('找不到 manifest.json，请先运行 build.py');
    manifest = await response.json();
    if (!manifest.cast.length) throw new Error('没有可用的 AI');
    seatA = manifest.cast[0].slug;
    seatB = (manifest.cast[1] || manifest.cast[0]).slug;
    document.querySelectorAll('input[name="mode"]').forEach(radio => radio.onchange = choices);
    choices();
    $('random').onclick = () => {
      const cast = [...manifest.cast].sort(() => Math.random() - 0.5);
      seatA = cast[0].slug; seatB = (cast[1] || cast[0]).slug;
      if (mode() === 'play') pick = CHARS[Math.floor(Math.random() * 4)].key;
      roster(); choices();
    };
    bootWorker();
    await window.__boardReady;
    if (!window.SPR || !ok(window.STAGE)) throw new Error('角色图加载失败');
    artReady = true; roster(); available();
  } catch (error) { fail(error); }
})();
