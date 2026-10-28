(async function () {
  'use strict';
  const $ = id => document.getElementById(id);
  const audio = new window.BPAudio(), input = new window.BPInput();
  let manifest, worker, ready = false, artReady = false, sequence = 0, generation = 0;
  let current = null, lastConfig = null, pausedAt = null;
  const pending = new Map();
  const mode = () => document.querySelector('input[name="mode"]:checked').value;
  const context = $('canvas').getContext('2d');
  function muteLabel() {
    $('mute').textContent = audio.muted ? '声音：关' : '声音：开';
    $('mute').setAttribute('aria-pressed', String(audio.muted));
  }
  $('mute').onclick = () => { audio.toggle(); muteLabel(); };
  muteLabel();

  function event(kind, fields) {
    try {
      // 服务器只记 k、s、i、f、r 五个短字段：k 模式，f 开始/结束，s 对手和节拍或死因，i 名次/回合
      const s = kind === 'start' ? `${(fields.opponents || []).join(',')}@${fields.speed}` : String(fields.death || '');
      const i = kind === 'end' ? `${Array.isArray(fields.place) ? fields.place.join(',') : fields.place}/${fields.turns}` : '';
      const body = JSON.stringify({ e: 'bp', p: '/games/bomb-party/', k: fields.mode, f: kind, s, i,
        w: navigator.webdriver ? 1 : 0 });
      if (navigator.sendBeacon) navigator.sendBeacon('/_e', new Blob([body], { type: 'application/json' }));
      else fetch('/_e', { method: 'POST', body, keepalive: true }).catch(() => {});
    } catch (_) { /* telemetry never blocks play */ }
  }
  function available() {
    $('start').disabled = !ready || !artReady;
    $('start').textContent = ready && artReady ? (mode() === 'play' ? '开场，加入派对 →' : '开场，看 AI 对打 →') : '准备中…';
    if (ready && artReady) $('loading').textContent = '场地准备好了，随时开场。';
  }
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
    $('error').textContent = `这一局没有继续：${error.message || error}。可以重新开场；若仍失败，请刷新页面。`;
    $('start').disabled = !ready || !artReady;
  }
  function rejectRequests(message) {
    for (const job of pending.values()) { clearTimeout(job.timer); job.reject(new Error(message)); }
    pending.clear();
  }
  function bootWorker() {
    ready = false;
    available();
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
        if (data.ok) job.resolve(data.data);
        else job.reject(new Error(data.error));
      }
    };
    worker.onerror = error => {
      ready = false; available(); rejectRequests('Worker 运行失败'); fail(new Error(error.message || 'Worker 运行失败'));
    };
  }
  function rpc(cmd, args) {
    return new Promise((resolve, reject) => {
      const id = ++sequence;
      const timer = setTimeout(() => {
        pending.delete(id);
        reject(new Error('程序长时间没有响应，运行环境已重置'));
        // Native Python calls cannot always be interrupted by sys.settrace.
        bootWorker();
      }, 13000);
      pending.set(id, { resolve, reject, timer });
      worker.postMessage({ id, cmd, args });
    });
  }
  function choices() {
    const count = mode() === 'play' ? 3 : 4;
    const previous = [...$('opponents').querySelectorAll('select')].map(s => s.value);
    $('opponents').replaceChildren();
    $('opponents').classList.toggle('watch', count === 4);
    $('color-label').hidden = count === 4;
    $('random').textContent = count === 3 ? '随机三个' : '随机四个';
    $('opponent-title').textContent = count === 3 ? '挑选三个对手' : '挑选四位选手';
    for (let i = 0; i < count; i++) {
      const label = document.createElement('label');
      label.textContent = count === 3 ? `对手 ${i + 1}` : `选手 ${i + 1}`;
      const select = document.createElement('select');
      for (const bot of manifest.cast) select.add(new Option(bot.name, bot.slug));
      select.value = previous[i] || manifest.cast[i % manifest.cast.length].slug;
      select.onchange = () => select.style.setProperty('--seat-color', manifest.cast.find(c => c.slug === select.value).color);
      select.onchange(); label.append(select); $('opponents').append(label);
    }
    available();
  }
  function config() {
    const selected = [...$('opponents').querySelectorAll('select')].map(s => manifest.cast.find(c => c.slug === s.value));
    const human = mode() === 'play' ? 0 : null;
    const cast = human === 0 ? [{ slug: 'human', name: '你', color: $('color').value }, ...selected] : selected;
    return { mode: mode(), human, speed: Number($('speed').value), seats: cast.map(c => c.slug),
      names: cast.map(c => c.name), colors: cast.map(c => c.color) };
  }
  function askRound(game) {
    if (game.over || game.computing || game.next || current !== game || pausedAt !== null) return;
    game.computing = true;
    // Sample only at the start of a round; never collect stale queued moves.
    const action = game.human === 0 ? input.sample() : 'stay';
    rpc('step', { action }).then(reply => {
      if (current === game) { game.next = reply; game.computing = false; }
    }).catch(error => { if (current === game) fail(error); });
  }
  async function start(settings) {
    if (!ready || !artReady) return;
    audio.unlock(); // Called synchronously from the start/replay click gesture.
    stop();
    const token = generation;
    $('start').disabled = true; $('again').disabled = true;
    $('error').hidden = true; $('result').hidden = true; $('setup').hidden = true; $('game').hidden = false;
    $('controls').hidden = settings.human === null;
    $('game-status').textContent = '选手正在入场…';
    document.body.classList.add('playing');
    try {
      const random = new Uint32Array(1); crypto.getRandomValues(random);
      const reply = await rpc('start', { seats: settings.seats, human: settings.human, seed: random[0] });
      if (token !== generation) return;
      lastConfig = settings;
      const now = performance.now();
      const game = current = { ...settings, G: { w: 13, h: 13, n: 4, seats: settings.seats,
        frames: [reply.frame], events: [] }, due: now + settings.speed, segment: null, next: null,
        computing: false, over: false, finished: false, lastEventTurn: 0, warnings: 0, token };
      game.warnings = reply.broken.filter(Boolean).length;
      $('game-hint').textContent = settings.human === null ? '四个程序同时出招。选好节拍，看看谁能活到最后。' : '方向键 / WASD 移动 · 空格 / J 放弹 · 按住方向连续移动，最后按下的方向优先。';
      $('game-status').textContent = settings.human === null ? 'AI 派对开场！' : '你在左上角，先炸开一条路！';
      event('start', { mode: settings.mode, opponents: settings.seats.filter((_, i) => i !== settings.human), speed: settings.speed });
      askRound(game);
      if (document.hidden) pause(true);
    } catch (error) { if (token === generation) fail(error); }
    finally { $('again').disabled = false; available(); }
  }
  function playEvents(game, turn) {
    if (turn <= game.lastEventTurn) return;
    audio.events(game.G.events.filter(e => e.t === turn));
    game.lastEventTurn = turn;
  }
  function finish(game) {
    if (game.finished) return;
    game.finished = true;
    input.clear();
    document.body.classList.remove('playing');
    $('controls').hidden = true;
    $('pause').disabled = true;
    const last = game.G.frames.at(-1), rows = last.players.map((p, i) => ({ ...p, name: game.names[i], color: game.colors[i], place: game.place[i] }));
    $('scores').replaceChildren();
    rows.sort((a, b) => a.place - b.place).forEach(p => {
      const tr = document.createElement('tr');
      [String(p.place), p.name, String(p.alive ? last.turn : p.death_turn), String(p.kills)].forEach((value, i) => {
        const td = document.createElement('td'); td.textContent = value;
        if (i === 1) td.style.color = p.color;
        tr.append(td);
      });
      $('scores').append(tr);
    });
    const you = game.human === null ? null : last.players[game.human];
    $('result-title').textContent = you ? (game.place[game.human] === 1 ? '你拿下了第一名！' : `这次第 ${game.place[game.human]} 名`) : `${rows.filter(p => p.place === 1).map(p => p.name).join('、')}获胜`;
    const cause = you ? (you.alive ? 'survived' : you.death_cause) : null;
    $('result-detail').textContent = `共 ${last.turn} 回合。${you ? (cause === 'blast' ? '你被爆炸击中，下次记得提前找退路。' : cause === 'crush' ? '你被落墙压中，注意红框预告。' : '你坚持到了最后！') : '同名次表示并列。'}${game.warnings ? ` ${game.warnings} 个程序因出错或过慢，本局后续原地停留。` : ''}`;
    $('game-status').textContent = '派对结束';
    $('result').hidden = false;
    audio.victory();
    event('end', { mode: game.mode, place: game.human === null ? game.place : game.place[game.human], turns: last.turn, death: cause });
    $('again').focus({ preventScroll: true });
  }
  function draw(now) {
    const game = current;
    if (game && !game.finished) {
      const clock = pausedAt === null ? now : pausedAt;
      if (!game.finished && pausedAt === null) {
        if (game.next && clock >= game.due) {
          const reply = game.next; game.next = null;
          game.G.frames.push(reply.frame); game.G.events.push(...reply.events);
          game.segment = { from: reply.frame.turn - 1, start: clock };
          game.due = clock + game.speed;
          game.over = reply.over; game.place = reply.place;
          game.warnings = reply.broken.filter(Boolean).length;
          playEvents(game, reply.frame.turn - 1);
          const human = game.human === null ? null : reply.frame.players[game.human];
          $('game-status').textContent = human && !human.alive ? '你已出局，看看谁能获胜。' : `第 ${reply.frame.turn} 回合${game.warnings ? ' · 有程序暂停出招' : ''}`;
          askRound(game);
        }
        if (game.over && !game.finalAt && clock >= game.due) {
          game.finalAt = clock;
          playEvents(game, game.G.frames.at(-1).turn);
        }
      }
      const segment = game.segment;
      const lastTurn = game.G.frames.length - 1;
      let tf = segment ? segment.from + Math.min(1, Math.max(0, (clock - segment.start) / game.speed)) : 0;
      // The offline renderer treats its last available frame as the ending.
      // Keep a duplicate initial frame and stay just below the live frontier.
      const renderGame = lastTurn ? game.G : { ...game.G, frames: [game.G.frames[0], game.G.frames[0]] };
      if (game.finalAt) tf = lastTurn + Math.min(0.84, Math.max(0, (clock - game.finalAt) / game.speed));
      else if (lastTurn) tf = Math.min(tf, lastTurn - 0.00001);
      if (game.lastDrawTf !== tf || game.lastDrawCount !== renderGame.frames.length) {
        window.drawBomber(context, renderGame, tf, { names: game.names, colors: game.colors,
          winners: game.over ? game.place.map((p, i) => p === 1 ? i : -1).filter(i => i >= 0) : [] });
        game.lastDrawTf = tf; game.lastDrawCount = renderGame.frames.length;
      }
      if (game.finalAt && clock - game.finalAt >= Math.max(550, game.speed) && pausedAt === null) finish(game);
    }
    requestAnimationFrame(draw);
  }
  function pause(value = pausedAt === null) {
    if (!current || current.finished) return;
    if (value && pausedAt === null) { pausedAt = performance.now(); input.clear(); }
    else if (!value && pausedAt !== null) {
      const delta = performance.now() - pausedAt;
      current.due += delta;
      if (current.segment) current.segment.start += delta;
      if (current.finalAt) current.finalAt += delta;
      pausedAt = null; audio.unlock(); askRound(current);
    }
    $('pause-overlay').hidden = pausedAt === null;
    $('pause').textContent = pausedAt === null ? '暂停' : '继续';
  }
  function setup() {
    stop();
    $('game').hidden = true; $('setup').hidden = false; $('result').hidden = true;
    $('pause').disabled = false; available();
    $('start').focus({ preventScroll: true });
  }
  input.mount($('controls'), () => current && !current.finished && current.human === 0 && pausedAt === null);
  $('settings').onsubmit = event => { event.preventDefault(); $('pause').disabled = false; start(config()); };
  $('again').onclick = () => { $('pause').disabled = false; start(lastConfig); };
  $('leave').onclick = setup; $('change').onclick = setup;
  $('pause').onclick = () => pause();
  document.addEventListener('visibilitychange', () => { if (document.hidden) pause(true); });
  window.addEventListener('blur', () => pause(true));
  ['touchmove', 'gesturestart', 'dblclick', 'contextmenu'].forEach(type => document.addEventListener(type, e => {
    if (document.body.classList.contains('playing')) e.preventDefault();
  }, { passive: false }));
  requestAnimationFrame(draw);
  try {
    const response = await fetch('manifest.json', { cache: 'no-store' });
    if (!response.ok) throw new Error('找不到 manifest.json，请先运行 build.py');
    manifest = await response.json();
    if (!manifest.cast.length) throw new Error('没有可用的 AI 陪练');
    choices();
    document.querySelectorAll('input[name="mode"]').forEach(radio => radio.onchange = choices);
    $('random').onclick = () => {
      const cast = [...manifest.cast];
      for (let i = cast.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1)); [cast[i], cast[j]] = [cast[j], cast[i]];
      }
      $('opponents').querySelectorAll('select').forEach((select, i) => { select.value = cast[i % cast.length].slug; select.onchange(); });
    };
    if (Object.values(manifest.links).every(link => !link.startsWith('#'))) document.querySelector('.placeholder-note').hidden = true;
    bootWorker();
    const atlasResponse = await fetch(`atlas.json?v=${manifest.version}`);
    if (!atlasResponse.ok) throw new Error('场地精灵加载失败');
    const atlas = await atlasResponse.json();
    window.ART = {};
    await Promise.all(Object.entries(atlas).map(async ([key, value]) => {
      const image = new Image(); image.src = value.src; await image.decode(); window.ART[key] = image;
    }));
    const stage = new Image(); stage.src = `stage.jpg?v=${manifest.version}`; await stage.decode(); window.STAGE = stage;
    artReady = true; available();
  } catch (error) { fail(error); }
})();
