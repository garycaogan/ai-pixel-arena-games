from collections import deque

DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


def walkable(gl, x, y, w):
    return 0 <= x < w and 0 <= y < w and gl[y][x] == "."


def decide(state):
    w = state["width"]
    h = state["height"]
    gl = state["grid"]
    me = None
    others = []
    for p in state["players"]:
        if p["id"] == state["you"]:
            me = p
        else:
            others.append(p)
    if me is None:
        return "stay"
    mx, my = me["x"], me["y"]
    bombs = state["bombs"]
    turn = state["turn"]
    items = state.get("items", [])

    bomb_at = {}
    for b in bombs:
        bomb_at[(b["x"], b["y"])] = b

    # danger cells for this turn (fuse==1 explodes this turn after moves)
    danger = set()
    for b in bombs:
        r = b["radius"]
        bx, by = b["x"], b["y"]
        if b["fuse"] <= 1:
            danger.add((bx, by))
            for dx, dy in DIRS.values():
                for k in range(1, r + 1):
                    cx, cy = bx + dx * k, by + dy * k
                    if not (0 <= cx < w and 0 <= cy < h):
                        break
                    c = gl[cy][cx]
                    if c == "@" or c == "#":
                        break
                    danger.add((cx, cy))
    # hypothetical: enemies could place bombs now at their feet
    for p in others:
        if p.get("can_bomb", p["active_bombs"] < p["bomb_limit"]):
            r = p["radius"]
            danger.add((p["x"], p["y"]))
            for dx, dy in DIRS.values():
                for k in range(1, r + 1):
                    cx, cy = p["x"] + dx * k, p["y"] + dy * k
                    if not (0 <= cx < w and 0 <= cy < h):
                        break
                    c = gl[cy][cx]
                    if c == "@" or c == "#":
                        break
                    danger.add((cx, cy))
    # next-turn danger: bombs with fuse 2 explode next turn
    danger2 = set()
    for b in bombs:
        r = b["radius"]
        for dx, dy in DIRS.values():
            for k in range(1, r + 1):
                cx, cy = b["x"] + dx * k, b["y"] + dy * k
                if not (0 <= cx < w and 0 <= cy < h):
                    break
                c = gl[cy][cx]
                if c == "@" or c == "#":
                    break
                danger2.add((cx, cy))
        danger2.add((b["x"], b["y"]))

    crush_soon = set()
    for c in state.get("next_crush", []):
        if c["turn"] <= turn + 2:
            crush_soon.add((c["x"], c["y"]))

    occupied = set((p["x"], p["y"]) for p in state["players"] if p["id"] != state["you"])

    def safe_cell(x, y):
        if not walkable(gl, x, y, w):
            return False
        if (x, y) in bomb_at:
            return False
        if (x, y) in danger:
            return False
        if (x, y) in crush_soon:
            return False
        return True

    # BFS to nearest safe & interesting target (item, or brick cluster to bomb)
    targets = {}
    for it in items:
        targets[(it["x"], it["y"])] = 60
    # bricks adjacent to reachable cells as bombing targets
    brick_spots = set()
    for y in range(h):
        for x in range(w):
            if gl[y][x] == "#":
                for dx, dy in DIRS.values():
                    nx, ny = x + dx, y + dy
                    if walkable(gl, nx, ny, w):
                        brick_spots.add((nx, ny))
    for s in brick_spots:
        if s not in targets:
            targets[s] = 20

    # BFS from my position over safe cells (this turn safe; we re-check per step roughly)
    best_act = None
    best_score = -1
    # first: try to move to a safe adjacent cell, prefer one closer (BFS dist) to targets
    dist = {}
    q = deque()
    start = (mx, my)
    dist[start] = 0
    q.append(start)
    while q:
        cx, cy = q.popleft()
        for dx, dy in DIRS.values():
            nx, ny = cx + dx, cy + dy
            if (nx, ny) in dist:
                continue
            if not walkable(gl, nx, ny, w) or (nx, ny) in bomb_at:
                continue
            dist[(nx, ny)] = dist[(cx, cy)] + 1
            q.append((nx, ny))

    def move_score(name):
        dx, dy = DIRS[name]
        nx, ny = mx + dx, my + dy
        if not safe_cell(nx, ny):
            return -1000
        if (nx, ny) in occupied:
            return -500
        s = 0
        # target-directed
        td = 100000
        for t, tv in targets.items():
            if t in dist:
                d = abs(t[0] - nx) + abs(t[1] - ny)
                td = min(td, d - tv / 10)
        s -= td
        # second-step safety
        ok2 = False
        for dx2, dy2 in DIRS.values():
            ox, oy = nx + dx2, ny + dy2
            if walkable(gl, ox, oy, w) and (ox, oy) not in bomb_at and (ox, oy) not in danger2 and (ox, oy) not in danger:
                ok2 = True
        if not ok2 and (nx, ny) not in danger2:
            s -= 30
        elif not ok2:
            s -= 200
        # stay near enemies but not too close to their bombs
        for p in others:
            d = abs(p["x"] - nx) + abs(p["y"] - ny)
            if d <= 2:
                s -= 25
        return s

    stay_ok = (mx, my) not in danger and (mx, my) not in crush_soon
    stay_s = 0 if stay_ok else -2000
    if stay_ok:
        td = 100000
        for t, tv in targets.items():
            if t in dist:
                d = abs(t[0] - mx) + abs(t[1] - my)
                td = min(td, d - tv / 10)
        stay_s -= td

    # bombing decision
    can_bomb = me["active_bombs"] < me["bomb_limit"] and (mx, my) not in bomb_at
    if can_bomb:
        worth = False
        r = me["radius"]
        for dx, dy in DIRS.values():
            for k in range(1, r + 1):
                cx, cy = mx + dx * k, my + dy * k
                if not (0 <= cx < w and 0 <= cy < h):
                    break
                c = gl[cy][cx]
                if c == "#":
                    worth = True
                    break
                if c == "@":
                    break
        # hit enemy?
        for p in others:
            if abs(p["x"] - mx) + abs(p["y"] - my) <= r and (p["x"] == mx or p["y"] == my):
                # check line of sight
                ok = True
                sx = 1 if p["x"] > mx else (-1 if p["x"] < mx else 0)
                sy = 1 if p["y"] > my else (-1 if p["y"] < my else 0)
                steps = max(abs(p["x"] - mx), abs(p["y"] - my))
                for t in range(1, steps):
                    cxx, cyy = mx + sx * t, my + sy * t
                    if gl[cyy][cxx] != ".":
                        ok = False
                        break
                if ok:
                    worth = True
        if worth:
            # verify escape exists after placing: simulate my bomb at feet fuse 3
            mycells = {(mx, my)}
            for dx, dy in DIRS.values():
                for k in range(1, r + 1):
                    cx, cy = mx + dx * k, my + dy * k
                    if not (0 <= cx < w and 0 <= cy < h):
                        break
                    c = gl[cy][cx]
                    if c != ".":
                        break
                    mycells.add((cx, cy))
            # BFS escape within 3 turns avoiding my bomb cells and existing danger
            esc = deque()
            esc.append(((mx, my), 1))
            seen = {(mx, my)}
            found = False
            while esc:
                (cx, cy), t = esc.popleft()
                if t > 3:
                    continue
                if (cx, cy) not in mycells and (cx, cy) not in danger:
                    found = True
                    break
                for dx, dy in DIRS.values():
                    nx, ny = cx + dx, cy + dy
                    if (nx, ny) in seen:
                        continue
                    if not walkable(gl, nx, ny, w) or (nx, ny) in bomb_at:
                        continue
                    if (nx, ny) in mycells:
                        # can pass through own new bomb cell? no; skip
                        continue
                    seen.add((nx, ny))
                    esc.append(((nx, ny), t + 1))
            if found:
                return "bomb"

    for name in DIRS:
        s = move_score(name)
        if s > best_score:
            best_score = s
            best_act = name
    if best_act is not None and best_score > stay_s:
        return best_act
    return "stay"
