"""Bomber II: exact blast simulation -> space-time BFS -> greedy objective search."""
from collections import deque, Counter

D4 = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
MOVES = ("up", "down", "left", "right")
S5 = ((0, 0), (0, -1), (0, 1), (-1, 0), (1, 0))

_cache = {}

def _crush_maps(w, rot, start):
    key = (w, rot, start)
    got = _cache.get(key)
    if got is not None:
        return got
    h = w
    cells = []
    lo, hi = 0, w - 1
    while lo <= hi:
        for x in range(lo, hi + 1):
            cells.append((x, lo))
        if hi > lo:
            for y in range(lo + 1, hi + 1):
                cells.append((hi, y))
            for x in range(hi - 1, lo - 1, -1):
                cells.append((x, hi))
            if hi - 1 > lo:
                for y in range(hi - 1, lo, -1):
                    cells.append((lo, y))
        lo += 1
        hi -= 1
    if rot == 1:
        cells = [(y, w - 1 - x) for (x, y) in cells]
    elif rot == 2:
        cells = [(w - 1 - x, w - 1 - y) for (x, y) in cells]
    elif rot == 3:
        cells = [(w - 1 - y, x) for (x, y) in cells]
    cellmap = {}
    atmap = {}
    for i, q in enumerate(cells):
        t = start + i
        cellmap[q] = t
        atmap[t] = q
    _cache[key] = (cellmap, atmap)
    return cellmap, atmap

def _rays(x, y, rad, grid, w, h, bmap):
    """Cells a bomb at (x,y) would engulf, plus chained bomb cells."""
    out = [(x, y)]
    chained = []
    for dx, dy in D4.values():
        for k in range(1, rad + 1):
            q = (x + dx * k, y + dy * k)
            if not (0 <= q[0] < w and 0 <= q[1] < h):
                break
            c = grid[q[1]][q[0]]
            if c == "@":
                break
            if c == "#":
                out.append(q)
                break
            if q in bmap:
                chained.append(bmap[q])
                out.append(q)
                break
            out.append(q)
    return out, chained

def _danger(grid, bombs, itemset, T, H, w, h, cellmap, atmap):
    """Returns (danger dict (x,y)->set of abs turns with flame, occ dict t->set of bomb cells)."""
    end = T + H
    danger = {}
    occ = {t: set() for t in range(T + 1, end + 1)}
    if not bombs:
        return danger, occ
    n = len(bombs)
    pos = [(b["x"], b["y"]) for b in bombs]
    rad = [b["radius"] for b in bombs]
    fuse = [T + b["fuse"] for b in bombs]
    direc = [b["direction"] for b in bombs]
    alive = [True] * n
    expl = [None] * n
    bmap = {pos[i]: i for i in range(n)}

    def chain(i, t):
        expl[i] = t
        cells, ch = _rays(pos[i][0], pos[i][1], rad[i], grid, w, h, bmap)
        for c in cells:
            s = danger.get(c)
            if s is None:
                danger[c] = {t}
            else:
                s.add(t)
        for j in ch:
            if alive[j] and (expl[j] is None or expl[j] > t):
                chain(j, t)

    for t in range(T + 1, end + 1):
        # sliding
        nxt = {}
        cnt = Counter()
        for i in range(n):
            if not alive[i] or direc[i] is None:
                continue
            dx, dy = D4[direc[i]]
            q = (pos[i][0] + dx, pos[i][1] + dy)
            if not (0 <= q[0] < w and 0 <= q[1] < h):
                continue
            c = grid[q[1]][q[0]]
            if c == "@" or c == "#" or q in bmap or q in itemset:
                continue
            ct = cellmap.get(q)
            if ct is not None and ct < t:
                continue
            nxt[i] = q
            cnt[q] += 1
        for i, q in nxt.items():
            if cnt[q] == 1:
                bmap.pop(pos[i], None)
                pos[i] = q
                bmap[q] = i
            else:
                direc[i] = None
        # fuse expiry + chains (id order)
        changed = True
        while changed:
            changed = False
            for i in range(n):
                if alive[i] and expl[i] is None and fuse[i] <= t:
                    alive[i] = False
                    bmap.pop(pos[i], None)
                    chain(i, t)
                    changed = True
        for i in range(n):
            if alive[i]:
                occ[t].add(pos[i])
        # crush
        q = atmap.get(t)
        if q is not None and q in bmap:
            i = bmap[q]
            if expl[i] is None:
                expl[i] = -1
            alive[i] = False
            bmap.pop(q, None)
    return danger, occ

def _reach(starts, T, H, w, h, grid, occ, danger, cellmap, blocked0):
    out = {}
    seen = set()
    dq = deque()
    for label, x, y, moved in starts:
        if moved and (x, y) in blocked0:
            continue
        if not (0 <= x < w and 0 <= y < h):
            continue
        c = grid[y][x]
        if c == "@" or c == "#" or (x, y) in occ.get(T + 1, ()):
            continue
        dd = danger.get((x, y))
        if dd and T + 1 in dd:
            continue
        ct = cellmap.get((x, y))
        if ct is not None and ct <= T + 1:
            continue
        key = (T + 1, x, y)
        seen.add((label,) + key)
        out.setdefault(label, set()).add(key)
        dq.append((label, T + 1, x, y))
    if not dq:
        return out
    t_end = T + H
    while dq:
        label, t, x, y = dq.popleft()
        nt = t + 1
        if nt > t_end:
            continue
        for dx, dy in S5:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            c = grid[ny][nx]
            if c == "@" or c == "#":
                continue
            if (nx, ny) in occ.get(nt, ()):
                continue
            dd = danger.get((nx, ny))
            if dd and nt in dd:
                continue
            ct = cellmap.get((nx, ny))
            if ct is not None and ct <= nt:
                continue
            key = (nt, nx, ny)
            sk = (label,) + key
            if sk in seen:
                continue
            seen.add(sk)
            out[label].add(key)
            dq.append((label, nt, nx, ny))
    return out


def _blast_cells(x, y, rad, grid, w, h):
    out = [(x, y)]
    for dx, dy in D4.values():
        for k in range(1, rad + 1):
            q = (x + dx * k, y + dy * k)
            if not (0 <= q[0] < w and 0 <= q[1] < h):
                break
            c = grid[q[1]][q[0]]
            if c == "@":
                break
            out.append(q)
            if c == "#":
                break
    return out

def _item_val(kind, me):
    if kind == "fire":
        return 6.0 if me["radius"] < 3 else (4.0 if me["radius"] < 5 else 1.5)
    if kind == "bomb":
        return 6.0 if me["bomb_limit"] < 2 else (4.0 if me["bomb_limit"] < 4 else 1.5)
    return 3.0 if not me["can_kick"] else 0.5

def _decide(state):
    T = state["turn"]
    w, h = state["width"], state["height"]
    grid = state["grid"]
    you = state["you"]
    players = state["players"]
    me = None
    for p in players:
        if p["id"] == you:
            me = p
            break
    if me is None:
        return "stay"
    others = [p for p in players if p["id"] != you]
    bombs = state["bombs"]
    cellmap, atmap = _crush_maps(w, state["crush_rotation"], state["crush_start"])
    items = state["items"]
    items_val = {(it["x"], it["y"]): _item_val(it["kind"], me) for it in items}

    ld = 0
    if bombs:
        ld = T + max(b["fuse"] for b in bombs) + 5
    lc = T - 1
    for c in state.get("next_crush") or ():
        if c["turn"] > lc:
            lc = c["turn"]
    need = max(12, ld - T + 3, lc - T + 3)
    H = min(need, 40, max(1, state["max_turns"] - T + 1))
    danger, occ = _danger(grid, bombs, set(items_val), T, H, w, h, cellmap, atmap)

    x0, y0 = me["x"], me["y"]
    blocked0 = {(p["x"], p["y"]) for p in others}
    bset = {(b["x"], b["y"]) for b in bombs}

    # static floor distance from me (for objective search)
    dist = {(x0, y0): 0}
    dq = deque([(x0, y0)])
    while dq:
        x, y = dq.popleft()
        d = dist[(x, y)]
        for dx, dy in D4.values():
            nx, ny = x + dx, y + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            if (nx, ny) in dist:
                continue
            c = grid[ny][nx]
            if c == "@" or c == "#" or (nx, ny) in bset:
                continue
            dist[(nx, ny)] = d + 1
            dq.append((nx, ny))

    starts = [("stay", x0, y0, False)] + [(a, x0 + D4[a][0], y0 + D4[a][1], True) for a in MOVES]
    reach = _reach(starts, T, H, w, h, grid, occ, danger, cellmap, blocked0)
    if not bombs:
        reach.pop("stay", None)

    # objectives: (priority, cell)
    objectives = []
    for c, v in items_val.items():
        objectives.append((2, c))
    if me["can_bomb"] and me["active_bombs"] == 0:
        for (x, y), d in dist.items():
            if d == 0:
                continue
            # useful bomb site: adjacent brick or opponent in blast
            adjb = 0
            for dx, dy in D4.values():
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and grid[ny][nx] == "#":
                    adjb += 1
            opp_hit = any((o["x"], o["y"]) in _blast_cells(x, y, me["radius"], grid, w, h) for o in others)
            if adjb or opp_hit:
                pri = 1 if opp_hit else 3
                objectives.append((pri, (x, y)))
    # safe roaming fallback: farthest reachable cell
    far = None
    for (x, y), d in dist.items():
        if d and (far is None or d > dist[far]):
            far = (x, y)
    if far:
        objectives.append((4, far))

    def nodes_for(a):
        return reach.get(a) or set()

    best = None
    best_score = -1e18
    for a in ("stay",) + MOVES:
        nodes = nodes_for(a)
        if not nodes:
            continue
        max_t = max(n[0] for n in nodes)
        if max_t < T + H:
            continue
        deg = len(nodes)
        score = deg * 0.15
        # objective achieved?
        for pri, c in objectives:
            hit = None
            for n in nodes:
                if (n[1], n[2]) == c:
                    if hit is None or n[0] < hit:
                        hit = n[0]
            if hit is not None:
                score += 1000.0 / (pri * (hit - T + 3))
                break
        # avoid lingering on threat lines of others
        pen = 0
        for n in nodes:
            if n[0] <= T + 2:
                continue
            for o in others:
                if o["can_bomb"]:
                    if o["x"] == n[1] or o["y"] == n[2]:
                        pen += 1
                        break
            if pen > 8:
                break
        score -= 0.6 * pen
        if score > best_score:
            best_score = score
            best = a
    if best is None:
        return "stay"

    # bomb now if it beats moving and kills/traps or breaks bricks
    if me["can_bomb"]:
        blast = set(_blast_cells(x0, y0, me["radius"], grid, w, h))
        chains = [b for b in bombs if (b["x"], b["y"]) in blast]
        expl_times = set()
        for ch in chains:
            for i, tt in enumerate(range(T + 1, T + ch["fuse"] + 1)):
                expl_times.add(tt)
        if chains:
            min_t = min(expl_times)
        else:
            min_t = T + state.get("bomb_fuse", 3) + 1
        # escape: is there a node that leaves blast before min_t and survives?
        escaped = False
        for a in ("stay",) + MOVES:
            for n in reach.get(a, ()):
                if (n[1], n[2]) not in blast and n[0] <= min_t:
                    # and can stay safe afterwards
                    dd = danger.get((n[1], n[2]))
                    if dd and any(tt >= n[0] for tt in dd):
                        continue
                    escaped = True
                    break
            if escaped:
                break
        bricks_here = sum(1 for c in blast if grid[c[1]][c[0]] == "#")
        kill = any((o["x"], o["y"]) in blast for o in others)
        if escaped and (kill or bricks_here or chains):
            bscore = (100.0 if kill else 0) + 8.0 * bricks_here + 2.0 * len(chains)
            # only if immediate move option isn't strictly better objective
            if best_score < bscore + 5.0 or best_score < 0:
                return "bomb"
    return best

def decide(state):
    try:
        return _decide(state)
    except Exception:
        return "stay"
