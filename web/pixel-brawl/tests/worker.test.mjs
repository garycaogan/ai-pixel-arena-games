// 用本地 Pyodide 真跑 worker.js（只模拟 Worker 的收发），打完一场人对 AI 和一场 AI 对 AI，并和引擎重放逐帧比对。
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(process.argv[2] || path.join(here, '../dist'));
const manifest = JSON.parse(fs.readFileSync(path.join(out, 'manifest.json'), 'utf8'));
const runtime = `pyodide-${manifest.pyodide}`;
globalThis.fetch = () => { throw new Error('Network is forbidden'); };
const require = createRequire(import.meta.url);
const { loadPyodide } = require(path.join(out, runtime, 'pyodide.js'));
let py, ready, rejectReady;
const boot = new Promise((resolve, reject) => { ready = resolve; rejectReady = reject; });
const messages = [], fetched = [];
const sandbox = { URL, performance, self: { location: pathToFileURL(path.join(out, 'worker.js')).href + '?v=' + manifest.version },
  importScripts: name => assert.equal(name, `${runtime}/pyodide.js`),
  loadPyodide: async options => { options.indexURL = fileURLToPath(options.indexURL); py = await loadPyodide(options); return py; },
  fetch: async name => {
    fetched.push(name);
    assert(!name.includes('://'), 'worker assets must use relative paths');
    const data = fs.readFileSync(path.join(out, name.split('?')[0]), 'utf8');
    return { ok: true, text: async () => data, json: async () => JSON.parse(data) };
  },
  postMessage: value => { messages.push(value); if (value.type === 'ready') ready(); if (value.type === 'fatal') rejectReady(new Error(value.message)); }
};
vm.runInNewContext(fs.readFileSync(path.join(out, 'worker.js'), 'utf8'), sandbox);
await boot;
assert.equal(fetched.length, manifest.files.length + 1);
let id = 0;
async function rpc(cmd, args) {
  await sandbox.onmessage({ data: { id: ++id, cmd, args } });
  const reply = messages.at(-1);
  assert.equal(reply.id, id); assert.equal(reply.ok, true, reply.error);
  return reply.data;
}
const slugs = manifest.cast.map(c => c.slug);
const check = seed => py.runPython(`
import driver, engine
t = driver._table
g = engine.replay(2, ${seed}, t.rows)
g.frame() == t.g.frame() and g.events == t.g.events
`);
// 人对名单第一家：键位按帧循环
let reply = await rpc('start', { seats: ['human', slugs[0]], human: 0, seed: 43, pick: 'yan' });
let k = 0, frames = 1;
const keys = ['p', 'h', 'k', 's', 't', 'z', 'a', 'x', 'dash+'];
while (!reply.over) {
  const inputs = Array.from({ length: 3 }, (_, j) => ({ h: [1, 1, -1, 0][(k >> 4) % 4], v: [0, 0, -1, 1][(k >> 5) % 4], press: j === 0 && k % 4 === 0 ? [keys[k % keys.length]] : [] }));
  reply = await rpc('step', { inputs }); frames += reply.frames.length; k++;
}
assert.equal(check(43), true);
assert.equal(reply.result.chars[0], 'yan');
assert(!reply.broken[1]);
// AI 对 AI
reply = await rpc('start', { seats: [slugs[0], slugs.at(-1)], human: null, seed: 7 });
let n = 1;
while (!reply.over) { reply = await rpc('step', { inputs: [{}, {}, {}, {}] }); n += reply.frames.length; }
assert.equal(check(7), true);
assert(!reply.broken.some(Boolean));
console.log(`worker + local Pyodide: human match ${frames} frames, ${slugs[0]} vs ${slugs.at(-1)} ${n} frames, both replay-identical; no network`);
