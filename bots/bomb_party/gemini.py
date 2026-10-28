"""Bomber II AI Bot - Version 3 (Tactical Simulation + Can-Bomb-Safely Navigation + Endgame Mastery)"""
from __future__ import annotations

from collections import deque

DIRS = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
}
ACTIONS = ("up", "down", "left", "right", "bomb", "stay")

_SPIRAL_CACHE = {}
_HISTORY = {}


def _rot(x: int, y: int, w: int, h: int, r: int) -> tuple[int, int]:
    for _ in range(r & 3):
        x, y, w, h = h - 1 - y, x, h, w
    return x, y


def get_crush_schedule(state: dict) -> dict[tuple[int, int], int]:
    w, h = state["width"], state["height"]
    rot = state["crush_rotation"]
    crush_start = state["crush_start"]
    key = (w, h, rot, crush_start)
    if key in _SPIRAL_CACHE:
        return _SPIRAL_CACHE[key]

    order = []
    l, t, r, b = 0, 0, w - 1, h - 1
    while l <= r and t <= b:
        for x in range(l, r + 1):
            order.append((x, t))
        for y in range(t + 1, b + 1):
            order.append((r, y))
        if t < b:
            for x in range(r - 1, l - 1, -1):
                order.append((x, b))
        if l < r:
            for y in range(b - 1, t, -1):
                order.append((l, y))
        l, t, r, b = l + 1, t + 1, r - 1, b - 1

    rotated = [_rot(x, y, w, h, rot) for x, y in order]
    spiral = []
    for x, y in rotated:
        if x == 0 or y == 0 or x == w - 1 or y == h - 1:
            continue
        if x % 2 == 0 and y % 2 == 0:
            continue
        spiral.append((x, y))

    schedule = {}
    for idx, pos in enumerate(spiral):
        schedule[pos] = crush_start + idx

    _SPIRAL_CACHE[key] = schedule
    return schedule


def sim_step_world(
    grid: list[list[str]],
    bombs: list[dict],
    items_set: set[tuple[int, int]],
    player_positions: set[tuple[int, int]],
    turn: int,
    crush_schedule: dict[tuple[int, int], int],
    w: int,
    h: int,
):
    new_grid = [row[:] for row in grid]
    new_bombs = [b.copy() for b in bombs]
    new_items = set(items_set)

    # Phase 4: Sliding
    blocked = (
        {(b["x"], b["y"]) for b in new_bombs}
        | player_positions
        | new_items
    )
    slides = {}
    for b in new_bombs:
        d = b.get("direction")
        if d is not None:
            dx, dy = DIRS[d]
            nx, ny = b["x"] + dx, b["y"] + dy
            if 0 <= nx < w and 0 <= ny < h and new_grid[ny][nx] == "." and (nx, ny) not in blocked:
                slides[b["id"]] = (nx, ny)
            else:
                b["direction"] = None

    counts = {}
    for pos in slides.values():
        counts[pos] = counts.get(pos, 0) + 1

    for b in new_bombs:
        bid = b["id"]
        if bid in slides:
            if counts[slides[bid]] == 1:
                b["x"], b["y"] = slides[bid]
            else:
                b["direction"] = None

    # Phase 5: Fuse & Chain & Rays
    for b in new_bombs:
        if not b.get("just_placed", False):
            b["fuse"] -= 1
        else:
            b["just_placed"] = False

    by_pos = {(b["x"], b["y"]): b for b in new_bombs}
    q = deque(sorted((b for b in new_bombs if b["fuse"] <= 0), key=lambda x: x["id"]))
    exploded = set()
    flames = set()
    bricks_hit = set()

    while q:
        b = q.popleft()
        if b["id"] in exploded:
            continue
        exploded.add(b["id"])
        bx, by = b["x"], b["y"]
        flames.add((bx, by))
        rad = b["radius"]
        for dx, dy in DIRS.values():
            for step in range(1, rad + 1):
                nx, ny = bx + dx * step, by + dy * step
                if not (0 <= nx < w and 0 <= ny < h):
                    break
                tile = new_grid[ny][nx]
                if tile == "@":
                    break
                flames.add((nx, ny))
                if tile == "#":
                    bricks_hit.add((nx, ny))
                    break
                other = by_pos.get((nx, ny))
                if other is not None:
                    if other["id"] not in exploded:
                        q.append(other)
                    break

    # Phase 6: Items, bricks, remove bombs
    new_items -= flames
    for bx, by in bricks_hit:
        new_grid[by][bx] = "."
    new_bombs = [b for b in new_bombs if b["id"] not in exploded]

    # Phase 7: Crush
    crushed_cell = None
    for pos, c_turn in crush_schedule.items():
        if c_turn == turn:
            cx, cy = pos
            if new_grid[cy][cx] != "@":
                new_grid[cy][cx] = "@"
                crushed_cell = (cx, cy)
                new_bombs = [b for b in new_bombs if (b["x"], b["y"]) != (cx, cy)]
                new_items.discard((cx, cy))
            break

    return new_grid, new_bombs, new_items, flames, crushed_cell, bricks_hit


def build_future_frames(
    grid: list[list[str]],
    bombs: list[dict],
    items_set: set[tuple[int, int]],
    player_positions: set[tuple[int, int]],
    start_turn: int,
    crush_schedule: dict[tuple[int, int], int],
    w: int,
    h: int,
    horizon: int = 6,
):
    frames = []
    cur_grid = [row[:] for row in grid]
    cur_bombs = [b.copy() for b in bombs]
    cur_items = set(items_set)

    for step in range(horizon):
        t = start_turn + step
        p_pos = player_positions if step == 0 else set()
        cur_grid, cur_bombs, cur_items, flames, crushed_cell, bricks_hit = sim_step_world(
            cur_grid, cur_bombs, cur_items, p_pos, t, crush_schedule, w, h
        )
        frames.append({
            "turn": t,
            "grid": cur_grid,
            "bombs": cur_bombs,
            "items": cur_items,
            "flames": flames,
            "crushed": crushed_cell,
            "bricks_hit": bricks_hit,
        })
    return frames


def analyze_survival(
    start_pos: tuple[int, int],
    frames: list[dict],
    initial_bombs_after_phase3: set[tuple[int, int]],
    other_players_pos: set[tuple[int, int]],
    w: int,
    h: int,
):
    f0 = frames[0]
    sx, sy = start_pos
    if (sx, sy) in f0["flames"] or f0["crushed"] == (sx, sy):
        return 0, 0, set(), set(), 999

    alive_positions = {start_pos}
    prev_bomb_positions = initial_bombs_after_phase3
    survived_steps = 1
    step1_positions = {start_pos}

    for step in range(1, len(frames)):
        f = frames[step]
        g_prev = frames[step - 1]["grid"]
        next_alive = set()

        for px, py in alive_positions:
            if (px, py) not in f["flames"] and f["crushed"] != (px, py) and f["grid"][py][px] == ".":
                next_alive.add((px, py))

            for dx, dy in DIRS.values():
                nx, ny = px + dx, py + dy
                if not (0 <= nx < w and 0 <= ny < h):
                    continue
                if g_prev[ny][nx] != ".":
                    continue
                if (nx, ny) in prev_bomb_positions:
                    continue
                if step == 1 and (nx, ny) in other_players_pos:
                    continue
                if (nx, ny) in f["flames"] or f["crushed"] == (nx, ny) or f["grid"][ny][nx] != ".":
                    continue
                next_alive.add((nx, ny))

        if not next_alive:
            break
        alive_positions = next_alive
        survived_steps = step + 1
        if step == 1:
            step1_positions = set(alive_positions)
        prev_bomb_positions = {(b["x"], b["y"]) for b in f["bombs"]}

    first_escape_step = 999
    if survived_steps == len(frames):
        all_future_flames = set()
        for f in frames[1:]:
            all_future_flames |= f["flames"]
            if f["crushed"]:
                all_future_flames.add(f["crushed"])
        if start_pos not in all_future_flames:
            first_escape_step = 0
        else:
            cur_s = {start_pos}
            p_bombs = initial_bombs_after_phase3
            for step in range(1, len(frames)):
                f = frames[step]
                g_prev = frames[step - 1]["grid"]
                nxt_s = set()
                later_flames = set()
                for lf in frames[step + 1:]:
                    later_flames |= lf["flames"]
                    if lf["crushed"]:
                        later_flames.add(lf["crushed"])
                for px, py in cur_s:
                    for cand in [(px, py)] + [(px + dx, py + dy) for dx, dy in DIRS.values()]:
                        cx, cy = cand
                        if not (0 <= cx < w and 0 <= cy < h):
                            continue
                        if cand != (px, py):
                            if g_prev[cy][cx] != "." or cand in p_bombs:
                                continue
                            if step == 1 and cand in other_players_pos:
                                continue
                        if cand in f["flames"] or f["crushed"] == cand or f["grid"][cy][cx] != ".":
                            continue
                        nxt_s.add(cand)
                        if cand not in later_flames and first_escape_step == 999:
                            first_escape_step = step
                cur_s = nxt_s
                p_bombs = {(b["x"], b["y"]) for b in f["bombs"]}

    final_grid = frames[-1]["grid"]
    final_bombs = {(b["x"], b["y"]) for b in frames[-1]["bombs"]}
    visited = set(alive_positions)
    q = deque(alive_positions)
    while q:
        cx, cy = q.popleft()
        for dx, dy in DIRS.values():
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                if final_grid[ny][nx] == "." and (nx, ny) not in final_bombs:
                    visited.add((nx, ny))
                    q.append((nx, ny))

    return survived_steps, len(visited), alive_positions, step1_positions, first_escape_step


def simulate_action_outcome(
    state: dict,
    me: dict,
    action: str,
    crush_schedule: dict[tuple[int, int], int],
    assumed_enemy_actions: dict[int, str] | None = None,
    horizon: int = 6,
):
    w, h = state["width"], state["height"]
    turn = state["turn"]
    grid = [list(row) for row in state["grid"]]

    mx, my = me["x"], me["y"]
    can_kick = me["can_kick"]
    can_bomb = me["can_bomb"]
    my_radius = me["radius"]

    bombs = []
    for b in state["bombs"]:
        bombs.append({
            "id": b["id"],
            "owner": b["owner"],
            "x": b["x"],
            "y": b["y"],
            "fuse": b["fuse"],
            "radius": b["radius"],
            "direction": b["direction"],
            "just_placed": False,
        })
    bombs_by_pos = {(b["x"], b["y"]): b for b in bombs}
    other_players = [p for p in state["players"] if p["id"] != me["id"]]
    other_pos = {(p["x"], p["y"]) for p in other_players}
    items_map = {(it["x"], it["y"]): it["kind"] for it in state["items"]}
    items_set = set(items_map.keys())

    new_mx, new_my = mx, my
    kicked_bomb = False
    placed_bomb = False
    move_succeeded = True

    if action in DIRS:
        dx, dy = DIRS[action]
        tx, ty = mx + dx, my + dy
        if not (0 <= tx < w and 0 <= ty < h) or grid[ty][tx] != ".":
            move_succeeded = False
        elif (tx, ty) in bombs_by_pos:
            if can_kick:
                bombs_by_pos[(tx, ty)]["direction"] = action
                kicked_bomb = True
            else:
                move_succeeded = False
        elif (tx, ty) in other_pos:
            move_succeeded = False
        else:
            new_mx, new_my = tx, ty

    enemy_final_pos = {}
    for ep in other_players:
        eid = ep["id"]
        ex, ey = ep["x"], ep["y"]
        eact = assumed_enemy_actions.get(eid, "stay") if assumed_enemy_actions else "stay"
        if eact in DIRS:
            dx, dy = DIRS[eact]
            etx, ety = ex + dx, ey + dy
            if 0 <= etx < w and 0 <= ety < h and grid[ety][etx] == ".":
                if (etx, ety) in bombs_by_pos:
                    if ep["can_kick"]:
                        b_target = bombs_by_pos[(etx, ety)]
                        if kicked_bomb and b_target["x"] == mx + DIRS.get(action, (0, 0))[0] and b_target["y"] == my + DIRS.get(action, (0, 0))[1]:
                            b_target["direction"] = None
                        else:
                            b_target["direction"] = eact
                    enemy_final_pos[eid] = (ex, ey)
                elif (etx, ety) == (new_mx, new_my) and (new_mx, new_my) != (mx, my):
                    new_mx, new_my = mx, my
                    move_succeeded = False
                    enemy_final_pos[eid] = (ex, ey)
                elif (etx, ety) not in other_pos and (etx, ety) != (mx, my):
                    enemy_final_pos[eid] = (etx, ety)
                else:
                    enemy_final_pos[eid] = (ex, ey)
            else:
                enemy_final_pos[eid] = (ex, ey)
        else:
            enemy_final_pos[eid] = (ex, ey)
            if eact == "bomb" and ep["can_bomb"] and (ex, ey) not in bombs_by_pos:
                next_id = max((b["id"] for b in bombs), default=0) + 1 + eid
                eb = {
                    "id": next_id,
                    "owner": eid,
                    "x": ex,
                    "y": ey,
                    "fuse": state.get("bomb_fuse", 3),
                    "radius": ep["radius"],
                    "direction": None,
                    "just_placed": True,
                }
                bombs.append(eb)
                bombs_by_pos[(ex, ey)] = eb

    picked_item = None
    eff_radius = my_radius
    eff_can_bomb = can_bomb
    if (new_mx, new_my) in items_map:
        picked_item = items_map[(new_mx, new_my)]
        items_set.discard((new_mx, new_my))
        if picked_item == "fire":
            eff_radius = min(state.get("max_radius", 8), my_radius + 1)
        elif picked_item == "bomb":
            eff_can_bomb = True

    for ep_pos in enemy_final_pos.values():
        items_set.discard(ep_pos)

    if action == "bomb":
        if eff_can_bomb and (new_mx, new_my) not in bombs_by_pos:
            next_id = max((b["id"] for b in bombs), default=0) + 100
            nb = {
                "id": next_id,
                "owner": me["id"],
                "x": new_mx,
                "y": new_my,
                "fuse": state.get("bomb_fuse", 3),
                "radius": eff_radius,
                "direction": None,
                "just_placed": True,
            }
            bombs.append(nb)
            bombs_by_pos[(new_mx, new_my)] = nb
            placed_bomb = True

    bombs_after_phase3 = {(b["x"], b["y"]) for b in bombs}
    all_player_positions = {(new_mx, new_my)} | set(enemy_final_pos.values())

    frames = build_future_frames(
        grid=grid,
        bombs=bombs,
        items_set=items_set,
        player_positions=all_player_positions,
        start_turn=turn,
        crush_schedule=crush_schedule,
        w=w,
        h=h,
        horizon=horizon,
    )

    survived_steps, comp_size, alive_end_pos, step1_pos, first_escape_step = analyze_survival(
        start_pos=(new_mx, new_my),
        frames=frames,
        initial_bombs_after_phase3=bombs_after_phase3,
        other_players_pos=set(enemy_final_pos.values()),
        w=w,
        h=h,
    )

    return {
        "action": action,
        "pos": (new_mx, new_my),
        "move_succeeded": move_succeeded,
        "kicked_bomb": kicked_bomb,
        "placed_bomb": placed_bomb,
        "picked_item": picked_item,
        "survived_steps": survived_steps,
        "comp_size": comp_size,
        "alive_end_pos": alive_end_pos,
        "step1_pos": step1_pos,
        "first_escape_step": first_escape_step,
        "frames": frames,
        "bombs_after_phase3": bombs_after_phase3,
        "eff_radius": eff_radius,
    }


def evaluate_worst_case_vs_enemies(
    state: dict,
    me: dict,
    action: str,
    base_outcome: dict,
    crush_schedule: dict[tuple[int, int], int],
):
    other_players = [p for p in state["players"] if p["id"] != me["id"]]
    if not other_players or base_outcome["survived_steps"] < 6:
        return base_outcome["survived_steps"], base_outcome["comp_size"], len(base_outcome["step1_pos"])

    mx, my = base_outcome["pos"]
    close_enemies = [
        ep for ep in other_players
        if abs(ep["x"] - mx) + abs(ep["y"] - my) <= 5
    ]
    if not close_enemies:
        return base_outcome["survived_steps"], base_outcome["comp_size"], len(base_outcome["step1_pos"])

    close_enemies.sort(key=lambda ep: abs(ep["x"] - mx) + abs(ep["y"] - my))
    primary_enemy = close_enemies[0]
    eid = primary_enemy["id"]
    ex, ey = primary_enemy["x"], primary_enemy["y"]

    worst_steps = base_outcome["survived_steps"]
    worst_comp = base_outcome["comp_size"]
    worst_s1 = len(base_outcome["step1_pos"])

    enemy_candidates = ["bomb"]
    for dname, (dx, dy) in DIRS.items():
        if abs((ex + dx) - mx) + abs((ey + dy) - my) < abs(ex - mx) + abs(ey - my):
            enemy_candidates.append(dname)
        elif primary_enemy["can_kick"]:
            enemy_candidates.append(dname)

    for eact in enemy_candidates:
        adv_out = simulate_action_outcome(
            state=state,
            me=me,
            action=action,
            crush_schedule=crush_schedule,
            assumed_enemy_actions={eid: eact},
            horizon=6,
        )
        st = adv_out["survived_steps"]
        cp = adv_out["comp_size"]
        s1 = len(adv_out["step1_pos"])
        if (st, cp, s1) < (worst_steps, worst_comp, worst_s1):
            worst_steps, worst_comp, worst_s1 = st, cp, s1

    return worst_steps, worst_comp, worst_s1


def count_bomb_brick_hits(grid: list[list[str]], bx: int, by: int, radius: int, w: int, h: int, already_targeted: set[tuple[int, int]]) -> int:
    hits = 0
    for dx, dy in DIRS.values():
        for step in range(1, radius + 1):
            nx, ny = bx + dx * step, by + dy * step
            if not (0 <= nx < w and 0 <= ny < h):
                break
            tile = grid[ny][nx]
            if tile == "@":
                break
            if tile == "#":
                if (nx, ny) not in already_targeted:
                    hits += 1
                break
    return hits


def can_escape_local_bomb(
    grid: list[list[str]],
    bx: int,
    by: int,
    radius: int,
    bombs_set: set[tuple[int, int]],
    other_pos: set[tuple[int, int]],
    w: int,
    h: int,
) -> bool:
    blast = {(bx, by)}
    for dx, dy in DIRS.values():
        for step in range(1, radius + 1):
            nx, ny = bx + dx * step, by + dy * step
            if not (0 <= nx < w and 0 <= ny < h):
                break
            if grid[ny][nx] == "@":
                break
            blast.add((nx, ny))
            if grid[ny][nx] == "#":
                break

    q = deque([(bx, by, 0)])
    visited = {(bx, by)}
    while q:
        cx, cy, d = q.popleft()
        if (cx, cy) not in blast:
            return True
        if d >= 3:
            continue
        for dx, dy in DIRS.values():
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                if grid[ny][nx] == "." and (nx, ny) not in bombs_set:
                    if d == 0 and (nx, ny) in other_pos:
                        continue
                    visited.add((nx, ny))
                    q.append((nx, ny, d + 1))
    return False


def bfs_distances_and_targets(
    start_pos: tuple[int, int],
    grid: list[list[str]],
    bombs_set: set[tuple[int, int]],
    danger_cells: set[tuple[int, int]],
    w: int,
    h: int,
):
    dist = {start_pos: 0}
    q = deque([start_pos])
    while q:
        cx, cy = q.popleft()
        d = dist[(cx, cy)]
        for dx, dy in DIRS.values():
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < w and 0 <= ny < h):
                continue
            if (nx, ny) in dist:
                continue
            if grid[ny][nx] != ".":
                continue
            if (nx, ny) in bombs_set:
                continue
            if d == 0 and (nx, ny) in danger_cells:
                continue
            dist[(nx, ny)] = d + 1
            q.append((nx, ny))
    return dist


def compute_voronoi_territory(
    my_pos: tuple[int, int],
    enemies: list[dict],
    grid: list[list[str]],
    bombs_set: set[tuple[int, int]],
    crush_schedule: dict[tuple[int, int], int],
    turn: int,
    w: int,
    h: int,
) -> tuple[int, int]:
    if not enemies:
        return 0, 0

    my_dist = {my_pos: 0}
    q = deque([my_pos])
    while q:
        cx, cy = q.popleft()
        d = my_dist[(cx, cy)]
        for dx, dy in DIRS.values():
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in my_dist:
                if grid[ny][nx] == "." and (nx, ny) not in bombs_set:
                    my_dist[(nx, ny)] = d + 1
                    q.append((nx, ny))

    en_dist = {}
    eq = deque()
    for ep in enemies:
        epos = (ep["x"], ep["y"])
        en_dist[epos] = 0
        eq.append(epos)
    while eq:
        cx, cy = eq.popleft()
        d = en_dist[(cx, cy)]
        for dx, dy in DIRS.values():
            nx, ny = cx + dx, cy + dy
            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in en_dist:
                if grid[ny][nx] == "." and (nx, ny) not in bombs_set:
                    en_dist[(nx, ny)] = d + 1
                    eq.append((nx, ny))

    my_cells = 0
    my_safe_endgame_cells = 0
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if grid[y][x] != ".":
                continue
            md = my_dist.get((x, y), 999)
            ed = en_dist.get((x, y), 999)
            if md == 999 and ed == 999:
                continue
            if md < ed:
                my_cells += 1
                ct = crush_schedule.get((x, y), 9999)
                if ct > turn + 25:
                    my_safe_endgame_cells += 1
    return my_cells, my_safe_endgame_cells


def decide(state: dict) -> str:
    my_id = state["you"]
    players = state["players"]
    me = None
    for p in players:
        if p["id"] == my_id:
            me = p
            break
    if me is None:
        return "stay"

    w, h = state["width"], state["height"]
    turn = state["turn"]
    if turn == 1:
        _HISTORY.clear()
    hist = _HISTORY.setdefault(my_id, deque(maxlen=8))
    hist.append((me["x"], me["y"]))

    crush_schedule = get_crush_schedule(state)
    other_players = [p for p in players if p["id"] != my_id]
    other_pos = {(p["x"], p["y"]) for p in other_players}
    grid = [list(row) for row in state["grid"]]

    stay_outcome = simulate_action_outcome(state, me, "stay", crush_schedule, horizon=6)
    base_frames = stay_outcome["frames"]

    already_targeted_bricks = set()
    all_pending_flames = set()
    imm_danger = set(base_frames[0]["flames"])
    if base_frames[0]["crushed"]:
        imm_danger.add(base_frames[0]["crushed"])

    for f in base_frames:
        already_targeted_bricks |= f["bricks_hit"]
        all_pending_flames |= f["flames"]
        if f["crushed"]:
            all_pending_flames.add(f["crushed"])

    outcomes = {}
    for action in ACTIONS:
        if action == "bomb" and not me["can_bomb"]:
            continue
        out = simulate_action_outcome(state, me, action, crush_schedule, horizon=6)
        if action in DIRS and not out["move_succeeded"] and not out["kicked_bomb"]:
            continue
        if action == "bomb" and not out["placed_bomb"]:
            continue

        adv_steps, adv_comp, adv_s1 = evaluate_worst_case_vs_enemies(
            state, me, action, out, crush_schedule
        )
        out["adv_steps"] = adv_steps
        out["adv_comp"] = adv_comp
        out["adv_s1"] = adv_s1
        outcomes[action] = out

    if not outcomes:
        return "stay"

    max_survived = max(o["survived_steps"] for o in outcomes.values())

    enemy_outcomes_stay = {}
    for ep in other_players:
        ep_bombs = {(b["x"], b["y"]) for b in state["bombs"]}
        ep_surv, ep_comp, _, _, _ = analyze_survival(
            start_pos=(ep["x"], ep["y"]),
            frames=base_frames,
            initial_bombs_after_phase3=ep_bombs,
            other_players_pos={(p["x"], p["y"]) for p in players if p["id"] != ep["id"]},
            w=w,
            h=h,
        )
        enemy_outcomes_stay[ep["id"]] = (ep_surv, ep_comp)

    best_action = "stay"
    best_score = -1e18

    for action, out in outcomes.items():
        score = 0.0
        surv = out["survived_steps"]
        comp = out["comp_size"]
        adv_surv = out["adv_steps"]
        adv_comp = out["adv_comp"]
        adv_s1 = out["adv_s1"]
        px, py = out["pos"]

        # 1. Primary Survival Score
        if surv < max_survived:
            score -= (max_survived - surv) * 1_000_000.0
        score += surv * 100_000.0

        # 2. Adversarial Survival (if enemy attacks/blocks us this turn)
        if adv_surv < 6:
            score -= (6 - adv_surv) * 80_000.0
        if adv_comp < 4:
            score -= (4 - adv_comp) * 12_000.0
        if adv_s1 <= 1 and len(other_players) > 0:
            score -= 6_000.0

        # 3. Reachable Safe Space (Anti-Cornering)
        if comp == 0:
            score -= 500_000.0
        elif comp < 5:
            score += comp * 4_500.0
        else:
            score += 22_500.0 + min(comp, 40) * 180.0

        s1_count = len(out["step1_pos"])
        score += min(s1_count, 4) * 800.0

        esc_step = out["first_escape_step"]
        if esc_step > 0:
            if esc_step >= 999:
                score -= 50_000.0
            else:
                score -= esc_step * 2_200.0

        if (px, py) in all_pending_flames and action != "bomb" and not out["kicked_bomb"]:
            score -= 1_200.0

        # 4. Crush Zone Awareness & Endgame Last-Tile Dominance
        cell_crush_turn = crush_schedule.get((px, py), 9999)
        turns_until_crush = cell_crush_turn - turn
        if turns_until_crush <= 10:
            score -= (11 - turns_until_crush) * 4_200.0
        elif turns_until_crush <= 28:
            score -= (29 - turns_until_crush) * 350.0
        elif turn >= state["crush_start"] + 40:
            # In late endgame, directly prefer standing on the tile that crushes latest!
            score += min(turns_until_crush, 60) * 260.0

        if out["alive_end_pos"]:
            best_end_crush = max(crush_schedule.get(pos, 9999) for pos in out["alive_end_pos"])
            if best_end_crush - turn < 30:
                score += (best_end_crush - turn) * 450.0
            else:
                score += 13_500.0 + min(best_end_crush - turn, 120) * 45.0

        # 5. Immediate Item Pickup Value
        picked = out["picked_item"]
        if picked is not None:
            if picked == "kick" and not me["can_kick"]:
                score += 9_500.0
            elif picked == "bomb" and me["bomb_limit"] < state.get("max_bombs", 6):
                score += 6_500.0 if me["bomb_limit"] < 3 else 2_800.0
            elif picked == "fire" and me["radius"] < state.get("max_radius", 8):
                score += 5_800.0 if me["radius"] < 4 else 2_500.0
            else:
                score += 600.0

        # 6. Bomb Placement & Kick Evaluation
        if out["placed_bomb"] or out["kicked_bomb"]:
            if out["placed_bomb"] and (adv_surv < 6 or comp < 3 or s1_count < 1):
                score -= 60_000.0
            else:
                bricks_destroyed = 0
                if out["placed_bomb"]:
                    bricks_destroyed = count_bomb_brick_hits(
                        grid, px, py, out["eff_radius"], w, h, already_targeted_bricks
                    )
                    early_mult = 1.5 if turn < 70 else 0.8
                    score += bricks_destroyed * 2_400.0 * early_mult

                enemy_impact = 0.0
                for ep in other_players:
                    eid = ep["id"]
                    base_esurv, base_ecomp = enemy_outcomes_stay[eid]
                    new_esurv, new_ecomp, _, _, _ = analyze_survival(
                        start_pos=(ep["x"], ep["y"]),
                        frames=out["frames"],
                        initial_bombs_after_phase3=out["bombs_after_phase3"],
                        other_players_pos={(p["x"], p["y"]) for p in players if p["id"] != eid},
                        w=w,
                        h=h,
                    )
                    if new_esurv < base_esurv:
                        enemy_impact += (base_esurv - new_esurv) * 10_000.0
                    if new_ecomp < base_ecomp:
                        enemy_impact += (base_ecomp - new_ecomp) * 360.0
                        if new_ecomp <= 2:
                            enemy_impact += 7_000.0

                score += enemy_impact

                if out["kicked_bomb"]:
                    if (px, py) in all_pending_flames and out["first_escape_step"] == 0:
                        score += 7_500.0
                    elif enemy_impact > 0:
                        score += 4_200.0
                    else:
                        score += 400.0

                if out["placed_bomb"] and bricks_destroyed == 0 and enemy_impact < 250.0:
                    score -= 3_500.0

        # 7. Territory / Voronoi Control
        if len(other_players) <= 2 or turn >= state["crush_start"] - 20:
            my_terr, my_endgame_terr = compute_voronoi_territory(
                my_pos=(px, py),
                enemies=other_players,
                grid=grid,
                bombs_set=out["bombs_after_phase3"],
                crush_schedule=crush_schedule,
                turn=turn,
                w=w,
                h=h,
            )
            score += my_terr * 60.0 + my_endgame_terr * 95.0

        # 8. Navigation Heuristics (Items, Safe-to-Bomb Brick Spots, Center / Enemy Positioning)
        dist_map = bfs_distances_and_targets(
            start_pos=(px, py),
            grid=grid,
            bombs_set=out["bombs_after_phase3"],
            danger_cells=imm_danger,
            w=w,
            h=h,
        )

        # Item attraction
        best_item_pull = 0.0
        for it in state["items"]:
            ipos = (it["x"], it["y"])
            if ipos == (px, py):
                continue
            if ipos in out["frames"][0]["flames"]:
                continue
            d = dist_map.get(ipos, 999)
            if d < 999:
                kind = it["kind"]
                if kind == "kick" and not me["can_kick"]:
                    val = 4200.0
                elif kind == "bomb" and me["bomb_limit"] < 3:
                    val = 3000.0
                elif kind == "fire" and me["radius"] < 4:
                    val = 2600.0
                else:
                    val = 1100.0
                pull = val / (d + 1.0)
                if pull > best_item_pull:
                    best_item_pull = pull
        score += best_item_pull

        # Brick farming attraction: ONLY pull toward spots where a bomb is actually escapable!
        if me["can_bomb"] or me["active_bombs"] < me["bomb_limit"]:
            best_brick_pull = 0.0
            for (cx, cy), d in dist_map.items():
                if d == 0 or d > 12:
                    continue
                if (cx, cy) in all_pending_flames:
                    continue
                if crush_schedule.get((cx, cy), 9999) - turn <= 14:
                    continue
                bhits = count_bomb_brick_hits(grid, cx, cy, me["radius"], w, h, already_targeted_bricks)
                if bhits > 0:
                    if can_escape_local_bomb(
                        grid, cx, cy, me["radius"], out["bombs_after_phase3"], other_pos, w, h
                    ):
                        val = (bhits * 850.0) / (d + 1.2)
                        if val > best_brick_pull:
                            best_brick_pull = val
            score += best_brick_pull

        # Enemy & Center positioning
        if other_players:
            min_edist = min(abs(ep["x"] - px) + abs(ep["y"] - py) for ep in other_players)
            if len(other_players) == 1:
                if min_edist > 4:
                    score -= min_edist * 45.0
                elif min_edist == 1:
                    score -= 120.0
            else:
                if min_edist <= 2:
                    score -= (3 - min_edist) * 180.0
                elif min_edist > 6:
                    score -= (min_edist - 6) * 20.0

        cx_mid, cy_mid = w // 2, h // 2
        dist_center = abs(px - cx_mid) + abs(py - cy_mid)
        if turn >= state["crush_start"] - 25:
            score -= dist_center * 150.0
        else:
            score -= dist_center * 12.0

        # Anti-oscillation / anti-camping penalty when nothing is happening
        if hist.count((px, py)) >= 2 and not state["bombs"]:
            score -= hist.count((px, py)) * 45.0

        if action == "stay":
            score -= 8.0

        if score > best_score:
            best_score = score
            best_action = action

    return best_action
