"""Opus bomber: survival-first simulator bot.

Each turn: simulate all known bombs (fuse, chains, slides, crush) forward,
check for every candidate action whether a survivable path exists — also
against the worst case where nearby opponents drop a bomb right now — and
among safe actions pick the one with the best goal utility (items, bricks,
traps, late-crush real estate).
"""
from collections import Counter, deque

D = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
MOVES = ("up", "down", "left", "right")
BIG = 10 ** 9
DEBUG = False
H = 9

_cache = {}


def spiral(w):
    cells = []
    lo, hi = 0, w - 1
    while lo <= hi:
        cells.extend((x, lo) for x in range(lo, hi + 1))
        cells.extend((hi, y) for y in range(lo + 1, hi + 1))
        if lo < hi:
            cells.extend((x, hi) for x in range(hi - 1, lo - 1, -1))
            cells.extend((lo, y) for y in range(hi - 1, lo, -1))
        lo, hi = lo + 1, hi - 1
    return cells


def crush_schedule(state):
    key = (state["width"], state["crush_rotation"], state["crush_start"])
    if _cache.get("key") == key:
        return _cache["ct"], _cache["sched"]
    w = state["width"]
    crushed = {tuple(c) for c in state["crushed"]}
    grid = state["grid"]
    sp = spiral(w)
    for _ in range(state["crush_rotation"]):
        sp = [(w - 1 - y, x) for x, y in sp]
    sched = [(x, y) for x, y in sp if not (grid[y][x] == "@" and (x, y) not in crushed)]
    cs = state["crush_start"]
    ct = {c: cs + i for i, c in enumerate(sched)}
    # sanity check against the public preview
    for item in state.get("next_crush", []):
        c = (item["x"], item["y"])
        if ct.get(c) != item["turn"]:
            ct[c] = item["turn"]
    _cache.update(key=key, ct=ct, sched=sched)
    return ct, sched


class World:
    pass


def simulate(W, extra):
    """extra: list of (x,y,radius) bombs placed at step 0.
    Returns fires[k], bombs_before[k], bricks_before[k] for k in 0..H."""
    T, ct = W.T, W.ct
    bl = [[b["x"], b["y"], b["fuse"], b["radius"], b["direction"], False] for b in W.bombs]
    occupied = {(b[0], b[1]) for b in bl}
    for (x, y, r) in extra:
        if (x, y) not in occupied:
            bl.append([x, y, W.fuse, r, None, True])
    bricks = W.bricks
    walls = W.walls
    blockers = W.pcells | W.items_set
    fires, bombs_before, bricks_before = [], [{(b["x"], b["y"]) for b in W.bombs}], [bricks]
    broken_all = set()
    for k in range(H):
        t = T + k
        cells = {(b[0], b[1]) for b in bl}
        targets = {}
        for i, b in enumerate(bl):
            if b[4]:
                dx, dy = D[b[4]]
                q = (b[0] + dx, b[1] + dy)
                if q in walls or q in bricks or q in cells or q in blockers or ct.get(q, BIG) < t:
                    b[4] = None
                else:
                    targets[i] = q
        if targets:
            cnt = Counter(targets.values())
            for i, q in targets.items():
                if cnt[q] == 1:
                    bl[i][0], bl[i][1] = q
                else:
                    bl[i][4] = None
        for b in bl:
            if b[5]:
                b[5] = False
            else:
                b[2] -= 1
        pos = {}
        for i, b in enumerate(bl):
            pos[(b[0], b[1])] = i
        pending = [i for i, b in enumerate(bl) if b[2] <= 0]
        fire = set()
        det = set()
        broken = set()
        while pending:
            i = pending.pop()
            if i in det:
                continue
            det.add(i)
            b = bl[i]
            fire.add((b[0], b[1]))
            r = b[3]
            for dx, dy in D.values():
                x, y = b[0], b[1]
                for _ in range(r):
                    x += dx
                    y += dy
                    q = (x, y)
                    if q in walls or ct.get(q, BIG) < t:
                        break
                    fire.add(q)
                    if q in bricks:
                        broken.add(q)
                        break
                    j = pos.get(q)
                    if j is not None:
                        if j not in det:
                            pending.append(j)
                        break
        if det:
            bl = [b for i, b in enumerate(bl) if i not in det]
        if broken:
            bricks = bricks - broken
            broken_all |= broken
        if t >= W.cs:
            idx = t - W.cs
            if idx < len(W.sched):
                c = W.sched[idx]
                bl = [b for b in bl if (b[0], b[1]) != c]
        fires.append(fire)
        bombs_before.append({(b[0], b[1]) for b in bl})
        bricks_before.append(bricks)
    return fires, bombs_before, bricks_before, broken_all


def nbrs(c):
    x, y = c
    return ((x, y - 1), (x, y + 1), (x - 1, y), (x + 1, y))


def reach(W, S, R, k0, block0=frozenset(), blockall=frozenset()):
    """R: set of positions before step k0. Returns list of reachable set sizes
    per step and final set."""
    fires, bb, kb = S[0], S[1], S[2]
    T, ct, walls = W.T, W.ct, W.walls
    depth = k0
    for k in range(k0, H):
        fire = fires[k]
        bombs = bb[k]
        bricks = kb[k]
        t = T + k
        nr = set()
        for r in R:
            if r not in fire and ct.get(r, BIG) > t:
                nr.add(r)
            for n in nbrs(r):
                if n in nr or n in walls or n in bricks or n in bombs or n in fire:
                    continue
                if ct.get(n, BIG) <= t:
                    continue
                if (k == k0 and n in block0) or n in blockall:
                    continue
                nr.add(n)
        R = nr
        if not R:
            return depth, R
        depth = k + 1
    return depth, R


def step0_ok(W, S, p):
    return p not in S[0][0] and W.ct.get(p, BIG) > W.T


def blast_cells(W, c, r, bricks, bombs):
    hit_bricks = []
    cells = [c]
    for dx, dy in D.values():
        x, y = c
        for _ in range(r):
            x += dx
            y += dy
            q = (x, y)
            if q in W.walls:
                break
            cells.append(q)
            if q in bricks:
                hit_bricks.append(q)
                break
            if q in bombs:
                break
    return cells, hit_bricks


def decide(state):
    try:
        return _decide(state)
    except Exception:
        return "stay"


def _decide(state):
    W = World()
    W.T = state["turn"]
    w, h = state["width"], state["height"]
    W.w, W.h = w, h
    W.fuse = state.get("bomb_fuse", 3)
    W.cs = state["crush_start"]
    W.ct, W.sched = crush_schedule(state)
    grid = state["grid"]
    walls, bricks = set(), set()
    for y in range(h):
        row = grid[y]
        for x in range(w):
            ch = row[x]
            if ch == "@":
                walls.add((x, y))
            elif ch == "#":
                bricks.add((x, y))
    for x in range(-1, w + 1):
        walls.add((x, -1))
        walls.add((x, h))
    for y in range(-1, h + 1):
        walls.add((-1, y))
        walls.add((w, y))
    W.walls, W.bricks = walls, frozenset(bricks)
    W.bombs = state["bombs"]
    items = {(it["x"], it["y"]): it["kind"] for it in state["items"]}
    W.items_set = set(items)
    me = None
    opps = []
    for p in state["players"]:
        if p["id"] == state["you"]:
            me = p
        else:
            opps.append(p)
    if me is None:
        return "stay"
    W.pcells = {(p["x"], p["y"]) for p in state["players"]}
    my = (me["x"], me["y"])
    T = W.T
    ct = W.ct
    bombcells = {(b["x"], b["y"]) for b in W.bombs}
    opp_cells = {(p["x"], p["y"]) for p in opps}

    # Hypothetical opponent bombs (they drop one right now)
    threats = []
    for p in opps:
        c = (p["x"], p["y"])
        if p["can_bomb"] and c not in bombcells and abs(c[0] - my[0]) + abs(c[1] - my[1]) <= p["radius"] + 4:
            threats.append((c[0], c[1], p["radius"]))

    can_bomb = me["can_bomb"] and my not in bombcells
    myr = me["radius"]

    S_base = simulate(W, [])
    S_worst = simulate(W, threats) if threats else S_base
    if can_bomb:
        S_bb = simulate(W, [(my[0], my[1], myr)])
        S_bw = simulate(W, [(my[0], my[1], myr)] + threats) if threats else S_bb
    # candidate actions -> position after step 0
    cands = []
    for a in MOVES:
        dx, dy = D[a]
        q = (my[0] + dx, my[1] + dy)
        if q in walls or q in bricks or q in bombcells or q in W.pcells:
            continue
        cands.append((a, q))
    cands.append(("stay", my))
    if can_bomb:
        cands.append(("bomb", my))

    paranoid = set(opp_cells)
    for oc in opp_cells:
        for n in nbrs(oc):
            paranoid.add(n)
    safety = {}
    for a, q in cands:
        if a == "bomb":
            sb, sw = S_bb, S_bw
        else:
            sb, sw = S_base, S_worst
        res = []
        for S, ba in ((sw, paranoid), (sw, opp_cells), (sb, frozenset())):
            if not step0_ok(W, S, q):
                res.append((0, 0))
                continue
            d, R = reach(W, S, {q}, 1, frozenset(), ba)
            res.append((d, len(R)))
        dp, np_ = res[0]
        dw, nw = res[1]
        db, nb = res[2]
        if dp >= H:
            tier = 4
        elif dw >= H:
            tier = 3
        elif db >= H:
            tier = 2
        else:
            tier = 0
        if a == "bomb" and tier < 3:
            tier = min(tier, 1)
        safety[a] = [tier, db, nb, nw]
    # a move into a cell another player may also step into can fail (we stay)
    stay_safe = safety["stay"][1] >= H
    for a, q in cands:
        if a in D and not stay_safe:
            for oc in opp_cells:
                if abs(oc[0] - q[0]) + abs(oc[1] - q[1]) == 1:
                    if safety[a][0] > 0:
                        safety[a][0] -= 1
                    break

    # ---- utilities ----
    broken_soon = S_base[3]
    live_bricks = bricks - broken_soon
    n_bricks = len(live_bricks)
    nopp = len(opps)
    fire_soon = set()
    for f in S_base[0][:4]:
        fire_soon |= f

    def item_value(kind):
        if kind == "fire":
            return 3.5 if myr < 4 else (2.0 if myr < 6 else 0.4)
        if kind == "bomb":
            lim = me["bomb_limit"]
            return 4.0 if lim < 3 else (2.0 if lim < 5 else 0.4)
        return 1.5 if not me["can_kick"] else 0.2

    late = T >= W.cs - 25
    remaining = [c for c in W.sched[max(0, T - W.cs):]]
    rem_n = max(1, len(remaining))
    attack_w = 0.6 if n_bricks > 8 else 1.6

    # long-range survival map vs. the crush schedule (bricks cost ~4 turns)
    fs = None
    fmax = 0
    if T + 70 >= W.cs:
        L = 70
        cellsall = [(x, y) for y in range(h) for x in range(w) if (x, y) not in walls and (x, y) not in opp_cells]
        fs = [None] * (L + 1)
        fs[L] = {c: L for c in cellsall if ct.get(c, BIG) > T + L}
        for t in range(L - 1, -1, -1):
            nxt = fs[t + 1]
            far = fs[t + 4] if t + 4 <= L else None
            cur = {}
            tt = T + t
            for c in cellsall:
                if ct.get(c, BIG) <= tt:
                    continue
                best = nxt.get(c, t)
                for n in nbrs(c):
                    if n in live_bricks:
                        if far is not None:
                            v = far.get(n)
                            if v is not None and v > best:
                                best = v
                    else:
                        v = nxt.get(n)
                        if v is not None and v > best:
                            best = v
                cur[c] = best
            fs[t] = cur
        fmax = max(fs[0].values()) if fs[0] else 0

    def static_escape(c, cells):
        seen = {c}
        frontier = [c]
        for d in range(W.fuse):
            nf = []
            for x in frontier:
                for n in nbrs(x):
                    if n in seen or n in walls or n in bricks or n in bombcells or n in opp_cells:
                        continue
                    if ct.get(n, BIG) <= T + d + 6:
                        continue
                    if n not in cells:
                        return True
                    seen.add(n)
                    nf.append(n)
            frontier = nf
        return False

    util_cache = {}

    def util(c, dist):
        v = util_cache.get(c)
        if v is None:
            v = 0.0
            kind = items.get(c)
            if kind:
                v += item_value(kind)
            if c not in bombcells:
                cells, hb = blast_cells(W, c, myr, live_bricks, bombcells)
                if hb and not static_escape(c, set(cells)):
                    hb = ()
                v += 1.0 * len(hb)
                for p in opps:
                    if (p["x"], p["y"]) in cells and (p["x"], p["y"]) != c:
                        v += attack_w
            util_cache[c] = v
        cti = ct.get(c, BIG)
        if cti - T - dist < 6:
            v -= 6.0
        if fs is not None:
            f = fs[min(dist, len(fs) - 1)].get(c, dist)
            deficit = fmax - f
            if deficit > 0:
                v -= min(14.0, 1.5 * deficit)
        return v

    def bfs_value(start):
        if start in fire_soon:
            pen = 0.0
        else:
            pen = 0.0
        best = util(start, 0)
        seen = {start: 0}
        dq = deque([start])
        while dq:
            c = dq.popleft()
            d = seen[c]
            if d >= 14:
                continue
            for n in nbrs(c):
                if n in seen or n in walls or n in bricks or n in bombcells or n in opp_cells:
                    continue
                if ct.get(n, BIG) <= T + d + 1:
                    continue
                seen[n] = d + 1
                val = util(n, d + 1) * (0.82 ** (d + 1))
                if val > best:
                    best = val
                dq.append(n)
        # mobility bonus
        return best - pen + 0.01 * min(len(seen), 30)

    # trap evaluation for bomb action
    def trap_bonus():
        bonus = 0.0
        for p in opps:
            oc = (p["x"], p["y"])
            if abs(oc[0] - my[0]) + abs(oc[1] - my[1]) > myr + 3:
                continue
            d0, _ = reach(W, S_base, {oc}, 0, frozenset({my}))
            if d0 < H:
                continue  # already doomed anyway
            d1, R1 = reach(W, S_bb, {oc}, 0, frozenset({my}))
            factor = 0.5 if p["can_kick"] else 1.0
            if d1 < H:
                bonus += 12.0 * factor
            elif len(R1) <= 2:
                bonus += 2.0 * factor
            elif len(R1) <= 5:
                bonus += 0.5 * factor
        return bonus

    def mobility(q):
        seen = {q}
        frontier = [q]
        for _ in range(4):
            nf = []
            for c in frontier:
                for n in nbrs(c):
                    if n in seen or n in walls or n in bricks or n in bombcells or n in opp_cells:
                        continue
                    if ct.get(n, BIG) <= T + 5:
                        continue
                    seen.add(n)
                    nf.append(n)
            frontier = nf
        return len(seen)

    near_opp = min([abs(oc[0] - my[0]) + abs(oc[1] - my[1]) for oc in opp_cells] or [99])

    scores = {}
    for a, q in cands:
        tier, db, nb, nw = safety[a]
        if a == "bomb":
            cells, hb = blast_cells(W, my, myr, live_bricks, bombcells)
            val = 1.2 * len(hb)
            for p in opps:
                if (p["x"], p["y"]) in cells:
                    val += 0.5 * attack_w
            val += trap_bonus()
            if val < 0.9:
                val = -5.0
            # after bombing we still go for things; small mobility consideration
            val += 0.02 * min(nb, 10)
        else:
            val = bfs_value(q)
            slack = ct.get(q, BIG) - T
            if slack <= 6:
                val -= 2.0 * (7 - slack)
            if a == "stay":
                val -= 0.05
            val += 0.03 * min(nb, 10) + 0.02 * min(nw, 10)
        if near_opp <= 5 and len(opps) == 1:
            mob = mobility(q)
            if mob < 8:
                val -= (8 - mob) * 0.6
        scores[a] = (tier, db if tier == 0 else 0, val)

    best = max(scores, key=lambda a: scores[a])
    if DEBUG:
        print(T, my, {a: (safety[a], scores[a]) for a in scores})
    return best
