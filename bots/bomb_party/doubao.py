from collections import deque

def decide(state):
    # Parse state
    me = next(p for p in state['players'] if p['id'] == state['you'])
    x, y = me['x'], me['y']
    W, H = state['width'], state['height']
    grid = state['grid']
    bombs = state['bombs']
    items = state['items']
    players = state['players']
    turn = state['turn']
    next_crush = state['next_crush']
    FUSE = state['bomb_fuse']
    R = me['radius']
    max_bombs = me['bomb_limit']
    active_bombs = me['active_bombs']
    can_bomb = (active_bombs < max_bombs) and not any(b['x'] == x and b['y'] == y for b in bombs)
    can_kick = me['can_kick']
    CRUSH_START = state['crush_start']
    is_late_game = turn >= CRUSH_START - 10

    # Constants
    DIRS = {'up': (0,-1), 'down': (0,1), 'left': (-1,0), 'right': (1,0)}
    ALL_ACTIONS = list(DIRS.keys()) + ['bomb', 'stay']
    INF = 10**18
    KICK_BONUS = 60
    ENEMY_HIT_BONUS = 40
    BRICK_BONUS = 12
    ITEM_BONUSES = {'kick': 50, 'fire': 30, 'bomb': 20}
    CENTER_BONUS = 25 if is_late_game else 5

    # Precompute all explosion areas and base danger times
    def get_explosion(px, py, r):
        area = set()
        area.add((px, py))
        for dx, dy in DIRS.values():
            for s in range(1, r+1):
                nx, ny = px + dx*s, py + dy*s
                if nx <0 or nx >= W or ny <0 or ny >= H:
                    break
                c = grid[ny][nx]
                if c == '@':
                    break
                area.add((nx, ny))
                if c == '#':
                    break
        return area

    # Step 1: Compute bomb explosion times (account for chain reactions)
    bomb_info = {}
    for b in bombs:
        area = get_explosion(b['x'], b['y'], b['radius'])
        # Account for maximum possible sliding area
        slide_area = set()
        if b['direction']:
            dx, dy = DIRS[b['direction']]
            sx, sy = b['x'], b['y']
            while True:
                nsx, nsy = sx + dx, sy + dy
                if not (0<=nsx<W and 0<=nsy<H and grid[nsy][nsx] == '.'):
                    break
                if any(ob['x'] == nsx and ob['y'] == nsy for ob in bombs if ob['id'] != b['id']):
                    break
                sx, sy = nsx, nsy
                slide_area.update(get_explosion(sx, sy, b['radius']))
        full_area = area.union(slide_area)
        bomb_info[b['id']] = {
            'x': b['x'], 'y': b['y'], 'fuse': b['fuse'],
            'area': full_area, 'triggered': False, 'time': b['fuse']
        }

    # Compute chain reactions
    changed = True
    while changed:
        changed = False
        for a_id, a in bomb_info.items():
            if a['triggered']:
                continue
            # Check if a is triggered by any other bomb
            for b_id, b in bomb_info.items():
                if a_id == b_id or not b['triggered']:
                    continue
                if (a['x'], a['y']) in b['area'] and a['time'] > b['time']:
                    a['time'] = b['time']
                    a['triggered'] = True
                    changed = True
                    break
            # If fuse runs out, trigger
            if not a['triggered'] and a['fuse'] == 0:
                a['triggered'] = True
                changed = True

    # Build danger map: earliest time any explosion hits the tile, INF if safe
    danger = [[INF]*W for _ in range(H)]
    for b in bomb_info.values():
        for (tx, ty) in b['area']:
            if b['time'] < danger[ty][tx]:
                danger[ty][tx] = b['time']

    # Add crush danger
    crush = {}
    for c in next_crush:
        cx, cy, ct = c['x'], c['y'], c['turn']
        t = ct - turn
        if t < danger[cy][cx]:
            danger[cy][cx] = t
        crush[(cx, cy)] = t

    # Forbidden tiles (walls, bombs, other players, dangerous tiles (<=1 turn to explode))
    def is_forbidden(nx, ny, ignore_bomb=False):
        if nx <0 or nx >= W or ny <0 or ny >= H:
            return True
        if grid[ny][nx] in ('#', '@'):
            return True
        if not ignore_bomb and any(b['x'] == nx and b['y'] == ny for b in bombs):
            return True
        if any(p['x'] == nx and p['y'] == ny for p in players if p['id'] != me['id']):
            return True
        if danger[ny][nx] <= 1:
            return True
        if (nx, ny) in crush and crush[(nx, ny)] <= 1:
            return True
        return False

    # Check if an action is safe: after taking action, there exists a path to safety within time
    def is_action_safe(action):
        ax, ay = x, y
        # Process action
        if action in DIRS:
            dx, dy = DIRS[action]
            nx, ny = x + dx, y + dy
            # Check if it's a bomb kick
            kick_bomb = next((b for b in bombs if b['x'] == nx and b['y'] == ny), None)
            if kick_bomb:
                if not can_kick:
                    # Can't kick, stay
                    ax, ay = x, y
                else:
                    # Kick, stay in place, bomb moves away
                    ax, ay = x, y
            else:
                # Normal move
                if not is_forbidden(nx, ny):
                    ax, ay = nx, ny
                else:
                    ax, ay = x, y
        elif action == 'bomb':
            if not can_bomb:
                return False
            # Stay in place, place bomb
            ax, ay = x, y

        # Time available to escape: danger time at (ax, ay)
        time_available = danger[ay][ax]
        if action == 'bomb':
            # Placed bomb has fuse FUSE, so explosion time is FUSE (since fuse decreases next turn)
            bomb_exp = get_explosion(ax, ay, R)
            for (tx, ty) in bomb_exp:
                if FUSE < danger[ty][tx]:
                    time_available = min(time_available, FUSE)
        if time_available <= 0:
            return False

        # BFS to find escape path
        visited = set()
        q = deque()
        q.append((ax, ay, 0))
        visited.add((ax, ay))
        while q:
            cx, cy, steps = q.popleft()
            if steps >= time_available:
                continue
            # If current tile is safe after explosion, we're good
            if danger[cy][cx] > time_available and (cx, cy) not in crush:
                return True
            # Move to adjacent tiles
            for dx, dy in DIRS.values():
                nx, ny = cx + dx, cy + dy
                if is_forbidden(nx, ny):
                    continue
                if (nx, ny) in visited:
                    continue
                visited.add((nx, ny))
                q.append((nx, ny, steps + 1))
        return False

    # Evaluate all safe actions
    safe_actions = []
    for action in ALL_ACTIONS:
        if not is_action_safe(action):
            continue
        # Calculate score
        score = 0
        ax, ay = x, y
        if action in DIRS:
            dx, dy = DIRS[action]
            nx, ny = x + dx, y + dy
            kick_bomb = next((b for b in bombs if b['x'] == nx and b['y'] == ny), None)
            if kick_bomb and can_kick:
                # Kicking bomb: check if it hits enemies or bricks
                sx, sy = nx, ny
                while True:
                    nsx, nsy = sx + dx, sy + dy
                    if is_forbidden(nsx, nsy, ignore_bomb=True):
                        break
                    sx, sy = nsx, nsy
                kick_area = get_explosion(sx, sy, kick_bomb['radius'])
                hits = sum(1 for p in players if p['id'] != me['id'] and (p['x'], p['y']) in kick_area)
                score += hits * KICK_BONUS
                bricks = sum(1 for (tx, ty) in kick_area if grid[ty][tx] == '#')
                score += bricks * BRICK_BONUS
            else:
                # Normal move
                if not is_forbidden(nx, ny):
                    ax, ay = nx, ny
            # Item bonus
            for i in items:
                d = abs(ax - i['x']) + abs(ay - i['y'])
                priority = ITEM_BONUSES[i['kind']]
                if i['kind'] == 'kick' and can_kick:
                    priority = 0
                if i['kind'] == 'fire' and me['radius'] >= state['max_radius']:
                    priority = 0
                if i['kind'] == 'bomb' and max_bombs >= state['max_bombs']:
                    priority = 0
                score += max(0, priority - d * 2)
            # Enemy distance bonus: keep distance 3-4
            if len(players) > 1:
                min_enemy_dist = min(abs(ax - p['x']) + abs(ay - p['y']) for p in players if p['id'] != me['id'])
                if 3 <= min_enemy_dist <= 4:
                    score += 15
                elif min_enemy_dist < 2:
                    score -= 20
            # Brick bonus
            min_brick_dist = min((abs(ax - bx) + abs(ay - by) for by in range(H) for bx in range(W) if grid[by][bx] == '#'), default=INF)
            score += max(0, 10 - min_brick_dist)
        elif action == 'bomb':
            # Bomb bonus: count bricks and enemies hit
            exp = get_explosion(x, y, R)
            bricks = sum(1 for (tx, ty) in exp if grid[ty][tx] == '#')
            enemies = sum(1 for p in players if p['id'] != me['id'] and (p['x'], p['y']) in exp)
            score += bricks * BRICK_BONUS + enemies * ENEMY_HIT_BONUS
            # Penalty for placing bomb without enough escape time
            if FUSE < 3:
                score -= 10
        # Center bonus
        cx, cy = W//2, H//2
        center_dist = abs(ax - cx) + abs(ay - cy)
        score += max(0, CENTER_BONUS - center_dist)
        # Crush avoidance bonus
        if (ax, ay) not in crush:
            score += 30
        else:
            score += crush[(ax, ay)] * 3
        # Add to list
        safe_actions.append((-score, action))  # Sort by negative score for ascending

    if not safe_actions:
        # All actions dangerous: pick the one with the longest time to live
        best = 'stay'
        best_t = -1
        for action in ALL_ACTIONS:
            ax, ay = x, y
            if action in DIRS:
                dx, dy = DIRS[action]
                nx, ny = x + dx, y + dy
                if not is_forbidden(nx, ny):
                    ax, ay = nx, ny
            t = danger[ay][ax]
            if (ax, ay) in crush:
                t = min(t, crush[(ax, ay)])
            if t > best_t:
                best_t = t
                best = action
        return best

    # Sort safe actions by score
    safe_actions.sort()
    top_actions = [a for (s, a) in safe_actions[:3]]

    # Priority rules
    # 1. Kick if it hits at least one enemy
    for a in top_actions:
        if a in DIRS and can_kick:
            dx, dy = DIRS[a]
            nx, ny = x + dx, y + ny
            if any(b['x'] == nx and b['y'] == ny for b in bombs):
                # Calculate where bomb goes
                sx, sy = nx, ny
                while True:
                    nsx, nsy = sx + dx, sy + dy
                    if is_forbidden(nsx, nsy, ignore_bomb=True):
                        break
                    sx, sy = nsx, nsy
                kick_area = get_explosion(sx, sy, R)
                if any(p['id'] != me['id'] and (p['x'], p['y']) in kick_area for p in players):
                    return a

    # 2. Place bomb if it hits at least one enemy or 2+ bricks, and not late game
    if 'bomb' in top_actions and can_bomb and not is_late_game:
        exp = get_explosion(x, y, R)
        enemies = sum(1 for p in players if p['id'] != me['id'] and (p['x'], p['y']) in exp)
        bricks = sum(1 for (tx, ty) in exp if grid[ty][tx] == '#')
        if enemies >= 1 or bricks >= 2:
            return 'bomb'

    # 3. Move to item if within 5 steps
    def find_path_to(target_set, max_depth=5):
        if not target_set:
            return None
        visited = set()
        q = deque()
        for a in top_actions:
            if a not in DIRS:
                continue
            dx, dy = DIRS[a]
            nx, ny = x + dx, y + dy
            if is_forbidden(nx, ny):
                continue
            if (nx, ny) in target_set:
                return a
            q.append((nx, ny, a, 1))
        while q:
            cx, cy, first, depth = q.popleft()
            if depth >= max_depth:
                continue
            if (cx, cy) in target_set:
                return first
            for dx, dy in DIRS.values():
                nx, ny = cx + dx, cy + dy
                if is_forbidden(nx, ny) or (nx, ny) in visited:
                    continue
                visited.add((nx, ny))
                q.append((nx, ny, first, depth + 1))
        return None

    # Target items
    item_targets = set()
    for i in items:
        if (i['kind'] == 'kick' and not can_kick) or \
           (i['kind'] == 'fire' and me['radius'] < state['max_radius']) or \
           (i['kind'] == 'bomb' and max_bombs < state['max_bombs']):
            item_targets.add((i['x'], i['y']))
    move = find_path_to(item_targets, max_depth=5)
    if move:
        return move

    # Target enemy positions if not late game
    if not is_late_game:
        enemy_targets = set()
        for p in players:
            if p['id'] != me['id']:
                # Add adjacent tiles to enemy (bomb placement spots)
                for dx, dy in DIRS.values():
                    nx, ny = p['x'] + dx, p['y'] + dy
                    if not is_forbidden(nx, ny):
                        enemy_targets.add((nx, ny))
        move = find_path_to(enemy_targets, max_depth=4)
        if move:
            return move

    # Target brick adjacent tiles if not late game
    if not is_late_game:
        brick_targets = set()
        for by in range(H):
            for bx in range(W):
                if grid[by][bx] == '#':
                    for dx, dy in DIRS.values():
                        nx, ny = bx + dx, by + dy
                        if not is_forbidden(nx, ny):
                            brick_targets.add((nx, ny))
        move = find_path_to(brick_targets, max_depth=3)
        if move:
            return move

    # Late game: prioritize center
    if is_late_game:
        cx, cy = W//2, H//2
        best = top_actions[0]
        best_dist = INF
        for a in top_actions:
            ax, ay = x, y
            if a in DIRS:
                dx, dy = DIRS[a]
                nx, ny = x + dx, y + dy
                if not is_forbidden(nx, ny):
                    ax, ay = nx, ny
            d = abs(ax - cx) + abs(ay - cy)
            if d < best_dist:
                best_dist = d
                best = a
        return best

    # Fallback to top action
    return top_actions[0]
