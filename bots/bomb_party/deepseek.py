"""炸弹派对 bot —— 精确时间线 + 时间展开安全集 DP + 启发式评估。

1. 压墙时间表：按 crush_rotation 重建螺旋路径，得到每格落墙回合（未来全知）。
2. 危险时间线：从当前炸弹引信出发逐回合模拟爆炸连锁（同回合地形快照、炸砖露路、
   压墙消除炸弹），得到每回合的火焰格与落墙格，以及"我这颗新弹能覆盖哪些格"。
3. 时间展开 DP：从视野末端往回推，得到"此刻站在格 c 能一路活到第 h 回合"的最大 h。
   这是硬约束——任何会缩短寿命的走法都排在后面。
4. 6 个候选动作（上/下/左/右/放弹/不动）按 生存 > 捡道具 > 炸砖挖宝 > 炸人 排序，
   后期随压墙推进向高生存区收拢。
"""

DIRS = ((0, -1), (0, 1), (-1, 0), (1, 0))
DNAME = {'up': (0, -1), 'down': (0, 1), 'left': (-1, 0), 'right': (1, 0)}
HORIZONS = (1, 2, 3, 4, 5, 6, 8, 10, 13, 16, 20, 25, 30, 36)
IVAL = {'fire': 14.0, 'bomb': 14.0, 'kick': 22.0}
INF = 1 << 20
CACHE = {}
PREV = {}


# ------------------------------------------------------------------ 静态几何
def _masks(W, HH):
    key = ('m', W, HH)
    v = CACHE.get(key)
    if v is not None:
        return v
    FULL = (1 << (W * HH)) - 1
    NXW = 0
    NX0 = 0
    for y in range(HH):
        NXW |= 1 << (y * W + W - 1)
        NX0 |= 1 << (y * W)
    v = (FULL, NX0, NXW)
    CACHE[key] = v
    return v


def _crush(W, rot, cs):
    """返回 (落墙表 cell->turn, 路径长度)。"""
    key = ('c', W, rot, cs)
    v = CACHE.get(key)
    if v is not None:
        return v
    cells = []
    lo, hi = 0, W - 1
    # 先造出整条顺时针螺旋（外圈到中心），再按旋转量旋转
    while lo <= hi:
        cells.extend((x, lo) for x in range(lo, hi + 1))
        cells.extend((hi, y) for y in range(lo + 1, hi + 1))
        if hi > lo:
            cells.extend((x, hi) for x in range(hi - 1, lo - 1, -1))
            cells.extend((lo, y) for y in range(hi - 1, lo, -1))
        lo, hi = lo + 1, hi - 1
    table = {}
    n = 0
    for x, y in cells:
        if x in (0, W - 1) or y in (0, W - 1) or (x % 2 == 0 and y % 2 == 0):
            continue
        for _ in range(rot):
            x, y = W - 1 - y, x
        table[(x, y)] = cs + n
        n += 1
    v = (table, n)
    CACHE[key] = v
    return v


def _expand(m, W, FULL, NX0, NXW):
    return ((m & ~NX0) >> 1) | ((m & ~NXW) << 1) | (m >> W) | ((m << W) & FULL)


# ------------------------------------------------------------------ 危险时间线
def _build(turn, H, grid, bombs, extra, fuse, crush_at, W, HH):
    """逐回合精确模拟（爆炸 → 炸砖 → 压墙）。返回 (floor, dead, blast)。"""
    terr = [list(r) for r in grid]
    live = []
    for b in bombs:
        live.append([b['x'], b['y'], b['radius'], turn + b['fuse'] - 1])
    newid = -1
    if extra is not None:
        live.append([extra[0], extra[1], extra[2], turn + fuse])
        newid = len(live) - 1
    newtime = turn + fuse if extra is not None else -1
    floor, dead, fl, blk = {}, {}, {}, {}
    blast = 0
    for t in range(turn, turn + H + 1):
        # 回合 t 开始时的可行走地形（本回合还没落墙）
        fm = 0
        for y in range(HH):
            row = terr[y]
            base = y * W
            for x in range(W):
                if row[x] == '.':
                    fm |= 1 << (base + x)
        bombat = {}
        bm = 0
        for i, b in enumerate(live):
            bombat[(b[0], b[1])] = i
            bm |= 1 << (b[1] * W + b[0])
        floor[t] = fm & ~bm
        blk[t] = bm
        exploded = set()
        stack = []
        for i, b in enumerate(live):
            if b[3] == t:
                exploded.add(i)
                stack.append(i)
        ext = 0
        brk = []
        mine = set()
        if t == newtime:
            mine.add(newid)
        while stack:
            i = stack.pop()
            b = live[i]
            ext |= 1 << (b[1] * W + b[0])
            for dx, dy in DIRS:
                x, y = b[0] + dx, b[1] + dy
                for _ in range(b[2]):
                    if not (0 <= x < W and 0 <= y < HH):
                        break
                    ch = terr[y][x]
                    if ch == '@':
                        break
                    ext |= 1 << (y * W + x)
                    if ch == '#':
                        brk.append((x, y))
                        break
                    j = bombat.get((x, y))
                    if j is not None:
                        if j not in exploded:
                            exploded.add(j)
                            stack.append(j)
                            if i in mine:
                                mine.add(j)
                        break
                    x += dx
                    y += dy
        if newid in mine:
            blast |= ext
        for (x, y) in brk:
            terr[y][x] = '.'
        if exploded:
            live = [b for i, b in enumerate(live) if i not in exploded]
        # 压墙：本回合落下的格
        cm = 0
        hit = False
        for (x, y), ct in crush_at.items():
            if ct == t and terr[y][x] == '.':
                cm |= 1 << (y * W + x)
                hit = True
        if hit:
            for (x, y), ct in crush_at.items():
                if ct == t and terr[y][x] == '.':
                    terr[y][x] = '@'
                    live = [b for b in live if (b[0], b[1]) != (x, y)]
        dead[t] = ext | cm
        fl[t] = ext
    return floor, dead, blast, fl, blk


def _safe(floor, dead, turn, W, HH, H):
    FULL, NX0, NXW = _masks(W, HH)
    out = []
    for h in HORIZONS:
        if h > H:
            break
        t = turn + h
        S = floor[t] & ~dead[t]
        for k in range(h - 1, -1, -1):
            t = turn + k
            S = floor[t] & ~dead[t] & (S | _expand(S, W, FULL, NX0, NXW))
        out.append(S)
    return out


def _bfs_multi(W, HH, grid, goals):
    dist = [INF] * (W * HH)
    q = []
    for g in goals:
        if grid[g // W][g % W] == '.' and dist[g] == INF:
            dist[g] = 0
            q.append(g)
    head = 0
    while head < len(q):
        i = q[head]
        head += 1
        d = dist[i] + 1
        x, y = i % W, i // W
        for dx, dy in DIRS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < W and 0 <= ny < HH):
                continue
            if grid[ny][nx] != '.':
                continue
            j = ny * W + nx
            if d < dist[j]:
                dist[j] = d
                q.append(j)
    return dist


def _bfs(W, HH, grid, src):
    dist = [INF] * (W * HH)
    dist[src] = 0
    q = [src]
    head = 0
    while head < len(q):
        i = q[head]
        head += 1
        d = dist[i] + 1
        x, y = i % W, i // W
        for dx, dy in DIRS:
            nx, ny = x + dx, y + dy
            if not (0 <= nx < W and 0 <= ny < HH):
                continue
            if grid[ny][nx] != '.':
                continue
            j = ny * W + nx
            if d < dist[j]:
                dist[j] = d
                q.append(j)
    return dist


def decide(state):
    try:
        return _decide(state)
    except Exception:
        return 'stay'


def _decide(state):
    W = state['width']
    HH = state['height']
    grid = state['grid']
    turn = state['turn']
    you = state['you']
    players = state['players']
    bombs = state['bombs']
    fuse = state['bomb_fuse']
    cs = state['crush_start']
    maxr = state.get('max_radius', 8)
    maxb = state.get('max_bombs', 6)
    me = None
    for p in players:
        if p['id'] == you:
            me = p
            break
    if me is None:
        return 'stay'
    cx, cy = me['x'], me['y']
    myr = me['radius']
    mycell = cy * W + cx

    tab, _ = _crush(W, state.get('crush_rotation', 0) % 4, cs)
    crush_at = dict(tab)
    for c in state.get('crushed', ()):
        crush_at.pop((c[0], c[1]), None)
    # 只保留有余下回合的落墙
    crush_at = {k: v for k, v in crush_at.items() if v >= turn}

    H = 30
    floor, dead, _, fl, blk = _build(turn, H, grid, bombs, None, fuse, crush_at, W, HH)
    sets = _safe(floor, dead, turn, W, HH, H)

    def level(cell):
        for i in range(len(sets) - 1, -1, -1):
            if (sets[i] >> cell) & 1:
                return HORIZONS[i]
        return 0

    item_at = {}
    for it in state['items']:
        item_at[(it['x'], it['y'])] = it['kind']
    goals = set()
    for (ix, iy) in item_at:
        goals.add(iy * W + ix)
    if not goals or True:
        for y in range(HH):
            for x in range(W):
                if grid[y][x] != '.':
                    continue
                for dx, dy in DIRS:
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < W and 0 <= ny < HH and grid[ny][nx] == '#':
                        goals.add(y * W + x)
                        break
    dist = _bfs_multi(W, HH, grid, goals)
    occ = set((b['x'], b['y']) for b in bombs)
    oppcells = [(p['x'], p['y'], p['radius']) for p in players if p['id'] != you]

    mylv = level(mycell)
    dcur = dist[mycell]

    # 对手潜在火力（他会放弹）
    threat = 0
    for ox, oy, orr in oppcells:
        threat |= 1 << (oy * W + ox)
        for dx, dy in DIRS:
            x, y = ox + dx, oy + dy
            for _ in range(orr):
                if not (0 <= x < W and 0 <= y < HH):
                    break
                if grid[y][x] != '.':
                    break
                threat |= 1 << (y * W + x)
                x += dx
                y += dy

    late = (turn - (cs - 45)) / 45.0
    late = 0.0 if late < 0 else (1.0 if late > 1 else late)

    # 压墙生存价值：越靠中心越晚被压到
    ctab = {}
    order = 0
    for (x, y), ct in sorted(crush_at.items(), key=lambda kv: kv[1]):
        order += 1
        ctab[y * W + x] = order
    total = len(ctab) or 1

    def surv(lv, full):
        sc = 5.0 * min(lv, 40)
        if lv >= full:
            sc += 60.0
        if lv < fuse + 1:
            sc -= 260.0
        return sc

    def crush_value(cell):
        if late <= 0:
            return 0.0
        o = ctab.get(cell)
        if o is None:
            return 60.0 * late
        return 60.0 * late * (o / total)

    cands = [('stay', mycell)]
    for nm, (dx, dy) in DNAME.items():
        nx, ny = cx + dx, cy + dy
        if not (0 <= nx < W and 0 <= ny < HH):
            continue
        if grid[ny][nx] != '.' or (nx, ny) in occ:
            continue
        cands.append((nm, ny * W + nx))

    prev = PREV.get('c') if PREV.get('t') == turn - 1 else None
    best = ('stay', -1e18)
    for nm, e in cands:
        ex, ey = e % W, e // W
        lv = level(e)
        sc = surv(lv, H) + crush_value(e)
        de = dist[e]
        if de >= INF:
            de = dcur + 4
        sc += 4.0 * (dcur - de) if de < dcur else -1.0 * min(de - dcur, 6)
        it = item_at.get((ex, ey))
        if it:
            sc += IVAL.get(it, 12.0)
        # 靠近砖（挖宝）
        if late < 0.9 and (ex, ey) != (cx, cy):
            nb = 0
            for dx, dy in DIRS:
                nx, ny = ex + dx, ey + dy
                if 0 <= nx < W and 0 <= ny < HH and grid[ny][nx] == '#':
                    nb += 1
            sc += 5.0 * nb * (1.0 - late)
        if (threat >> e) & 1:
            sc -= 6.0 + 8.0 * late
        if prev is not None and e == prev and len(cands) > 1:
            sc -= 5.0
        if nm == 'stay':
            sc -= 0.9
        if lv >= H and mylv < H:
            sc += 25.0
        if sc > best[1]:
            best = (nm, sc)

    prevlv = PREV.get('lv', 0)

    if me.get('can_bomb') and (cx, cy) not in occ:
        fl2, dead2, blast, flx, blk2 = _build(turn, H, grid, bombs, (cx, cy, myr),
                                              fuse, crush_at, W, HH)
        st2 = _safe(fl2, dead2, turn, W, HH, H)

        def level2(cell):
            for i in range(len(st2) - 1, -1, -1):
                if (st2[i] >> cell) & 1:
                    return HORIZONS[i]
            return 0

        # 放弹后：下一回合必须能站到某个相邻格，并从那时起活到爆炸之后
        st3 = _safe(fl2, dead2, turn + 1, W, HH, H - 1)

        def level3(cell):
            for i in range(len(st3) - 1, -1, -1):
                if (st3[i] >> cell) & 1:
                    return HORIZONS[i]
            return 0

        esc = -1
        for dx, dy in DIRS:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < W and 0 <= ny < HH):
                continue
            if grid[ny][nx] != '.' or (nx, ny) in occ:
                continue
            v = level3(ny * W + nx)
            if v > esc:
                esc = v
        if esc >= fuse - 1 and esc >= 1:
            brk = 0
            hit_item = 0
            for dx, dy in DIRS:
                x, y = cx + dx, cy + dy
                for _ in range(myr):
                    if not (0 <= x < W and 0 <= y < HH):
                        break
                    ch = grid[y][x]
                    if ch == '@':
                        break
                    if ch == '#':
                        brk += 1
                        break
                    if (x, y) in item_at:
                        hit_item += 1
                    x += dx
                    y += dy
            sc = surv(esc, H) + crush_value(mycell) + 8.0 + 22.0 * brk + 2.0 * brk * brk
            sc -= 30.0 * hit_item
            sc += 2.0 * myr
            if myr < maxr:
                sc += 3.0
            if me.get('bomb_limit', 1) < maxb:
                sc += 3.0
            own = sum(1 for b in bombs if b['owner'] == you)
            if own:
                sc -= 20.0
            # 炸人
            for ox, oy, orr in oppcells:
                if (blast >> (oy * W + ox)) & 1:
                    olv = level2(oy * W + ox)
                    if olv < fuse:
                        sc += 500.0
                    elif olv < fuse + 4:
                        sc += 120.0
                    else:
                        sc += 10.0
                elif abs(ox - cx) + abs(oy - cy) <= myr + 2:
                    sc += 6.0
            if sc > best[1]:
                best = ('bomb', sc)

    act = best[0]
    nd = mycell
    if act in DNAME:
        dx, dy = DNAME[act]
        nd = (cy + dy) * W + (cx + dx)
    if PREV.get('t') != turn:
        PREV['c'] = nd
        PREV['lv'] = level(nd) if act != 'bomb' else prevlv
        PREV['t'] = turn
    return act
