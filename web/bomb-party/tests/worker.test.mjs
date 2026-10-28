// Execute worker.js with real local Pyodide; emulate only Worker I/O, no browser.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createRequire } from 'node:module';
const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(here, '../dist');
const manifest = JSON.parse(fs.readFileSync(path.join(out, 'manifest.json'), 'utf8'));
globalThis.fetch = () => { throw new Error('Network is forbidden'); };
const require = createRequire(import.meta.url);
const { loadPyodide } = require(path.join(out, 'pyodide-0.29.5/pyodide.js'));
let py, ready, rejectReady;
const boot = new Promise((resolve, reject) => { ready = resolve; rejectReady = reject; });
const messages = [], fetched = [];
const sandbox = { URL, self: { location: pathToFileURL(path.join(out, 'worker.js')).href + '?v=' + manifest.version },
  importScripts: name => assert.equal(name, 'pyodide-0.29.5/pyodide.js'),
  loadPyodide: async options => {
    options.indexURL = fileURLToPath(options.indexURL);
    py = await loadPyodide(options);
    return py;
  },
  fetch: async (name, options) => {
    fetched.push({ name, options });
    assert(!name.includes('://'), 'worker assets must use relative paths');
    const data = fs.readFileSync(path.join(out, name.split('?')[0]), 'utf8');
    return { ok: true, text: async () => data, json: async () => JSON.parse(data) };
  },
  postMessage: value => {
    messages.push(value);
    if (value.type === 'ready') ready();
    if (value.type === 'fatal') rejectReady(new Error(value.message));
  }
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
// 坐名单里的程序（10/28 起是杯赛各家 AI 加陪练），不写死测试陪练
let reply = await rpc('start', { seats: ['human', 'opus', 'baseline', 'grok'], human: 0, seed: 43 });
assert.equal(reply.frame.turn, 0);
while (!reply.over) reply = await rpc('step', { action: ['right', 'down', 'bomb', 'left', 'up', 'stay'][reply.frame.turn % 6] });
const consistent = py.runPython(`
import driver, engine
t = driver._table
replayed = engine.replay(4, 43, t.rows)
replayed.frame() == t.g.frame() and replayed.events == t.g.events
`);
assert.equal(consistent, true);
assert.equal(reply.place.length, 4);
assert(!reply.broken.some(Boolean));
console.log(`Worker + local Pyodide: ready/progress/RPC, full ${reply.frame.turn}-round human match and engine replay passed; no network`);
