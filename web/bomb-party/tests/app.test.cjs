// A deterministic DOM/Worker simulation in Node. No browser is launched.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const Input = require('../input.js');
let now = 0, nextFrame, id = 0;
const timers = new Map(), handlers = new Map(), beacons = [], calls = [], draws = [];
class Element {
  constructor(tag = 'div') {
    this.tag = tag; this.children = []; this.hidden = false; this.disabled = false;
    this.value = ''; this.dataset = {}; this.attributes = {};
    this.style = { setProperty() {} }; this.classes = new Set();
    this.classList = { add: c => this.classes.add(c), remove: c => this.classes.delete(c),
      contains: c => this.classes.has(c), toggle: (c, enabled) => enabled ? this.classes.add(c) : this.classes.delete(c) };
  }
  add(option) { this.children.push(option); if (!this.value) this.value = option.value; }
  append(child) { this.children.push(child); }
  replaceChildren(...children) { this.children = children; }
  querySelectorAll(selector) {
    return this.children.flatMap(child => [
      ...(selector === 'select' && child.tag === 'select' || selector === '[data-action]' && child.dataset.action ? [child] : []),
      ...(child.querySelectorAll ? child.querySelectorAll(selector) : [])
    ]);
  }
  setAttribute(key, value) { this.attributes[key] = value; }
  addEventListener() {}
  focus() {}
  getContext() { return {}; }
}
const elements = new Map();
const get = key => { if (!elements.has(key)) elements.set(key, new Element()); return elements.get(key); };
get('color').value = '#1FC77E'; get('speed').value = '220';
for (const action of ['up', 'left', 'right', 'down', 'bomb']) {
  const button = new Element('button'); button.dataset.action = action; get('controls').append(button);
}
const modes = [{ value: 'play', checked: true }, { value: 'watch', checked: false }];
const body = new Element('body');
const document = { body, hidden: false, getElementById: get,
  createElement: tag => new Element(tag),
  querySelector: selector => selector.includes('checked') ? modes.find(m => m.checked) : get('placeholder'),
  querySelectorAll: () => modes,
  addEventListener: (type, fn) => handlers.set('document:' + type, fn)
};
const manifest = { version: 'test', links: { video: '#video', source: '#source' }, cast: [
  { slug: 'baseline', name: '稳健', color: '#2FD3E6' }, { slug: 'aggressive', name: '激进', color: '#FF4B4B' },
  { slug: 'farmer', name: '发育', color: '#FFDD3C' }, { slug: 'kicker', name: '踢弹', color: '#A57BFF' }
] };
let turn = 0, frozen = false;
const frame = () => ({ turn, players: Array.from({ length: 4 }, (_, i) => ({ id: i,
  alive: turn < 2 || i === 1, death_turn: turn < 2 || i === 1 ? 0 : 2,
  kills: i === 1 ? 2 : 0, death_cause: i === 0 ? 'blast' : 'crush' })) });
class Worker {
  constructor() { queueMicrotask(() => this.onmessage({ data: { type: 'ready' } })); }
  terminate() { this.dead = true; }
  postMessage({ id, cmd, args }) {
    calls.push({ cmd, args });
    if (cmd === 'start') turn = 0;
    if (cmd === 'step') { if (frozen) return; turn++; }
    const data = { frame: frame(), over: turn === 2, place: turn === 2 ? [2, 1, 3, 3] : null,
      events: turn ? [{ t: turn, type: turn === 1 ? 'bomb' : 'explode' }] : [], broken: [false, false, false, false] };
    queueMicrotask(() => { if (!this.dead) this.onmessage({ data: { type: 'reply', id, ok: true, data } }); });
  }
}
const sound = [];
class Audio {
  unlock() { sound.push('unlock'); }
  events(events) { sound.push(...events.map(e => e.type)); }
  victory() { sound.push('victory'); }
  toggle() { this.muted = !this.muted; }
}
const window = { BPInput: Input, BPAudio: Audio, addEventListener: (type, fn) => handlers.set('window:' + type, fn),
  drawBomber: (_, game, tf, opt) => draws.push({ frames: game.frames.length, tf, opt }) };
// Input.mount uses the host window; it gets exactly the same event registry.
global.window = window;
const sandbox = { window, document, Worker, Option: function (name, value) { return { name, value }; },
  performance: { now: () => now }, crypto: { getRandomValues: values => { values[0] = 123; } },
  navigator: { webdriver: true, sendBeacon: (url, blob) => { beacons.push({ url, blob }); return true; } }, Blob,
  Image: class { decode() { return Promise.resolve(); } },
  fetch: async url => ({ ok: true, json: async () => url.startsWith('manifest') ? manifest : {} }),
  requestAnimationFrame: fn => { nextFrame = fn; },
  setTimeout: fn => { const key = ++id; timers.set(key, fn); return key; },
  clearTimeout: key => timers.delete(key)
};
const flush = () => new Promise(resolve => setImmediate(resolve));
const tick = async time => { now = time; nextFrame(now); await flush(); };
const key = (type, code) => handlers.get('window:' + type)({ code, preventDefault() {} });

(async () => {
  vm.runInNewContext(fs.readFileSync(require.resolve('../app.js'), 'utf8'), sandbox);
  await flush();
  assert.equal(get('start').disabled, false, get('error').textContent || get('loading').textContent);
  assert.equal(get('opponents').querySelectorAll('select').length, 3);
  get('settings').onsubmit({ preventDefault() {} }); await flush();
  assert(body.classList.contains('playing'));
  assert.equal(calls.filter(c => c.cmd === 'step').length, 1);
  key('keydown', 'KeyW');
  await tick(219);
  assert.equal(draws.at(-1).frames, 2, 'duplicate frame keeps initial scene out of victory pose');
  await tick(220);
  assert.equal(calls.filter(c => c.cmd === 'step').at(-1).args.action, 'up');
  assert.equal(draws.at(-1).tf, 0, 'one-turn-delayed playback');
  assert(!sound.includes('bomb'), 'sound waits for the visible frame');
  now = 300; get('pause').onclick();
  await tick(500);
  assert.equal(calls.filter(c => c.cmd === 'step').length, 2, 'pause never queues more rounds');
  now = 600; get('pause').onclick();
  await tick(740);
  assert.equal(draws.at(-1).tf, 1);
  assert(sound.includes('bomb'));
  await tick(960); await tick(1511);
  assert.equal(get('result').hidden, false);
  assert.equal(get('result-title').textContent, '这次第 2 名');
  assert.equal(get('scores').children.length, 4);
  assert(sound.includes('explode') && sound.includes('victory'));
  const events = await Promise.all(beacons.map(async b => ({ url: b.url, ...JSON.parse(await b.blob.text()) })));
  assert.deepEqual(events.map(e => e.f), ['start', 'end']);
  assert.equal(events[0].e, 'bp'); assert.equal(events[0].p, '/games/bomb-party/');
  // serve.py 只记 k、s、i、f、r：开局 s=对手@节拍，结束 s=死因、i=名次/回合
  assert.equal(events[0].k, 'play'); assert.equal(events[0].w, 1); assert.ok(events[0].s.endsWith('@220'));
  assert.equal(events[1].s, 'blast'); assert.equal(events[1].i, '2/2');

  // Replay uses the same seats but creates a fresh engine match.
  get('again').onclick(); await flush();
  assert.equal(calls.filter(c => c.cmd === 'start').length, 2);
  get('leave').onclick();
  modes[0].checked = false; modes[1].checked = true; modes[1].onchange();
  assert.equal(get('opponents').querySelectorAll('select').length, 4);
  get('random').onclick();
  assert.equal(new Set(get('opponents').querySelectorAll('select').map(s => s.value)).size, 4);
  get('settings').onsubmit({ preventDefault() {} }); await flush();
  assert.equal(calls.filter(c => c.cmd === 'start').at(-1).args.human, null);
  assert.equal(get('controls').hidden, true);
  get('leave').onclick();

  // A slow result holds playback and does not accumulate decisions or inputs.
  frozen = true;
  get('settings').onsubmit({ preventDefault() {} }); await flush();
  const before = calls.filter(c => c.cmd === 'step').length;
  await tick(5000); await tick(6000);
  assert.equal(calls.filter(c => c.cmd === 'step').length, before);
  assert(draws.at(-1).tf < 1);
  assert.equal(timers.size, 1);
  [...timers.values()][0](); await flush();
  assert.equal(get('setup').hidden, false);
  assert.equal(get('error').hidden, false);
  assert.equal(get('start').disabled, false, 'watchdog boots a new local Worker');
  console.log('App: lobby, human/watch, delayed playback, input sampling, pause, replay, result, telemetry and Worker watchdog passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
