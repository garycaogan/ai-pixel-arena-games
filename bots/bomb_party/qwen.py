"""炸弹派对 · 强对抗版

核心：
1. 精确复算引擎时序（移动→拾取→放弹→滑行→连锁爆炸→压墙），把"第 d 回合末的火焰"
   预计算成位掩码；逃生用时间扩展 BFS（炸弹会消失、格子会空出来）。
2. 进攻三层：放弹必杀（trap 分析）→ 踢弹必杀/逼迫 → 潜力场（炸砖、抢道具、
   把对手往死角赶、避免被夹击）。
3. 自己按 seed 的旋转量重算完整压墙螺旋（state 只预告 5 块），提前让开。
4. 全局 try/except，任何异常退回 stay；位运算保证每步远低于 50ms CPU。
"""

DIRS = ((0, -1), (0, 1), (-1, 0), (1, 0))          # up down left right
DNAMES = ("up", "down", "left", "right")
DVEC = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
AIDX = {"stay": 0, "up": 1, "down": 2, "left": 3, "right": 4, "bomb": 5}
MOVES = ("stay", "up", "down", "left", "right", "bomb")
BIG = 1 << 40


# ------------------------------------------------------------------ 位工具
def bits(m):
    while m:
        b = m & -m
        yield b.bit_length() - 1
        m ^= b


def nbits(m):
    c = 0
    while m:
        m &= m - 1
        c += 1
    return c


def spiral_cells(n):
    cells = []
    lo, hi = 0, n - 1
    while lo <= hi:
        for x in range(lo, hi + 1):
            cells.append((x, lo))
        for y in range(lo + 1, hi + 1):
            cells.append((hi, y))
        if lo < hi:
            for x in range(hi - 1, lo - 1, -1):
                cells.append((x, hi))
            for y in range(hi - 1, lo, -1):
                cells.append((lo, y))
        lo, hi = lo + 1, hi - 1
    return cells


# ------------------------------------------------------------------ 静态信息
class Sim:
    def __init__(self, st):
        W = self.W = st["width"]
        H = self.H = st["height"]
        N = W * H
        steel0 = 0
        for y in range(H):
            for x in range(W):
                if x in (0, W - 1) or y in (0, H - 1) or (x % 2 == 0 and y % 2 == 0):
                    steel0 |= 1 << (y * W + x)
        self.steel0 = steel0
        grid = st["grid"]
        brick = 0
        steel = steel0
        for y in range(H):
            row = grid[y]
            for x in range(W):
                c = row[x]
                if c == "#":
                    brick |= 1 << (y * W + x)
                elif c == "@":
                    steel |= 1 << (y * W + x)
        self.brick = brick
        self.steel = steel
        self.walk = ((1 << N) - 1) & ~steel & ~brick
        self.floor = ((1 << N) - 1) & ~steel
        # 邻居位
        self.nb = [0] * N
        for y in range(H):
            for x in range(W):
                k = y * W + x
                s = 1 << k
                if x:
                    s |= 1 << (k - 1)
                if x < W - 1:
                    s |= 1 << (k + 1)
                if y:
                    s |= 1 << (k - W)
                if y < H - 1:
                    s |= 1 << (k + W)
                self.nb[k] = s
        # 静态射线（遇砖/钢停）：ray[k] = (up,down,left,right)
        self.ray = [None] * N
        for y in range(H):
            for x in range(W):
                k = y * W + x
                out = []
                for dx, dy in DIRS:
                    a, b = x + dx, y + dy
                    ks = []
                    while 0 <= a < W and 0 <= b < H:
                        kk = b * W + a
                        ks.append(kk)
                        if (steel >> kk) & 1 or (brick >> kk) & 1:
                            break
                        a += dx
                        b += dy
                    out.append(ks)
                self.ray[k] = out
        # 压墙时间表（用开局钢墙判定过滤，和引擎一致）
        cs = self.crush_start = st.get("crush_start", 80) or 80
        rot = (st.get("crush_rotation", 0) or 0) % 4
        cells = spiral_cells(W)
        for _ in range(rot):
            cells = [(W - 1 - y, x) for x, y in cells]
        cells = [(x, y) for x, y in cells if not (steel0 >> (y * W + x)) & 1]
        nc = st.get("next_crush") or []
        idx = len(st.get("crushed") or [])
        self.crush_ok = bool(cells) and len(nc) >= 1 and \
            cells[idx:idx + len(nc)] == [(c["x"], c["y"]) for c in nc]
        self.crush_turn_of = {}
        if self.crush_ok:
            for i, (x, y) in enumerate(cells):
                self.crush_turn_of[(x, y)] = cs + i
            self.crush_cells = cells
            self.crush_last = cs + len(cells) - 1
        else:
            for c in nc:
                self.crush_turn_of[(c["x"], c["y"])] = c["turn"]
            self.crush_last = max((c["turn"] for c in nc), default=cs)
        self.crush_min = min(self.crush_turn_of.values()) if self.crush_turn_of else BIG
        # 每回合落哪块（用于火焰模拟）
        self.crush_by_turn = {}
        for (x, y), t in self.crush_turn_of.items():
            self.crush_by_turn.setdefault(t, []).append(y * W + x)


# ------------------------------------------------------------------ 局面
class G:
    """一回合的局面 + 未来火焰模拟。"""

    def __init__(self, st, sim):
        self.st = st
        self.sim = sim
        self.W = sim.W
        self.T = st["turn"]
        self.max_turns = st.get("max_turns", 270)
        self.fuse_full = st.get("bomb_fuse", 3) or 3
        self.max_radius = st.get("max_radius", 8)
        W = self.W
        self.me = st["you"]
        self.items = {}
        self.item_mask = 0
        for it in st.get("items") or []:
            k = it["y"] * W + it["x"]
            self.items[k] = it["kind"]
            self.item_mask |= 1 << k
        self.p = {}
        for pl in st["players"]:
            self.p[pl["id"]] = pl
        my = self.p[self.me]
        self.my = my
        self.mk = my["y"] * W + my["x"]
        self.mx, self.myy = my["x"], my["y"]
        self.radius = my["radius"]
        self.limit = my["bomb_limit"]
        self.active = my["active_bombs"]
        self.can_kick = bool(my["can_kick"])
        self.can_bomb = bool(my.get("can_bomb", self.active < self.limit))
        self.opp_mask = 0
        self.opp = []
        for pid, pl in self.p.items():
            if pid == self.me:
                continue
            self.opp.append(pid)
            self.opp_mask |= 1 << (pl["y"] * W + pl["x"])
        self.occ_mask = self.opp_mask | (1 << self.mk)
        self.can_bomb_now = bool(my.get("can_bomb", self.active < self.limit))
        self._sb = {}
        self.bombs = {}
        self.pos0 = {}
        self.new_id = 0
        for b in st.get("bombs") or []:
            k = b["y"] * W + b["x"]
            bb = [b["bid"] if False else b["id"], b["owner"], k, b["x"], b["y"],
                  b["fuse"], b["radius"], b.get("direction"), False]
            self.bombs[bb[0]] = bb
            self.pos0[k] = bb
            if bb[0] >= self.new_id:
                self.new_id = bb[0] + 1
        self.pos0_mask = 0
        for k in self.pos0:
            self.pos0_mask |= 1 << k
        self.nalive = len(self.p)
        # 可变副本
        self.steel = sim.steel
        self.brick = sim.brick
        self.walk = sim.walk
        self.floor = sim.floor
        self.item_mask_cur = self.item_mask
        self.occ_cur = self.occ_mask
        self.bomb_mask_cur = self.pos0_mask
        self.fut = {}
        self.snapshot = None

    # -------------------------------------------------- 快照/还原
    def save(self):
        return (self.steel, self.brick, self.walk, self.floor, self.item_mask_cur,
                self.occ_cur, self.bomb_mask_cur,
                {bid: list(b) for bid, b in self.bombs.items()},
                dict(self.pos0), self.new_id, dict(self.fut))

    def load(self, s):
        (self.steel, self.brick, self.walk, self.floor, self.item_mask_cur,
         self.occ_cur, self.bomb_mask_cur, bb, pos, nid, fut) = s
        self.bombs = bb
        self.pos0 = pos
        self.new_id = nid
        self.fut = fut

    # -------------------------------------------------- 火焰
    def flames(self, extra=(), extra_k=None, extra_r=0):
        """当前炸弹 + 可选新弹(extra_k, extra_r, fuse=full) 的连锁火焰与碎砖。"""
        sim = self.sim
        W = self.W
        steel = self.steel
        brick = self.brick
        pend = []
        fired = {}
        for bid, b in self.bombs.items():
            if b[5] <= 1:
                pend.append(b)
            fired[bid] = b[5] - 1 if b[5] > 1 else 0
        pend.sort(key=lambda b: b[0])
        if extra_k is not None:
            eb = [self.new_id, self.me, extra_k, extra_k % W, extra_k // W,
                  self.fuse_full, extra_r, None, True]
            fired[self.new_id] = self.fuse_full - 1
        flames = 0
        broken = 0
        done = set()
        i = 0
        while i < len(pend):
            b = pend[i]
            i += 1
            if b[0] in done:
                continue
            done.add(b[0])
            k = b[2]
            flames |= 1 << k
            x, y = b[3], b[4]
            r = b[6]
            for d in range(4):
                dx, dy = DIRS[d]
                a, c = x + dx, y + dy
                for _ in range(r):
                    if not (0 <= a < W and 0 <= c < W):
                        break
                    kk = c * W + a
                    if (steel >> kk) & 1:
                        break
                    flames |= 1 << kk
                    if (brick >> kk) & 1:
                        broken |= 1 << kk
                        break
                    hit = None
                    ob = self.pos0.get(kk) if not b[8] else None
                    if ob is None and kk == k:
                        ob = None
                    if ob is None:
                        for bid2, b2 in self.bombs.items():
                            if b2[2] == kk and bid2 not in done:
                                hit = b2
                                break
                    else:
                        if ob[0] not in done:
                            hit = ob
                    if hit is not None:
                        if fired.get(hit[0], 99) <= 0:
                            fired[hit[0]] = 0
                            pend.append(hit)
                        break
                    a += dx
                    c += dy
        return flames, broken

    def _flames_at(self, bomb_at, brick):
        """指定炸弹位置表下的连锁火焰（滑行之后用）。"""
        W = self.W
        steel = self.steel
        pend = []
        fired = {}
        for bid, b in self.bombs.items():
            fired[bid] = b[5] - 1 if b[5] > 1 else 0
            if b[5] <= 1:
                pend.append(b)
        pend.sort(key=lambda b: b[0])
        flames = 0
        broken = 0
        done = set()
        i = 0
        while i < len(pend):
            b = pend[i]
            i += 1
            if b[0] in done:
                continue
            done.add(b[0])
            x, y, r = b[3], b[4], b[6]
            flames |= 1 << (y * self.W + x)
            for d in range(4):
                dx, dy = DIRS[d]
                a, c = x + dx, y + dy
                for _ in range(r):
                    if not (0 <= a < self.W and 0 <= c < self.W):
                        break
                    kk = c * self.W + a
                    if (steel >> kk) & 1:
                        break
                    flames |= 1 << kk
                    if (brick >> kk) & 1:
                        broken |= 1 << kk
                        break
                    ob = bomb_at.get(kk)
                    if ob is not None and ob[0] not in done:
                        if fired.get(ob[0], 99) <= 0:
                            fired[ob[0]] = 0
                            pend.append(ob)
                        break
                    a += dx
                    c += dy
        return flames, broken

    # -------------------------------------------------- 未来推演
    def project(self, my_k, horizon, extra_k=None, extra_r=0, kick=None):
        """推演 1..horizon 回合末的火焰（我此后原地不动）。
        extra_k/extra_r: 我本回合在脚下放的新弹。
        kick: (bomb, act) 我本回合踢的弹。
        返回 list，fut[d] = 第 T+d 回合末火焰掩码。"""
        sim = self.sim
        W = self.W
        sv = self.save()
        if extra_k is not None:
            nb = [self.new_id, self.me, extra_k, extra_k % W, extra_k // W,
                  self.fuse_full, extra_r, None, True]
            self.bombs[nb[0]] = nb
            self.pos0[extra_k] = nb
            self.new_id += 1
        if kick is not None:
            b, act = kick
            dx, dy = DVEC[act]
            a, c = b[3] + dx, b[4] + dy
            ok = 0 <= a < W and 0 <= c < W
            if ok:
                kk = c * W + a
                if (self.steel >> kk) & 1 or (self.brick >> kk) & 1 or kk in self.pos0 \
                        or (self.item_mask_cur >> kk) & 1 or (self.occ_cur >> kk) & 1:
                    ok = False
            if ok:
                self.pos0.pop(b[2], None)
                b[2], b[3], b[4], b[7] = kk, a, c, act
                self.pos0[kk] = b
            else:
                b[7] = None
        fut = [0] * (horizon + 1)
        brick = self.brick
        for d in range(1, horizon + 1):
            turn = self.T + d - 1
            # 滑行
            at = dict(self.pos0)
            moving = [b for b in self.bombs.values() if b[7]]
            target = {}
            cancel = set()
            for b in moving:
                dx, dy = DVEC[b[7]]
                a, c = b[3] + dx, b[4] + dy
                if not (0 <= a < W and 0 <= c < W):
                    continue
                kk = c * W + a
                if (self.steel >> kk) & 1 or (brick >> kk) & 1 or kk in at \
                        or (self.item_mask_cur >> kk) & 1 or kk == my_k \
                        or (self.occ_cur >> kk) & 1:
                    continue
                if kk in target:
                    cancel.add(kk)
                target[kk] = b
            for kk, b in target.items():
                if kk in cancel:
                    continue
                at.pop(b[2], None)
                b[2], b[3], b[4] = kk, kk % W, kk // W
                at[kk] = b
            for b in self.bombs.values():
                b[7] = None
            f, broken = self._flames_at(at, brick)
            # 移除爆炸弹、递减
            for b in list(self.bombs.values()):
                if b[5] <= 1:
                    at.pop(b[2], None)
                    del self.bombs[b[0]]
                    self.pos0.pop(b[2], None)
                else:
                    b[5] -= 1
            self.pos0 = at
            brick &= ~broken
            self.brick = brick
            # 道具烧毁 + 露出（隐藏道具未知，忽略露出）
            self.item_mask_cur &= ~f
            # 压墙
            ck = sim.crush_by_turn.get(turn)
            if ck:
                for k in ck:
                    m = 1 << k
                    self.steel |= m
                    self.walk &= ~m
                    self.floor &= ~m
                    brick &= ~m
                    self.occ_cur &= ~m
                    if k in self.pos0:
                        b = self.pos0.pop(k)
                        self.bombs.pop(b[0], None)
            fut[d] = f
        self.load(sv)
        return fut

    # -------------------------------------------------- 时间扩展逃生
    def survives(self, k0, d0, horizon, fut, block0=0, blockall=0):
        """从 k0 在时刻 d0 起能否活到 horizon。blockall: 始终不能站的格（如自己脚下的弹）。"""
        sim = self.sim
        W = self.W
        walk = self.walk & ~blockall
        if (1 << k0) & (fut[d0] if d0 <= horizon else 0):
            return False
        if d0 == 0 and ((1 << k0) & block0):
            return False
        frontier = 1 << k0
        for d in range(d0, horizon + 1):
            if d == horizon:
                return (frontier & ~fut[horizon] & walk) != 0
            nxt = 0
            for k in bits(frontier):
                nxt |= sim.nb[k]
            forbid = block0 if d == 0 else self.bomb_mask_at(d)
            frontier = nxt & walk & ~fut[d + 1] & ~forbid
            if frontier == 0:
                return False
        return False

    def bomb_mask_at(self, d):
        return 0

    def survive_from(self, k0, horizon, fut, d0=0, blockall=0, forbid0=0):
        """d0=0 表示"本回合我还没动"。forbid0: 本回合不能走进去的格（回合开始的炸弹）。"""
        sim = self.sim
        W = self.W
        walk = self.walk & ~blockall
        frontier = 1 << k0
        if frontier & (fut[0] if 0 in fut else 0):
            pass
        if frontier & forbid0:
            return False
        for d in range(max(1, d0), horizon + 1):
            if frontier & fut[d]:
                # 当前 frontier 全部要在此刻之前离开
                pass
            if d == horizon:
                return (frontier & ~fut[d] & walk) != 0
            nxt = 0
            for k in bits(frontier):
                nxt |= sim.nb[k]
            frontier = nxt & walk & ~fut[d + 1]
            if frontier == 0:
                return False
        return (frontier & walk) != 0

    # -------------------------------------------------- 攻击面
    def blast_cells(self, k, r, brick=None):
        """在 k 放弹（半径 r）的火焰格集合（考虑当前砖）。"""
        sim = self.sim
        W = self.W
        if brick is None:
            brick = self.brick
        steel = self.steel
        out = [k]
        x, y = k % W, k // W
        for d in range(4):
            dx, dy = DIRS[d]
            a, c = x + dx, y + dy
            for _ in range(r):
                if not (0 <= a < W and 0 <= c < W):
                    break
                kk = c * W + a
                if (steel >> kk) & 1:
                    break
                out.append(kk)
                if (brick >> kk) & 1:
                    break
                a += dx
                c += dy
        return out

    def blast_mask(self, k, r, brick=None):
        m = 0
        for kk in self.blast_cells(k, r, brick):
            m |= 1 << kk
        return m

    def new_bricks(self, k, r):
        m = 0
        for kk in self.blast_cells(k, r):
            if (self.brick >> kk) & 1:
                m |= 1 << kk
        return m

    def safe_bomb(self, k, H=5):
        """在 k 放一颗弹后自己能否逃出（k 之后不可再踏入）。"""
        c = self._sb.get(k)
        if c is not None:
            return c
        fut = self.project(k, H, extra_k=k, extra_r=self.radius)
        c = esc(self, k, fut, H, no_cell=(1 << k))
        self._sb[k] = c
        return c


# ------------------------------------------------------------------ 逃生/必杀
def esc(g, k0, fut, horizon, no_cell=0):
    """从 k0 出发（fut[1] 时刻起被检查），能否活到 horizon。"""
    sim = g.sim
    walk = g.sim.walk
    if (1 << k0) & fut[1]:
        return False
    fr = 1 << k0
    for d in range(1, horizon):
        nxt = 0
        for k in bits(fr):
            nxt |= sim.nb[k]
        fr = nxt & walk & ~fut[d + 1] & ~no_cell
        if fr == 0:
            return False
    return (fr & ~fut[horizon] & walk) != 0


def opp_dies(g, k0, fut, horizon):
    """对手从 k0 出发（本回合可移动一步），是否在 horizon 内必死。"""
    sim = g.sim
    fr = sim.nb[k0] & sim.walk
    if fr == 0:
        fr = 1 << k0
    for d in range(1, horizon + 1):
        fr &= ~fut[d]
        if fr == 0:
            return True
        if d == horizon:
            break
        nxt = 0
        for k in bits(fr):
            nxt |= sim.nb[k]
        fr = nxt & sim.walk
        if fr == 0:
            return True
    return False


# ------------------------------------------------------------------ 评分
def _crush_pen(g, k):
    t = g.sim.crush_turn_of.get((k % g.W, k // g.W))
    if t is None:
        return 0.0
    d = t - g.T
    if d <= 1:
        return 60.0
    if d <= 3:
        return 30.0
    if d <= 7:
        return 8.0
    if d <= 14:
        return 2.0
    return 0.0


def _item_score(g, k):
    W = g.W
    x, y = k % W, k // W
    my = g.my
    best = 0.0
    for ik, kind in g.items.items():
        ix, iy = ik % W, ik // W
        d = abs(ix - x) + abs(iy - y)
        if d > 9:
            continue
        if kind == "kick":
            v = 1.2 if not g.can_kick else 0.0
        elif kind == "fire":
            v = 5.0 if my["radius"] < g.max_radius else 0.2
        else:
            v = 4.2 if my["bomb_limit"] < 6 else 0.2
        s = v * 2.2 / (0.8 + d)
        if s > best:
            best = s
    return best


def _pot(g, k, endgame):
    """落点潜力（不含放弹本身）。"""
    sim = g.sim
    W = g.W
    x, y = k % W, k // W
    s = 0.0
    # 可炸砖潜力
    nb = 0
    for kk in g.blast_cells(k, g.radius):
        if (sim.brick >> kk) & 1:
            nb += 1
    s += 1.15 * nb
    # 道具
    s += _item_score(g, k)
    # 对手
    for pid in g.opp:
        pl = g.p.get(pid)
        if pl is None:
            continue
        ok = pl["y"] * W + pl["x"]
        d = abs(pl["x"] - x) + abs(pl["y"] - y)
        if d <= 1:
            s -= 3.0 if not endgame else 0.0
        elif d <= 3:
            s -= 0.6
        else:
            s += 0.25 * min(4, d - 3)
        # 对手在窄路则逼近
        if d <= 7:
            fr = sim.nb[ok] & sim.walk
            if nbits(fr) <= 2:
                s += 2.0
    # 自由度：能安全放弹的位置价值极高
    free = nbits(sim.nb[k] & sim.walk)
    s += 1.2 * free
    if free >= 3:
        s += 2.0
    if k != g.mk and g.can_bomb_now and not (1 << k) & g.pos0_mask:
        if g.safe_bomb(k):
            s += 7.0
    # 压墙
    s -= _crush_pen(g, k)
    # 中心偏好（前期），后期无所谓
    if g.T < g.sim.crush_min - 5:
        c = (W - 1) / 2.0
        s += 0.35 * (1.0 - (abs(x - c) + abs(y - c)) / (W - 1.0))
    return s


def _bomb_score(g, fut_bomb, H):
    """放弹的额外评分。"""
    sim = g.sim
    W = g.W
    s = 0.0
    nb = 0
    hit = 0
    cells = g.blast_cells(g.mk, g.radius)
    cs = set(cells)
    for kk in cells:
        if (sim.brick >> kk) & 1:
            nb += 1
    for pid in g.opp:
        pl = g.p.get(pid)
        if pl is None:
            continue
        ok = pl["y"] * W + pl["x"]
        if ok in cs:
            hit += 3.0
        else:
            m = sim.nb[ok]
            c = 0
            for kk in bits(m):
                if kk in cs:
                    c += 1
            hit += 0.55 * c
    s += 10.0 + 2.6 * nb + hit
    # 炸出的砖里可能有道具（期望）
    s += 0.5 * nb
    # 不要把弹放在马上会被压墙的格
    s -= 0.5 * _crush_pen(g, g.mk)
    return s


# ------------------------------------------------------------------ 主决策
_SIM = None
_SIM_KEY = None
_HIST = {}


def decide(state):
    try:
        return _decide(state)
    except Exception:
        return "stay"


def _decide(state):
    sim = Sim(state)
    g = G(state, sim)
    W = g.W
    H = 6
    mk = g.mk
    endgame = (g.nalive <= 2)
    scores = {}
    fut_base = g.project(mk, H)

    def dest(act):
        if act == "stay":
            return mk, None
        dx, dy = DVEC[act]
        x, y = g.mx + dx, g.myy + dy
        if not (0 <= x < W and 0 <= y < W):
            return None, None
        k = y * W + x
        if (sim.steel >> k) & 1 or (sim.brick >> k) & 1:
            return None, None
        b = g.pos0.get(k)
        if b is not None:
            return None, (b, act) if g.can_kick else None
        return k, None

    # ---- 移动候选
    for act in ("stay", "up", "down", "left", "right"):
        k, kick = dest(act)
        if kick is not None:
            continue
        if k is None:
            continue
        if not esc(g, k, fut_base, H):
            scores[act] = -500.0 + _pot(g, k, endgame) * 0.01
            continue
        scores[act] = _pot(g, k, endgame)

    # ---- 放弹
    under = g.pos0.get(mk) is not None
    can_place = (not under) and g.can_bomb
    best_kill = None
    if can_place:
        fut_bomb = g.project(mk, H, extra_k=mk, extra_r=g.radius)
        if esc(g, mk, fut_bomb, H, no_cell=(1 << mk)):
            s = _bomb_score(g, fut_bomb, H) + _pot(g, mk, endgame) * 0.35
            nk = 0
            for pid in g.opp:
                pl = g.p.get(pid)
                if pl is None:
                    continue
                ok = pl["y"] * W + pl["x"]
                if opp_dies(g, ok, fut_bomb, H):
                    nk += 1
            if nk:
                best_kill = ("bomb", nk)
                s += 400.0 * nk + (200.0 if endgame else 0.0)
            scores["bomb"] = s
        else:
            scores["bomb"] = -800.0

    # ---- 踢弹
    if g.can_kick:
        for act in DNAMES:
            k, kick = dest(act)
            if kick is None:
                continue
            b, a2 = kick
            fut_k = g.project(mk, H, kick=(list(b), a2))
            if not esc(g, mk, fut_k, H):
                scores[act] = max(scores.get(act, -900.0), -700.0)
                continue
            nk = 0
            for pid in g.opp:
                pl = g.p.get(pid)
                if pl is None:
                    continue
                ok = pl["y"] * W + pl["x"]
                if opp_dies(g, ok, fut_k, H):
                    nk += 1
            if nk:
                best_kill = (act, nk)
                sc = 380.0 * nk
            else:
                # 把弹踢向砖/对手方向有价值
                sc = 2.0
                dx, dy = DVEC[a2]
                a, c = b[3] + dx, b[4] + dy
                if 0 <= a < W and 0 <= c < W:
                    kk = c * W + a
                    for step in range(1, 5):
                        ax, ay = b[3] + dx * step, b[4] + dy * step
                        if not (0 <= ax < W and 0 <= ay < W):
                            break
                        k2 = ay * W + ax
                        if (sim.steel >> k2) & 1 or (sim.brick >> k2) & 1:
                            if (sim.brick >> k2) & 1:
                                sc += 1.5
                            break
                        for pid in g.opp:
                            pl = g.p.get(pid)
                            if pl and pl["x"] == ax and pl["y"] == ay:
                                sc += 2.5
            sc += _pot(g, mk, endgame) * 0.3
            if sc > scores.get(act, -1e9):
                scores[act] = sc

    if not scores:
        return "stay"
    if best_kill is not None:
        act, nk = best_kill
        if scores.get(act, -1e9) > -400:
            return act
        return act
    # 反停滞：连续不动就逼自己走（按座位独立记录）
    hst = _HIST.get(g.me)
    if hst is None:
        hst = _HIST[g.me] = {"turn": 0, "pos": None, "still": 0}
    if g.T == 1 or hst["turn"] >= g.T:
        hst["turn"] = g.T
        hst["pos"] = mk
        hst["still"] = 0
    else:
        if hst["pos"] == mk:
            hst["still"] = min(8, hst["still"] + 1)
        else:
            hst["still"] = 0
        hst["turn"] = g.T
        hst["pos"] = mk
    if hst["still"] >= 1 and scores.get("stay", -1e9) > -400:
        scores["stay"] -= 6.0 * hst["still"]
    if hst["still"] >= 1 and scores.get("bomb", -1e9) > -400:
        scores["bomb"] -= 2.0 * hst["still"]
    best = max(scores.values())
    cands = [a for a, s in scores.items() if s >= best - 1e-9]
    if best <= -400:
        # 都危险：挑活得最久的
        return _least_bad(g, fut_base, H)
    if len(cands) == 1:
        return cands[0]
    h = (g.T * 11 + mk * 7 + g.me * 3) % len(cands)
    return cands[h]


def _least_bad(g, fut, H):
    sim = g.sim
    W = g.W
    best = None
    for act in MOVES:
        if act == "bomb":
            continue
        if act == "stay":
            k = g.mk
        else:
            dx, dy = DVEC[act]
            x, y = g.mx + dx, g.myy + dy
            if not (0 <= x < W and 0 <= y < W):
                continue
            k = y * W + x
            if (sim.steel >> k) & 1 or (sim.brick >> k) & 1 or k in g.pos0:
                continue
        surv = 0
        for d in range(1, H + 1):
            if (fut[d] >> k) & 1:
                break
            surv += 1
        sc = surv * 20 + nbits(sim.nb[k] & sim.walk)
        if best is None or sc > best[0]:
            best = (sc, act)
    return best[1] if best else "stay"
