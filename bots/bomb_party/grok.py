"""Bomber II: break bricks, take items, don't die.

Fuse timing, checked against the engine:
  a bomb showing fuse k explodes at the end of the resolution k-1 turns
  from now (fuse 1 dies this resolution, fuse 3 dies in two resolutions).
  A bomb planted this resolution is not in the state yet; it explodes at
  offset bomb_fuse (3 resolutions later).
"""

from collections import deque

DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
DIR_LIST = ("up", "down", "left", "right")
ACTIONS = DIR_LIST + ("bomb", "stay")

_LAST = None
_STUCK = 0


def decide(state):
    global _LAST, _STUCK
    try:
        action = _decide(state)
    except Exception:
        action = "stay"
    if action not in ACTIONS:
        action = "stay"
    if action == _LAST == "stay":
        _STUCK += 1
    else:
        _STUCK = 0
    _LAST = action
    return action


def floor_at(grid, x, y):
    h = len(grid)
    w = len(grid[0]) if h else 0
    return 0 <= x < w and 0 <= y < h and grid[y][x] == "."


def blast_cells(grid, x, y, radius):
    cells = {(x, y)}
    bricks = []
    h = len(grid)
    w = len(grid[0])
    for dx, dy in DIRS.values():
        for dist in range(1, radius + 1):
            xx, yy = x + dx * dist, y + dy * dist
            if not (0 <= xx < w and 0 <= yy < h) or grid[yy][xx] == "@":
                break
            cells.add((xx, yy))
            if grid[yy][xx] == "#":
                bricks.append((xx, yy))
                break
    return cells, bricks


def danger_index(flames):
    d = {}
    for t, cells in enumerate(flames):
        for c in cells:
            if c not in d:
                d[c] = t
    return d


def blast_timeline(state, horizon=8):
    w, h = state["width"], state["height"]
    grid = state["grid"]
    bombs = []
    for b in state["bombs"]:
        bombs.append({
            "id": b["id"], "x": b["x"], "y": b["y"], "fuse": b["fuse"],
            "radius": b["radius"], "direction": b["direction"],
        })
    items = {(it["x"], it["y"]) for it in state["items"]}
    players = {(p["x"], p["y"]) for p in state["players"]}
    flames = [set() for _ in range(horizon)]
    for _ in range(horizon):
        slides = {}
        dest_count = {}
        for b in bombs:
            d = b["direction"]
            if not d:
                continue
            dx, dy = DIRS[d]
            q = (b["x"] + dx, b["y"] + dy)
            if not (0 <= q[0] < w and 0 <= q[1] < h) or grid[q[1]][q[0]] != ".":
                b["direction"] = None
                continue
            if q in items or q in players:
                b["direction"] = None
                continue
            slides[id(b)] = q
            dest_count[q] = dest_count.get(q, 0) + 1
        occupied = {(b["x"], b["y"]) for b in bombs}
        for b in bombs:
            q = slides.get(id(b))
            if q is None:
                continue
            if dest_count[q] == 1 and q not in occupied:
                b["x"], b["y"] = q
            else:
                b["direction"] = None
        for b in bombs:
            b["fuse"] -= 1
        by_cell = {(b["x"], b["y"]): b for b in bombs}
        pending = deque(sorted((b for b in bombs if b["fuse"] <= 0), key=lambda b: b["id"]))
        seen = set()
        hit = set()
        while pending:
            b = pending.popleft()
            if b["id"] in seen:
                continue
            seen.add(b["id"])
            cells, _ = blast_cells(grid, b["x"], b["y"], b["radius"])
            hit |= cells
            for c in cells:
                other = by_cell.get(c)
                if other is not None and other["id"] not in seen:
                    pending.append(other)
        flames[_].update(hit) if False else None
        # index is the loop variable; assign properly
        flames[_] |= hit
        bombs = [b for b in bombs if b["id"] not in seen]
    return flames


def add_plant(flames, grid, x, y, radius, fuse):
    """Plant decision happens at offset 0. Blast is `fuse` resolutions later
    (plant on turn 5, fuse shows 3 on turn 6, dies end of turn 8 = offset 3
    from the decision)."""
    out = [set(s) for s in flames]
    while len(out) <= fuse:
        out.append(set())
    cells, _ = blast_cells(grid, x, y, radius)
    out[fuse] |= cells
    return out


def escape_exists(grid, pos, bomb_cells, danger, horizon=6, occupied=()):
    """Survive `horizon` resolutions without standing on a blast.

    Node t is the start of resolution t. A cell with danger d burns at the
    end of resolution d, so occupying it at t >= d is death (we would have
    to leave during the detonation resolution, which this search does not
    count as safe — one-ply play stays if the search says stay is ok).

    Bricks stop being walkable until the resolution AFTER they burn: the
    blast and the brick removal happen together, so the newly opened cell
    is entered on the next resolution at the earliest. Modelling it as open
    the whole time is how a sealed plant looked survivable.
    """
    blocked = set(bomb_cells)
    occupied = set(occupied)

    def walkable(cell, t):
        x, y = cell
        if not (0 <= y < len(grid) and 0 <= x < len(grid[0])):
            return False
        ch = grid[y][x]
        if ch == ".":
            return True
        if ch == "#":
            # open only after the blast resolution has finished
            d = danger.get(cell)
            return d is not None and t > d
        return False

    if danger.get(pos, 99) <= 0:
        return False
    q = deque([(pos[0], pos[1], 0)])
    seen = {(pos[0], pos[1], 0)}
    while q:
        x, y, t = q.popleft()
        if t >= horizon:
            return True
        if danger.get((x, y), 99) <= t:
            continue
        options = [(x, y)]
        for dname in DIR_LIST:
            nx = x + DIRS[dname][0]
            ny = y + DIRS[dname][1]
            if (nx, ny) in blocked or (nx, ny) in occupied:
                continue
            if walkable((nx, ny), t + 1):
                options.append((nx, ny))
        for nx, ny in options:
            if danger.get((nx, ny), 99) <= t:
                # still here at the start of a resolution that burns it
                continue
            nt = t + 1
            if danger.get((nx, ny), 99) <= nt:
                continue
            if nt >= horizon:
                return True
            key = (nx, ny, nt)
            if key not in seen:
                seen.add(key)
                q.append(key)
    return False



def dist_map(grid, start, blocked):
    blocked = set(blocked)
    blocked.discard(start)
    q = deque([start])
    dist = {start: 0}
    while q:
        x, y = q.popleft()
        for dx, dy in DIRS.values():
            nx, ny = x + dx, y + dy
            if (nx, ny) in dist or (nx, ny) in blocked:
                continue
            if floor_at(grid, nx, ny):
                dist[(nx, ny)] = dist[(x, y)] + 1
                q.append((nx, ny))
    return dist


def first_step(grid, start, goal, blocked):
    if start == goal:
        return None
    blocked = set(blocked)
    blocked.discard(start)
    q = deque([goal])
    prev = {goal: None}
    while q:
        x, y = q.popleft()
        for dx, dy in DIRS.values():
            nx, ny = x + dx, y + dy
            if (nx, ny) in prev or (nx, ny) in blocked:
                continue
            if floor_at(grid, nx, ny) or (nx, ny) == start:
                prev[(nx, ny)] = (x, y)
                if (nx, ny) == start:
                    nxt = prev[start]
                    for name, d in DIRS.items():
                        if (start[0] + d[0], start[1] + d[1]) == nxt:
                            return name
                    return None
                q.append((nx, ny))
    return None


def crush_offset(state):
    turn = state["turn"]
    out = {}
    for cell in state.get("next_crush") or []:
        off = cell["turn"] - turn
        if 0 <= off <= 12:
            out[(cell["x"], cell["y"])] = off
    return out


def _decide(state):
    you = state["you"]
    grid = state["grid"]
    w, h = state["width"], state["height"]
    me = next(p for p in state["players"] if p["id"] == you)
    pos = (me["x"], me["y"])
    turn = state["turn"]
    fuse = state["bomb_fuse"]
    radius = me["radius"]
    others = [p for p in state["players"] if p["id"] != you]
    bomb_cells = {(b["x"], b["y"]) for b in state["bombs"]}
    my_bombs = [b for b in state["bombs"] if b["owner"] == you]
    items = {(it["x"], it["y"]): it["kind"] for it in state["items"]}
    opp_pos = {(p["x"], p["y"]) for p in others}
    flames = blast_timeline(state, horizon=8)
    danger = danger_index(flames)
    cmap = crush_offset(state)
    for cell, off in cmap.items():
        if danger.get(cell, 99) > off:
            danger[cell] = off
    center = (w // 2, h // 2)

    def end_of(act):
        if act in DIRS:
            q = (pos[0] + DIRS[act][0], pos[1] + DIRS[act][1])
            if q in bomb_cells:
                return pos  # kick, we stay
            return q
        return pos

    def legal(act):
        if act == "stay":
            return True
        if act == "bomb":
            return me["can_bomb"] and pos not in bomb_cells
        if act not in DIRS:
            return False
        q = end_of(act)
        if act in DIRS and (pos[0] + DIRS[act][0], pos[1] + DIRS[act][1]) in bomb_cells:
            return me["can_kick"]
        if q in opp_pos:
            return False
        return floor_at(grid, q[0], q[1])

    def safe_dest(dest):
        return escape_exists(grid, dest, bomb_cells, danger, horizon=6, occupied=opp_pos)

    moves = [a for a in DIR_LIST + ("stay",) if legal(a) and safe_dest(end_of(a))]

    # while one of our bombs is live, do not plant another and do not step
    # toward its blast
    if my_bombs:
        def safety(dest):
            return danger.get(dest, 99)
        best = max(moves or ["stay"], key=lambda a: (safety(end_of(a)), -abs(end_of(a)[0] - center[0]) - abs(end_of(a)[1] - center[1])))
        if moves:
            return best
        # no safe move: take the one that burns latest
        fallbacks = [a for a in DIR_LIST + ("stay",) if legal(a)]
        return max(fallbacks, key=lambda a: danger.get(end_of(a), 99))

    # candidate plant cells: reachable, blast opens a brick, and after the
    # plant there is still an escape
    blocked = set(bomb_cells)
    dist = dist_map(grid, pos, blocked)
    plant_here = False
    if me["can_bomb"] and pos not in bomb_cells:
        cells, bricks = blast_cells(grid, pos[0], pos[1], radius)
        if bricks:
            fl = add_plant(flames, grid, pos[0], pos[1], radius, fuse)
            pdanger = danger_index(fl)
            for cell, off in cmap.items():
                if pdanger.get(cell, 99) > off:
                    pdanger[cell] = off
            # must have a neighbor we can step to next resolution that itself escapes
            if escape_exists(grid, pos, bomb_cells | {pos}, pdanger, horizon=fuse + 2, occupied=opp_pos):
                # and that escape does not depend on standing still in the blast
                if any(
                    legal(a) and a in DIRS and escape_exists(
                        grid, end_of(a), bomb_cells | {pos}, pdanger, horizon=fuse + 2, occupied=opp_pos
                    )
                    for a in DIR_LIST
                ):
                    plant_here = True

    if plant_here and (len(bricks) >= 1):
        # don't plant if an existing bomb already threatens this cell
        if danger.get(pos, 99) > fuse:
            return "bomb"

    # walk toward the nearest useful plant or item
    goal = None
    best_score = -1
    for cell, d in dist.items():
        if d == 0 or d > 8 or cell in bomb_cells:
            continue
        if danger.get(cell, 99) <= d:
            continue
        kind = items.get(cell)
        cells, bricks = blast_cells(grid, cell[0], cell[1], radius)
        fl = add_plant(flames, grid, cell[0], cell[1], radius, fuse) if bricks and me["can_bomb"] else None
        plant_ok = False
        if fl is not None:
            pdanger = danger_index(fl)
            plant_ok = escape_exists(grid, cell, bomb_cells | {cell}, pdanger, horizon=fuse + 2)
        score = 0
        if kind:
            score += {"kick": 28, "bomb": 22, "fire": 18}[kind]
        if plant_ok:
            score += len(bricks) * 6
        # prefer not walking into a lane an opponent bomb already owns
        score -= d * 1.5
        if score > best_score:
            best_score = score
            goal = cell

    if goal and best_score > 0:
        step = first_step(grid, pos, goal, blocked)
        if step and step in moves:
            return step

    # otherwise the move whose cell burns latest, then closest to center
    if moves:
        def rank(a):
            dest = end_of(a)
            return (danger.get(dest, 99), -abs(dest[0] - center[0]) - abs(dest[1] - center[1]))
        return max(moves, key=rank)

    fallbacks = [a for a in DIR_LIST + ("stay",) if legal(a)]
    if not fallbacks:
        return "stay"
    return max(fallbacks, key=lambda a: danger.get(end_of(a), 99))
