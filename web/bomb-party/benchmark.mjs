// Uses only the copied local runtime. Any network attempt is a test failure.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.resolve(process.argv[2] || path.join(here, 'dist'));
globalThis.fetch = () => { throw new Error('Network is forbidden in this benchmark'); };
const require = createRequire(import.meta.url);
const { loadPyodide } = require(path.join(out, 'pyodide-0.29.5/pyodide.js'));
const py = await loadPyodide({ indexURL: path.join(out, 'pyodide-0.29.5/'), stdout() {}, stderr() {} });
const manifest = JSON.parse(fs.readFileSync(path.join(out, 'manifest.json'), 'utf8'));
py.FS.mkdirTree('/app/bots');
for (const name of manifest.files) py.FS.writeFile(`/app/${name}`, fs.readFileSync(path.join(out, name), 'utf8'));
py.runPython('import sys; sys.path.insert(0, "/app")');
const report = py.runPython(`
import json, time, driver
slugs = ${JSON.stringify(manifest.cast.map(c => c.slug))}
samples = {s: [] for s in slugs}
rounds = []
games = []
for seed in (0, 7, 43, 101, 2026, 888):
    table = driver.Table(slugs, None, seed)
    while not table.g.over():
        start = time.perf_counter()
        reply = table.step()
        rounds.append((time.perf_counter() - start) * 1000)
        for seat, ms in reply['ms'].items():
            samples[slugs[seat]].append(ms)
        if any(table.broken):
            raise AssertionError('a sparring bot failed: ' + str(reply))
    games.append({'seed': seed, 'turns': table.g.turn, 'place': table.g.placements()})
json.dumps({'pyodide': '0.29.5', 'python': sys.version.split()[0], 'games': games,
 'bots': {s: {'steps': len(v), 'mean_ms': round(sum(v)/len(v), 3), 'max_ms': max(v)} for s,v in samples.items()},
 'whole_round': {'steps': len(rounds), 'mean_ms': round(sum(rounds)/len(rounds), 3), 'max_ms': round(max(rounds), 3)},
 'includes_deadline_tracing': True, 'network': False})
`);
console.log(JSON.stringify(JSON.parse(report), null, 2));
