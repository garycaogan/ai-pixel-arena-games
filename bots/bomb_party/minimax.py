"""炸弹派对（Bomber II）AI

核心思路
--------
1) 精确推演：把场上炸弹按引信排开，逐回合推进，得到"第 0~5 回合末"每一格的火焰；
   再叠加压墙时间表（钢墙逐格填满整张地图，最后只剩中心几个格）。
2) 生存优先：落脚点不仅要求本回合末不在火里，还要求"从那里还能一直跑下去"
   （深度 6 的逃生搜索 + 压墙规避）。所有候选动作先按存活回合数排序。
3) 进攻：算出对手 3 步内可能待的格子，我脚下的弹若能全部罩住就是必杀；
   否则炸砖开路、封锁走位。
4) 节奏：压墙从 crush_start 起每回合填一格，越到后期越往中心收缩（中心最后被压）。
"""
from collections import deque

DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
ORDER = ("up", "down", "left", "right")
HORIZON = 6

_VISIT = set()


def _spiral(size):
    cells = []
    lo, hi = 0, size - 1
    while lo <= hi:
        cells.extend((x, lo) for x in range(lo, hi + 1))
        cells.extend((hi, y) for y in range(lo + 1, hi + 1))
        if lo < hi:
            cells.extend((x, hi) for x in range(hi - 1, lo - 1, -1))
            cells.extend((lo, y) for y in range(hi - 1, lo, -1))
        lo, hi = lo + 1, hi - 1
    return cells


def _crush_schedule(w, h, rot, crush_start):
    sched = {}
    cells = _spiral(w)
    for _ in range(rot % 4):
        cells = [(w - 1 - y, x) for x, y in cells]
    k = 0
    for (x, y) in cells:
        if x in (0, w - 1) or y in (0, h - 1) or (x % 2 == 0 and y % 2 == 0):
            continue
        sched[(x, y)] = crush_start + k
        k += 1
    return sched


class Board:
    def __init__(self, state):
        self.t = state["turn"]
        self.w = state["width"]
        self.h = state["height"]
        self.grid = state["grid"]
        self.me = None
        self.opps = []
        for p in state["players"]:
            if p["id"] == state["you"]:
                self.me = p
            else:
                self.opps.append(p)
        self.bombs = [dict(b) for b in state["bombs"]]
        self.bomb_fuse = state.get("bomb_fuse", 3)
        self.items = {}
        for it in state["items"]:
            self.items[(it["x"], it["y"])] = it["kind"]
        self.crush = _crush_schedule(self.w, self.h, state.get("crush_rotation", 0),
                                     state.get("crush_start", 80))
        self.bomb_cells = set((b["x"], b["y"]) for b in self.bombs)
        self.occ = set((p["x"], p["y"]) for p in state["players"])
        self.future = self._simulate()

    # ---- 地形 -----------------------------------------------------
    def wall(self, x, y):
        if x < 0 or y < 0 or x >= self.w or y >= self.h:
            return True
        return self.grid[y][x] != "."

    # ---- 爆炸 -----------------------------------------------------
    def ray(self, bx, by, radius, bombset=None):
        cells = [(bx, by)]
        for dx, dy in DIRS.values():
            for d in range(1, radius + 1):
                x, y = bx + dx * d, by + dy * d
                if x < 0 or y < 0 or x >= self.w or y >= self.h:
                    break
                if self.grid[y][x] == "@":
                    break
                cells.append((x, y))
                if self.grid[y][x] == "#":
                    break
                if bombset is not None and (x, y) in bombset:
                    break
        return cells

    def flames(self, exploding, allbombs=None):
        """爆炸（含连锁）的火焰格集合。"""
        if allbombs is None:
            allbombs = exploding
        bombset = set((b["x"], b["y"]) for b in allbombs)
        out = set()
        queue = deque(sorted(exploding, key=lambda b: b["id"]))
        seen = set()
        while queue:
            b = queue.popleft()
            if b["id"] in seen:
                continue
            seen.add(b["id"])
            cells = self.ray(b["x"], b["y"], b["radius"], bombset)
            out.update(cells)
            for ob in allbombs:
                if ob["id"] in seen or ob["id"] == b["id"]:
                    continue
                if (ob["x"], ob["y"]) in cells:
                    queue.append(ob)          # 连锁引爆
        return out

    def _simulate(self):
        """future[e] = 第 e 回合末（e 从 0 开始）会起火的格子。"""
        bombs = [dict(b) for b in self.bombs]
        danger = []
        for _ in range(HORIZON):
            boom = [b for b in bombs if b["fuse"] == 1]
            danger.append(self.flames(boom, bombs))
            rest = [b for b in bombs if b["fuse"] != 1]
            for b in rest:
                b["fuse"] -= 1
                if b.get("direction"):
                    dx, dy = DIRS[b["direction"]]
                    nx, ny = b["x"] + dx, b["y"] + dy
                    if self.wall(nx, ny) or (nx, ny) in self.bomb_cells:
                        b["direction"] = None
                    else:
                        b["x"], b["y"] = nx, ny
            bombs = rest
        return danger

    # ---- 安全 / 逃生 ----------------------------------------------
    def safe_at(self, cell, e, extra=None):
        if cell is None:
            return False
        if e < len(self.future) and cell in self.future[e]:
            return False
        if extra and e in extra and cell in extra[e]:
            return False
        ct = self.crush.get(cell)
        if ct is not None and ct <= self.t + e:
            return False
        return True

    def mobility(self, pos, extra=None):
        """从 pos 出发，下一个回合末还有多少个安全落点（越多越不容易被堵死）。"""
        n = 0
        seen = set()
        for (x, y) in ((pos[0] + dx, pos[1] + dy) for dx, dy in DIRS.values()):
            if self.wall(x, y) or (x, y) in self.bomb_cells:
                continue
            if self.safe_at((x, y), 1, extra):
                seen.add((x, y))
        if self.safe_at(pos, 1, extra):
            seen.add(pos)
        return len(seen)

    def survive(self, pos, extra=None, blocked=None, horizon=HORIZON):
        """从 pos 出发还能活几个回合末；-1 = 本回合末就死。"""
        if not self.safe_at(pos, 0, extra):
            return -1
        frontier = {pos}
        alive = 0
        for e in range(1, horizon + 1):
            nxt = set()
            for (x, y) in frontier:
                if self.safe_at((x, y), e, extra):
                    nxt.add((x, y))            # 原地不动
                for dx, dy in DIRS.values():
                    q = (x + dx, y + dy)
                    if self.wall(q[0], q[1]):
                        continue
                    if blocked and e in blocked and q in blocked[e] and q != (x, y):
                        continue
                    if self.safe_at(q, e, extra):
                        nxt.add(q)
            if not nxt:
                break
            frontier = nxt
            alive = e
        return alive

    def reach(self, opp, steps=3):
        """对手 steps 步内可能待的格子（粗略上界）。"""
        start = (opp["x"], opp["y"])
        seen = {start}
        frontier = {start}
        blocked = set(self.occ)
        for _ in range(steps):
            nxt = set()
            for (x, y) in frontier:
                for dx, dy in DIRS.values():
                    q = (x + dx, y + dy)
                    if self.wall(q[0], q[1]) or q in blocked:
                        continue
                    if q in self.bomb_cells:
                        continue
                    if q not in seen:
                        seen.add(q)
                        nxt.add(q)
            frontier = nxt
        return seen


ITEM_VALUE = {"fire": 10.0, "bomb": 9.0, "kick": 11.0}
ITEM_NEAR = {"fire": 2.2, "bomb": 1.8, "kick": 2.6}


def _decide(state):
    b = Board(state)
    me = b.me
    my = (me["x"], me["y"])
    turn = b.t
    radius = me.get("radius", 2)
    _VISIT.add(my)

    # ---------- 普通移动 / 原地 ----------
    cands = []
    for d in ORDER:
        dx, dy = DIRS[d]
        q = (my[0] + dx, my[1] + dy)
        if b.wall(q[0], q[1]) or q in b.occ or q in b.bomb_cells:
            continue
        cands.append((q, d))
    cands.append((my, "stay"))

    def base_score(pos, dep):
        s = dep * 10.0
        if pos in b.items:
            s += ITEM_VALUE[b.items[pos]]
        else:
            for dx, dy in DIRS.values():
                q = (pos[0] + dx, pos[1] + dy)
                if q in b.items:
                    s += ITEM_NEAR[b.items[q]]
                    break
        ct = b.crush.get(pos)
        if ct is not None:
            late = ct - turn
            s += 0.0 if late <= 0 else min(8.0, late * 0.06)
        if pos not in _VISIT:
            s += 1.5
        s += 1.2 * b.mobility(pos)
        # 目标格被人盯着 -> 可能被抢（同时移动竞争同一格），轻微惩罚
        for opp in b.opps:
            if abs(opp["x"] - pos[0]) + abs(opp["y"] - pos[1]) == 1:
                s -= 0.0
        return s

    scored = []
    for (pos, act) in cands:
        dep = b.survive(pos)
        if dep < 0:
            continue
        s = base_score(pos, dep)
        for opp in b.opps:
            d = abs(pos[0] - opp["x"]) + abs(pos[1] - opp["y"])
            if d <= 1:
                s -= 3.0
            elif d == 2:
                s -= 0.5
        scored.append((s, act))

    # ---------- 放弹 ----------
    if me.get("can_bomb") and my not in b.bomb_cells:
        fire = set(b.ray(my[0], my[1], radius))
        myr = radius
        # 新弹 fuse=3：回合末不减，第 3 个回合末才爆（turn+3 结束）
        extra = {3: fire}
        blocked = {1: {my}, 2: {my}, 3: {my}}
        # 连锁：若已有炸弹爆炸时波及我脚下这枚新弹，新弹会提前引爆（而且会炸我）
        bombset = set((bb["x"], bb["y"]) for bb in b.bombs)
        for bb in b.bombs:
            if bb["fuse"] >= 2:
                e0 = bb["fuse"] - 1
                fl = b.ray(bb["x"], bb["y"], bb["radius"], bombset)
                if my in fl:
                    extra.setdefault(e0, set()).update(b.ray(my[0], my[1], myr))
                    extra.setdefault(e0, set()).add(my)
        dep = b.survive(my, extra, blocked)
        if dep >= 4:
            s = base_score(my, dep) + 2.0
            kill = 0
            for opp in b.opps:
                if opp.get("can_kick"):
                    d = abs(opp["x"] - my[0]) + abs(opp["y"] - my[1])
                    if d == 1:
                        continue
                reach = b.reach(opp, steps=b.bomb_fuse)
                if reach <= fire:
                    kill = max(kill, 3)
                else:
                    cov = len(reach & fire) / float(len(reach))
                    if cov >= 0.99:
                        kill = max(kill, 2)
                    elif cov >= 0.6:
                        kill = max(kill, 1)
            n_brick = 0
            for dx, dy in DIRS.values():
                for d in range(1, radius + 1):
                    x, y = my[0] + dx * d, my[1] + dy * d
                    if x < 0 or y < 0 or x >= b.w or y >= b.h:
                        break
                    if b.grid[y][x] == "@":
                        break
                    if b.grid[y][x] == "#":
                        n_brick += 1
                        break
            s += kill * 26.0 + min(n_brick, 4) * 1.6
            # 别把唯一的退路自己炸了：如果脚下弹的火会盖住太多空间，略降分
            scored.append((s, "bomb"))

    # ---------- 踢弹 ----------
    if me.get("can_kick"):
        for ob in b.bombs:
            if abs(ob["x"] - my[0]) + abs(ob["y"] - my[1]) != 1:
                continue
            d = None
            for name, (dx, dy) in DIRS.items():
                if (my[0] + dx, my[1] + dy) == (ob["x"], ob["y"]):
                    d = name
                    break
            if d is None:
                continue
            kdx, kdy = DIRS[d]
            tgt = (ob["x"] + kdx, ob["y"] + kdy)
            if b.wall(tgt[0], tgt[1]) or tgt in b.bomb_cells:
                continue
            newf = b.flames([dict(ob, x=tgt[0], y=tgt[1])])
            if my not in newf:
                dep = b.survive(my)
                s = base_score(my, dep) + 4.0
                for opp in b.opps:
                    if abs(tgt[0] - opp["x"]) + abs(tgt[1] - opp["y"]) <= 1:
                        s += 8.0
                scored.append((s, d))

    if not scored:
        return "stay"
    scored.sort(key=lambda t: (-t[0], t[1]))
    return scored[0][1]


_ERR = None


def decide(state):
    global _ERR
    try:
        _ERR = None
        return _decide(state)
    except Exception:
        import traceback
        _ERR = traceback.format_exc()
        return "stay"
