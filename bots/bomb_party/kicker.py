"""Standard-library sparring bot: short time-expanded escape search and loot routing.

This file alone is a valid submission. Test policies call choose(state, style).
"""
from collections import Counter, deque

DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0), "stay": (0, 0)}


def _rays(grid, b, at):
    x, y = b["x"], b["y"]
    cells = {(x, y)}
    for dx, dy in list(DIRS.values())[:4]:
        for d in range(1, b["radius"] + 1):
            q = u, v = x + dx * d, y + dy * d
            if not (0 <= v < len(grid) and 0 <= u < len(grid[0])) or grid[v][u] == "@":
                break
            cells.add(q)
            if grid[v][u] == "#" or q in at:
                break
    return cells


def _forecast(state, extra=None):
    """Simulate public bombs, including motion, simultaneous rays and future walls.

Players are held at their published cells for bomb sliding. Unexpected opponent
moves/kicks remain deliberately outside this modest baseline's model.
"""
    horizon = max([state["bomb_fuse"] + 1] + [b["fuse"] for b in state["bombs"]])
    horizon = min(horizon, 8)
    grid = [list(r) for r in state["grid"]]
    bombs = [dict(b) for b in state["bombs"]] + ([dict(extra)] if extra else [])
    people = {(p["x"], p["y"]) for p in state["players"]}
    items = {(p["x"], p["y"]) for p in state["items"]}
    schedule = {p["turn"] - state["turn"] + 1: (p["x"], p["y"]) for p in state["next_crush"]}
    forecast = []
    for time in range(1, horizon + 1):
        walk_grid = [r[:] for r in grid]
        before = {(b["x"], b["y"]) for b in bombs}
        blocked = before | people | items
        wants = {}
        for b in bombs:
            direction = b.get("direction")
            if direction:
                dx, dy = DIRS[direction]
                q = x, y = b["x"] + dx, b["y"] + dy
                if 0 <= y < len(grid) and 0 <= x < len(grid[0]) and grid[y][x] == "." and q not in blocked:
                    wants[b["id"]] = q
                else:
                    b["direction"] = None
        counts = Counter(wants.values())
        sliding = set()
        for b in bombs:
            q = wants.get(b["id"])
            if q is not None:
                if counts[q] == 1:
                    b["x"], b["y"] = q
                    sliding.add(q)
                else:
                    b["direction"] = None
            b["fuse"] -= 1
        at = {(b["x"], b["y"]): b for b in bombs}
        pending = [b for b in bombs if b["fuse"] <= 0]
        exploded, danger = set(), set()
        while pending:
            b = pending.pop()
            if b["id"] in exploded:
                continue
            exploded.add(b["id"])
            rays = _rays(grid, b, at)
            danger.update(rays)
            pending.extend(at[q] for q in rays if q in at and at[q]["id"] not in exploded)
        for x, y in danger:
            if grid[y][x] == "#":
                grid[y][x] = "."
        items -= danger
        bombs = [b for b in bombs if b["id"] not in exploded]
        q = schedule.get(time)
        if q is not None:
            grid[q[1]][q[0]] = "@"
            walk_grid[q[1]][q[0]] = "@"
            bombs = [b for b in bombs if (b["x"], b["y"]) != q]
            items.discard(q)
        forecast.append((danger, before, sliding, walk_grid))
    return forecast


def _legal(grid, q):
    x, y = q
    return 0 <= y < len(grid) and 0 <= x < len(grid[0]) and grid[y][x] == "."


def _escape_count(start, forecast, offset=0, occupied=()):
    positions = {start}
    for danger, blocked, sliding, grid in forecast[offset:]:
        nxt = set()
        for x, y in positions:
            for dx, dy in DIRS.values():
                q = x + dx, y + dy
                if (_legal(grid, q) and q not in occupied and q not in danger and q not in sliding
                        and (q not in blocked or q == (x, y))):
                    nxt.add(q)
        positions = nxt
        if not positions:
            return 0
    return len(positions)


def _survives(start, forecast, offset=0, occupied=()):
    return bool(_escape_count(start, forecast, offset, occupied))


def _distances(state, start, blocked, directions=None):
    distances, queue = {start: 0}, deque([start])
    while queue:
        x, y = queue.popleft()
        for dx, dy in (directions or list(DIRS.values())[:4]):
            q = x + dx, y + dy
            if q not in distances and q not in blocked and _legal(state["grid"], q):
                distances[q] = distances[x, y] + 1
                queue.append(q)
    return distances


def _choose(state, style="baseline"):
    me = next(p for p in state["players"] if p["id"] == state["you"])
    start = me["x"], me["y"]
    occupied = {(p["x"], p["y"]) for p in state["players"] if p["id"] != me["id"]}
    bombs = {(b["x"], b["y"]): b for b in state["bombs"]}
    enemies = list(occupied)
    forecast = _forecast(state)
    danger, _, sliding, after = forecast[0]
    # Prefer useful bombs, but verify an escape through the full fuse/chain horizon.
    rays = _rays(state["grid"], dict(x=start[0], y=start[1], radius=me["radius"]), bombs)
    boxes = sum(state["grid"][y][x] == "#" for x, y in rays)
    threatened = sum(q in rays for q in enemies)
    near = min((abs(start[0] - x) + abs(start[1] - y) for x, y in enemies), default=99)
    useful = boxes or threatened or (style in ("aggressive", "kicker") and near <= 3)
    if style == "farmer":
        useful = boxes or threatened
    if me["can_bomb"] and start not in bombs and useful:
        extra = dict(id=-1, owner=me["id"], x=start[0], y=start[1],
                     fuse=state["bomb_fuse"] + 1, radius=me["radius"], direction=None)
        future = _forecast(state, extra)
        escape_directions = 0
        for dx, dy in list(DIRS.values())[:4]:
            q = start[0] + dx, start[1] + dy
            danger2, blocked2, sliding2, grid2 = future[1]
            if (_legal(grid2, q) and q not in occupied and q not in blocked2
                    and q not in danger2 and q not in sliding2
                    and _survives(q, future, 2, occupied)):
                escape_directions += 1
        robust = near > 3 or escape_directions >= 2
        if (robust and start not in future[0][0] and _legal(future[0][3], start)
                and _survives(start, future, 1, occupied)):
            return "bomb"
    # BFS distances give purposeful routes to items, opponents and bombable crates.
    directions = list(DIRS.values())[:4]
    if style in ("aggressive", "kicker"):
        directions.reverse()
    distances = _distances(state, start, set(bombs) | occupied, directions)
    targets = []
    for item in state["items"]:
        q = item["x"], item["y"]
        if q in distances:
            bonus = 10 if item["kind"] == "kick" and not me["can_kick"] else 7
            if style == "aggressive":
                bonus = 3
            if style == "farmer":
                bonus += 5
            targets.append((bonus - distances[q] * .7, q))
    for q, d in distances.items():
        x, y = q
        adjacent_boxes = sum(0 <= y + dy < state["height"] and 0 <= x + dx < state["width"]
                             and state["grid"][y + dy][x + dx] == "#"
                             for dx, dy in list(DIRS.values())[:4])
        enemy_distance = min((abs(x - u) + abs(y - v) for u, v in enemies), default=0)
        if adjacent_boxes:
            targets.append(((5 if style == "farmer" else 2) + adjacent_boxes - .45 * d, q))
        if style != "farmer" or not any("#" in row for row in state["grid"]):
            appetite = 12 if style == "aggressive" else (5 if style == "kicker" else 3)
            targets.append((appetite - enemy_distance * (.9 if style == "aggressive" else .45) - .25 * d, q))
    target = max(targets, default=(0, start), key=lambda it: it[0])[1]
    reverse = _distances(state, target, set(bombs) | occupied, directions)
    candidates = []
    # Rotate local tie-breaking by location/turn (no fixed north/east map bias).
    order = list(DIRS)
    personality = {"baseline": 0, "aggressive": 1, "farmer": 2, "kicker": 3}[style]
    shift = (state["turn"] // 4 + start[0] * 3 + start[1] * 7 + personality) % 4
    order = order[shift:4] + order[:shift] + ["stay"]
    for action in order:
        dx, dy = DIRS[action]
        q = start[0] + dx, start[1] + dy
        if q in bombs and q != start:
            if me["can_kick"] and style == "kicker":
                # A legal kick stays here; let the next turn's forecast replan.
                dx2, dy2 = DIRS[action]
                landing = q[0] + dx2, q[1] + dy2
                b = bombs[q]
                if b["fuse"] > 1 and _legal(state["grid"], landing) and landing not in bombs and landing not in occupied:
                    virtual = dict(state)
                    virtual["bombs"] = [dict(b, direction=action) if (b["x"], b["y"]) == q else b for b in state["bombs"]]
                    prediction = _forecast(virtual)
                    if start not in prediction[0][0] and _survives(start, prediction, 1, occupied):
                        candidates.append((10002, action))
            continue
        if (not _legal(state["grid"], q) or not _legal(after, q) or q in occupied
                or q in danger or q in sliding):
            continue
        escape_count = _escape_count(q, forecast, 1, occupied)
        safe = bool(escape_count)
        distance = reverse.get(q, 100)
        contested = action != "stay" and any(abs(q[0]-x) + abs(q[1]-y) == 1 for x, y in enemies)
        # Escape danger dominates strategy; discourage idle oscillation.
        margin = min(8, escape_count) * .5 if bombs else 0
        clear_of_fire = bombs and not any(q in prediction[0] for prediction in forecast)
        score = (10000 * safe + margin + 20 * bool(clear_of_fire) - distance
                 - 20 * contested + (0.15 if action != "stay" else 0))
        candidates.append((score, action))
    return max(candidates, default=(0, "stay"), key=lambda it: it[0])[1]


def choose(state, style="baseline"):
    # Evaluate every formal seat from its own top-left spawn. This avoids a
    # global up/right preference in shortest-path and equal-score choices.
    rotations = state["you"] if state["num_players"] == 4 else (2 * state["you"] if state["num_players"] == 2 else 0)
    local = state
    clockwise = {"up": "right", "right": "down", "down": "left", "left": "up", None: None}
    counter = {value: key for key, value in clockwise.items()}
    for _ in range(rotations):
        w = state["width"]
        local = dict(local)
        local["grid"] = ["".join(row[w - 1 - x] for row in local["grid"]) for x in range(w)]
        for key in ("players", "bombs", "items", "next_crush"):
            local[key] = [{**p, "x": p["y"], "y": w - 1 - p["x"]} for p in local[key]]
        local["bombs"] = [{**b, "direction": counter[b.get("direction")]} for b in local["bombs"]]
        local["items"].sort(key=lambda p: (p["x"], p["y"]))
        local["crushed"] = [[y, w - 1 - x] for x, y in local["crushed"]]
    action = _choose(local, style)
    for _ in range(rotations):
        action = clockwise.get(action, action)
    return action


def decide(state):
    return choose(state)


def decide(state):
    return choose(state, 'kicker')
