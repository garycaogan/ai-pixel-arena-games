'use strict';
importScripts('__PYODIDE__/pyodide.js');

let driver;
const boot = (async () => {
  const progress = (stage) => postMessage({ type: 'progress', stage });
  progress('正在加载本地 Python 运行环境…');
  const py = await loadPyodide({ indexURL: new URL('__PYODIDE__/', self.location).href, stdout() {}, stderr() {} });
  const response = await fetch('manifest.json', { cache: 'no-store' });
  if (!response.ok) throw new Error('找不到游戏清单，请重新构建');
  const manifest = await response.json();
  if (new URL(self.location).searchParams.get('v') !== manifest.version) throw new Error('游戏已更新，请刷新页面');
  progress('正在加载引擎和 AI 陪练…');
  py.FS.mkdirTree('/app/bots');
  await Promise.all(manifest.files.map(async (file) => {
    const response = await fetch(`${file}?v=${manifest.version}`);
    if (!response.ok) throw new Error(`无法加载 ${file}`);
    py.FS.writeFile(`/app/${file}`, await response.text());
  }));
  py.runPython('import sys; sys.path.insert(0, "/app"); sys.setrecursionlimit(3000)');
  driver = py.pyimport('driver');
  postMessage({ type: 'ready' });
})().catch(error => postMessage({ type: 'fatal', message: String(error.message || error) }));

onmessage = async ({ data: { id, cmd, args } }) => {
  try {
    await boot;
    if (!driver) throw new Error('Python 加载失败，请刷新重试');
    const value = driver.rpc(cmd, JSON.stringify(args || {}));
    postMessage({ type: 'reply', id, ok: true, data: JSON.parse(value) });
  } catch (error) {
    postMessage({ type: 'reply', id, ok: false, error: String(error.message || error).slice(-600) });
  }
};
