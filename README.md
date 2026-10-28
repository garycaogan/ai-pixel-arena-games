# AI 像素擂台 · 小游戏

10 个 AI 拿同一份题，各自写一个游戏程序，再让这些程序在同一个赛场里对打。这个仓库放的是能玩、能复现的部分：游戏引擎、各家 AI 交上来的程序、网页版和美术。比赛过程做成了视频，在 B 站「AI 像素擂台」。

在线玩：<https://lab.ytdeepsea.com/games/>

## 炸弹派对

第一款是炸弹派对：13×13 的场地，4 个人各占一个角，炸木箱、捡道具、用炸弹把别人困住。道具三种：火力（炸得更远）、加弹（同时多放一颗）、踢弹（把炸弹踢出去滑行）。第 80 回合起，场地边上开始一块块落墙，一圈圈往里压，被压到就出局，活到最后的人赢。

网页版 <https://lab.ytdeepsea.com/games/bomb-party/> 可以自己上场和 3 个 AI 打，也可以只看 AI 对打。对手就是下面这 10 家写的程序，原样在你的浏览器里跑（Pyodide）。

### 这 10 个程序是怎么写出来的

10 家 AI 拿到一字不差的同一份题（`games/bomb_party/BRIEF.md`），各自在一个断网的工位里干 45 分钟：能读裁判的全部源码，能跟陪练试打，能看表；开赛 20 分钟以后才能交卷，可以交很多次，算最后一次。GPT 用的是 OpenAI 的 Codex 命令行，Claude 用的是 Anthropic 的 Claude Code，另外 8 家走 API，用同一套工位程序（跑命令、读文件、写文件三个工具）。思考档都开 high，8 家 API 各有花费上限，到了就提示马上交卷。

| 程序 | 模型 | 怎么写的 | 交卷 | 试打局数 |
|---|---|---|---|---|
| `opus.py` | Claude Opus 5.5 | Claude Code | 2 版，最后一版第 29.3 分钟 | 2,824 |
| `astra.py` | GPT-6 Astra | Codex | 2 版，最后一版第 43.3 分钟 | 164 |
| `gemini.py` | Gemini 4 Argon | API + 工位程序 | 1 版，最后一版第 20.6 分钟 | 96 |
| `deepseek.py` | DeepSeek V4.1 Flash | API + 工位程序 | 1 版，最后一版第 39.1 分钟 | 104 |
| `kimi.py` | Kimi K3 | API + 工位程序 | 2 版，最后一版第 29.0 分钟 | 252 |
| `doubao.py` | 豆包 Seed 2.0 Pro | API + 工位程序 | 3 版，最后一版第 32.0 分钟 | 534 |
| `qwen.py` | Qwen 3.8 Max | API + 工位程序 | 3 版，最后一版第 40.7 分钟 | 8 |
| `glm.py` | GLM 5.3 | API + 工位程序 | 3 版，最后一版第 44.8 分钟 | 48 |
| `minimax.py` | MiniMax M3 | API + 工位程序 | 3 版，最后一版第 42.4 分钟 | 10 |
| `grok.py` | Grok 4.7 | API + 工位程序 | 1 版，最后一版第 22.2 分钟 | 73 |

两件要说明的事：Gemini 交完第 1 版后，下一个请求连续 5 次超过网关等待时间，第 31 分钟被工位停掉，算的是第 1 版。工位程序当时会把聊天记录里的旧代码缩成头尾、中间写「…省略 N 字…」，Gemini、Kimi、GLM 都照着这个写法把半截代码写进过 `bot.py`，各自花了时间修（GLM 在第 43 分钟中招，最后交的是 1 分钟里重写的兜底版）。最后交的程序里都没有这个标记，这个压缩之后也去掉了。

### 成绩

10 家 AI 加 2 个陪练抽签分 3 组，每组 4 局、四个出生角每人各站一次，名次积分 3/2/1/0；每组最好的 AI 和成绩最好的小组第二进决赛，再打 4 局。`tools/cup.py` 用同样的种子能原样复现。

| 选手 | 名次 | 小组赛（4 局名次） | 决赛（4 局名次） |
|---|---|---|---|
| Claude Opus 5.5 | 冠军 | C 组 12 分（1 1 1 1） | 11 分（2 1 1 1） |
| Gemini 4 Argon | 亚军 | A 组 12 分（1 1 1 1） | 7 分（1 2 3 3） |
| GPT-6 Astra | 季军 | B 组 10 分（1 1 1 3） | 4 分（3 3 4 2） |
| MiniMax M3 | 第四 | C 组 7 分（3 2 2 2） | 2 分（4 4 2 4） |
| GLM 5.3 | 小组未出线 | B 组 6 分（3 3 2 2） | — |
| DeepSeek V4.1 Flash | 小组未出线 | A 组 5 分（2 4 2 3） | — |
| Kimi K3 | 小组未出线 | C 组 5 分（2 3 3 3） | — |
| Qwen 3.8 Max | 小组未出线 | A 组 4 分（3 2 3 4） | — |
| 豆包 Seed 2.0 Pro | 小组未出线 | B 组 1 分（4 4 4 3） | — |
| Grok 4.7 | 小组未出线 | C 组 0 分（4 4 4 4） | — |

16 局一共 48 次出局：28 次是被自己的炸弹炸死，14 次被墙压死，被对手炸死的只有 6 次。

## 在本地跑

只需要 Python 3.13 标准库，不装任何包。

```sh
# 打一局：4 个程序各坐一个角
python3 tools/play.py opus astra kimi grok

# 换图、存回放
python3 tools/play.py opus astra kimi grok --seed 7 --export game.json

# 按视频里的赛制打一遍小组赛加决赛，结果写到 results/bomb_party/cup.json
python3 tools/cup.py --bots-dir bots/bomb_party

# 引擎测试
python3 -m unittest games.bomb_party.tests.test_engine
```

每个程序在单独的子进程里跑，每步 50 毫秒 CPU，和比赛时一样。macOS 上默认再套一层 `sandbox-exec`（禁止读写文件、联网），设 `ARENA_NO_SANDBOX=1` 可以关掉。

## 让你的 AI 也写一个

把 `games/bomb_party/PROMPT.md` 交给你常用的 AI，让它写一个 `bot.py`（只用 Python 标准库，实现 `decide(state)`，返回 `up`、`down`、`left`、`right`、`bomb` 或 `stay`），然后：

```sh
python3 tools/play.py path/to/bot.py opus astra gemini
```

`games/bomb_party/BRIEF.md` 是比赛时每家 AI 收到的完整原题，包括工位说明。`bots/bomb_party/notes/` 是它们交卷时自己写的打法说明和赛前宣言。

## 网页版

源码在 `web/bomb-party/`。浏览器里用 Pyodide 跑同一份 `engine.py` 和各家程序，画面是 `art/bomb-party/render-bomber.js`。

```sh
cd web/bomb-party
# 先把 Pyodide 0.29.5 的发布包（GitHub Release 里的 pyodide-0.29.5.tar.bz2）解压到 pyodide-0.29.5/
python3 build.py
python3 -m http.server 8765 --bind 127.0.0.1 --directory dist
```

然后打开 <http://127.0.0.1:8765/>。不要直接用 `file://` 打开。页面会往同域的 `/_e` 发不带玩家标识的对局统计，静态服务器上这个请求返回 404，不影响游戏。

网页里的程序没有真正的安全沙箱：单步超过 2.5 秒会被停用，但不能强行打断一次很长的原生调用。只放你信得过的程序。

## 目录

```
games/bomb_party/   引擎、规则、给 AI 的原题、陪练、演示、测试
bots/bomb_party/    10 家 AI 的程序、3 个测试陪练、notes/ 各家自己写的说明
arena/              裁判：子进程跑程序、限时、按回合收动作
tools/              play.py 打一局，cup.py 小组赛加决赛
web/bomb-party/     网页版
art/bomb-party/     GPT Image 生成的精灵图、切图脚本、渲染器、提示词
```

## 美术

人物、地块、道具和场地是用 GPT Image 生成的三张图，`art/bomb-party/cut_art.py` 切成 32 像素一格的精灵，提示词在 `p-*.txt`。`render-bomber.js` 按小数回合号插值画走路、放弹、爆炸、碎箱、落墙，机器人身上的青色按选手换色。

## 许可

MIT，见 `LICENSE`。「炸弹派对」是这个项目自己的游戏，和任何商业游戏没有关系。各家 AI 的名字和商标归各自公司所有。
