// 量名单里每家程序在 Pyodide 里一帧多久，以及整帧（两家 decide + 引擎结算 + 帧快照 JSON）多久。
// node benchmark.mjs [dist] [--seeds 3,17]   每家坐左边、右边是陪练打满整场；最后一组是名单前两家互打。
// 只用构建里的本地 Pyodide，禁止联网。30 帧/秒的预算是每帧 33.3 毫秒。
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const flag = (k, d) => { const i = args.indexOf(k); return i >= 0 ? args.splice(i, 2)[1] : d; };
const seeds = flag('--seeds', '3,17').split(',').map(Number);
const out = path.resolve(args[0] || path.join(here, 'dist'));
globalThis.fetch = () => { throw new Error('Network is forbidden in this benchmark'); };
const require = createRequire(import.meta.url);
const manifest = JSON.parse(fs.readFileSync(path.join(out, 'manifest.json'), 'utf8'));
const { loadPyodide } = require(path.join(out, `pyodide-${manifest.pyodide}/pyodide.js`));
const py = await loadPyodide({ indexURL: path.join(out, `pyodide-${manifest.pyodide}/`), stdout() {}, stderr() {} });
py.FS.mkdirTree('/app/bots');
for (const name of manifest.files) py.FS.writeFile(`/app/${name}`, fs.readFileSync(path.join(out, name), 'utf8'));
py.runPython('import sys; sys.path.insert(0, "/app")');
const report = py.runPython(`
import json, time, driver
slugs = ${JSON.stringify(manifest.cast.map(c => c.slug))}
seeds = ${JSON.stringify(seeds)}
def run(pair):
    ms, frames, broken, batch = [], 0, [0, 0], []
    for seed in seeds:
        t = driver.Table(pair, None, seed)
        while not t.g.over():
            t0 = time.perf_counter()
            reply = json.loads(driver.rpc.__globals__['json'].dumps(t.step([{}] * 4)))
            batch.append((time.perf_counter() - t0) * 1000 / max(1, len(reply['frames'])))
        frames += t.g.turn
        s = t.stats()
        ms.append(s)
        broken = [broken[i] + int(t.broken[i]) for i in (0, 1)]
    calls = [sum(s['calls'][i] for s in ms) for i in (0, 1)]
    mean = [round(sum(s['mean_ms'][i] * s['calls'][i] for s in ms) / max(1, calls[i]), 3) for i in (0, 1)]
    batch.sort()
    return {'pair': pair, 'frames': frames, 'decide_mean_ms': mean, 'decide_max_ms': [max(s['max_ms'][i] for s in ms) for i in (0, 1)],
            'frame_mean_ms': round(sum(batch) / len(batch), 3), 'frame_p95_ms': round(batch[int(len(batch) * .95)], 3),
            'frame_max_ms': round(batch[-1], 3), 'broken': broken}
rows = [run([s, 'baseline']) for s in slugs]
if len(slugs) > 2:
    rows.append(run(slugs[:2]))
json.dumps({'pyodide': '${manifest.pyodide}', 'python': sys.version.split()[0], 'budget_ms': 33.3, 'rows': rows})
`);
console.log(JSON.stringify(JSON.parse(report), null, 2));
