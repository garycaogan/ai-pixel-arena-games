# 像素拳斗网页版

浏览器里和 AI 写的程序 1 对 1 打格斗，三局两胜；也能挑两家 AI 看它们对打。引擎、画法、角色图直接用 `games/brawl/` 里的 `engine.py`、`render.js`、`sprites.js`，各家程序和引擎一起在 Pyodide（Web Worker）里每帧调 `decide(state)`。

```sh
# 先把 Pyodide 0.29.5 的发布包（GitHub Release 里的 pyodide-0.29.5.tar.bz2）解压到 pyodide-0.29.5/
python3 build.py
python3 -m http.server 8765 --bind 127.0.0.1 --directory dist
```

然后打开 <http://127.0.0.1:8765/>，不要用 `file://`。名单在 `build.py` 顶部的 `CAST`，程序从 `bots/brawl/<名字>.py` 读，第一家是开局默认对手。

键位：A/D 或 ←/→ 走（往后就是站防），W/↑ 跳，S/↓ 蹲（后下是蹲防），同方向连按两下冲刺或后撤步；J 轻拳、K 重拳、L 脚、U 扫腿、I 投、空格 必杀技、O 对空技、P 超必杀。手机上是左边摇杆、右边八个键。

帧时钟 30 帧/秒。真人在打时只提前算 1 帧，看 AI 对打时提前算 10 帧；某家程序一帧算得慢时整场放慢，不跳帧。程序返回非法值或报错按站着不动处理，连续三次或单次超过 1 秒就停用这家。网页里的程序没有真正的安全沙箱，只放你信得过的程序。

```sh
python3 -m unittest -v tests.test_game     # 驱动（重放一致、朝向、出招缓冲、坏程序）和构建
node tests/input.test.cjs                  # 键盘和摇杆取样
node tests/worker.test.mjs                 # 真 worker.js 加本地 Pyodide 打两整场，重放比对
node benchmark.mjs                         # 每家程序在 Pyodide 里一帧多久
```
