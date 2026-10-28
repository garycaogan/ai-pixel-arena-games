"""Bomber II: deterministic simultaneous rules, with no I/O during play."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import asdict, dataclass
import copy
import json
import math
from pathlib import Path
import random

DIRS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}
ACTIONS = (*DIRS, "bomb", "stay")
LETTER = dict(zip(ACTIONS, "UDLRBS"))
FROM_LETTER = {v: k for k, v in LETTER.items()}
ITEMS = ("fire", "bomb", "kick")
DEFAULTS = {"size": 13, "max_turns": 270, "bomb_fuse": 3, "blast_radius": 2,
            "bomb_limit": 1, "max_radius": 8, "max_bombs": 6, "brick_density": .65,
            "item_density": .40, "crush_start": 80, "crush_skip_initial_steel": True}


def configuration(n, config=None):
    out = dict(DEFAULTS)
    out.update(config or {})
    for key in ("size", "max_turns", "bomb_fuse", "blast_radius", "bomb_limit",
                "max_radius", "max_bombs", "crush_start"):
        if type(out[key]) is not int or out[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    if out["size"] < 5 or out["size"] % 2 != 1:
        raise ValueError("size must be odd and >= 5")
    if out["blast_radius"] > out["max_radius"] or out["bomb_limit"] > out["max_bombs"]:
        raise ValueError("initial upgrades exceed caps")
    for key in ("brick_density", "item_density"):
        if type(out[key]) not in (float, int) or not 0 <= out[key] <= 1:
            raise ValueError(f"{key} must be in [0, 1]")
    if "crush_rotation" in out and (type(out["crush_rotation"]) is not int or out["crush_rotation"] not in range(4)):
        raise ValueError("crush_rotation must be 0, 1, 2 or 3")
    if type(out["crush_skip_initial_steel"]) is not bool:
        raise ValueError("crush_skip_initial_steel must be boolean")
    if type(n) is not int or not 2 <= n <= (out["size"] - 2) ** 2:
        raise ValueError("player count must fit interior, with at least two players")
    return copy.deepcopy(out)


def spiral(size):
    """Geometric clockwise traversal, before initial-terrain filtering."""
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


def orbit(x, y, w):
    return {(x, y), (w - 1 - y, x), (w - 1 - x, w - 1 - y), (y, w - 1 - x)}


@dataclass
class Player:
    id: int
    x: int
    y: int
    alive: bool = True
    death_turn: int = 0
    death_cause: str = ""
    killer: int | None = None
    kills: int = 0
    bombs: int = 0                 # cumulative planted bombs
    bricks: int = 0
    pickups: int = 0
    radius: int = 2
    bomb_limit: int = 1
    can_kick: bool = False


@dataclass
class Bomb:
    id: int
    owner: int
    x: int
    y: int
    fuse: int
    radius: int
    direction: str | None = None

    def public(self):
        return {**asdict(self), "sliding": self.direction is not None}


class Game:
    @classmethod
    def new(cls, n, seed, config=None):
        g = cls()
        g.config = cfg = configuration(n, config)
        g.n, g.seed, g.width, g.height = n, seed, cfg["size"], cfg["size"]
        w = g.width
        g.turn, g.next_bomb = 0, 0
        g.bombs, g.events, g.flames = [], [], []
        g.items, g._hidden = {}, {}
        cfg.setdefault("crush_rotation", seed % 4)
        g.crushed = []
        rng = random.Random(seed)
        g.grid = [["@" if x in (0, w - 1) or y in (0, w - 1) or (x % 2 == 0 and y % 2 == 0)
                   else "." for x in range(w)] for y in range(w)]
        for y in range(w):
            for x in range(w):
                cells = orbit(x, y, w)
                if (x, y) == min(cells) and g.grid[y][x] == "." and rng.random() < cfg["brick_density"]:
                    for a, b in cells:
                        g.grid[b][a] = "#"
        corners = [(1, 1), (w - 2, 1), (w - 2, w - 2), (1, w - 2)]
        if n in (2, 4):
            points = [corners[0], corners[2]] if n == 2 else corners
            # Clear all four identical 3x3 interior pockets, retaining lattice steel.
            pockets = [(x, y) for y in range(1, 4) for x in range(1, 4)]
            for x, y in pockets:
                for a, b in orbit(x, y, w):
                    if g.grid[b][a] != "@":
                        g.grid[b][a] = "."
        else:
            points = []
            center, radius = (w - 1) / 2, (w - 1) * .39
            for i in range(n):
                angle = -math.pi / 2 + 2 * math.pi * i / n
                target = round(center + radius * math.cos(angle)), round(center + radius * math.sin(angle))
                choices = [(x, y) for y in range(1, w - 1) for x in range(1, w - 1) if (x, y) not in points]
                points.append(min(choices, key=lambda p: (abs(p[0] - target[0]) + abs(p[1] - target[1]), p)))
            # Optional ring layouts also keep the terrain rotationally symmetric.
            for x, y in points:
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        a, b = x + dx, y + dy
                        if 0 < a < w - 1 and 0 < b < w - 1:
                            for u, v in orbit(a, b, w):
                                g.grid[v][u] = "."
        # Freeze the path from the FINAL opening terrain, including optional
        # ring-spawn clearings. Later broken bricks stay in this same schedule.
        g._spiral = spiral(w)
        for _ in range(cfg["crush_rotation"]):
            g._spiral = [(w - 1 - y, x) for x, y in g._spiral]
        if cfg["crush_skip_initial_steel"]:
            g._spiral = [(x, y) for x, y in g._spiral if g.grid[y][x] != "@"]
        # Hidden contents are allocated only after spawn pockets are final.
        for y in range(w):
            for x in range(w):
                cells = orbit(x, y, w)
                if (x, y) == min(cells) and g.grid[y][x] == "#" and rng.random() < cfg["item_density"]:
                    kind = rng.choices(ITEMS, (4, 4, 2))[0]
                    for q in cells:
                        g._hidden[q] = kind
        g.players = [Player(i, x, y, radius=cfg["blast_radius"], bomb_limit=cfg["bomb_limit"])
                     for i, (x, y) in enumerate(points)]
        return g

    def alive(self):
        return [p for p in self.players if p.alive]

    def over(self):
        return len(self.alive()) <= 1 or self.turn >= self.config["max_turns"]

    def fallback(self, i):
        return "stay"

    def upcoming_crush(self):
        index = max(0, self.turn - self.config["crush_start"] + 1)
        return [{"x": x, "y": y, "turn": self.config["crush_start"] + j}
                for j, (x, y) in enumerate(self._spiral[index:index + 5], start=index)]

    def _public_players(self, living_only=False):
        counts = Counter(b.owner for b in self.bombs)
        return [{**asdict(p), "active_bombs": counts[p.id], "can_bomb": counts[p.id] < p.bomb_limit}
                for p in self.players if p.alive or not living_only]

    def state_for(self, i):
        return {"turn": self.turn + 1, "max_turns": self.config["max_turns"],
                "width": self.width, "height": self.height, "num_players": self.n, "you": i,
                "grid": ["".join(r) for r in self.grid], "players": self._public_players(True),
                "bombs": [b.public() for b in self.bombs],
                "items": [{"x": x, "y": y, "kind": kind} for (x, y), kind in sorted(self.items.items())],
                "bomb_fuse": self.config["bomb_fuse"], "max_radius": self.config["max_radius"],
                "max_bombs": self.config["max_bombs"], "crush_start": self.config["crush_start"],
                "crush_rotation": self.config["crush_rotation"],
                "next_crush": self.upcoming_crush(), "crushed": [list(q) for q in self.crushed]}

    def _die(self, p, cause, killer, ev):
        p.alive, p.death_turn, p.death_cause, p.killer = False, self.turn, cause, killer
        if killer is not None and killer != p.id:
            self.players[killer].kills += 1
        ev.append({"t": self.turn, "type": "die", "id": p.id, "cause": cause,
                   "by": killer, "at": [p.x, p.y]})

    def _floor(self, q):
        x, y = q
        return 0 <= x < self.width and 0 <= y < self.height and self.grid[y][x] == "."

    def step(self, moves):
        # Referee stops at over(); scripted demos may deliberately continue.
        self.turn += 1
        ev, alive = [], self.alive()
        actions = {p.id: moves.get(p.id) if moves.get(p.id) in ACTIONS else "stay" for p in alive}
        occupied = {(p.x, p.y) for p in alive}
        by_cell = {(b.x, b.y): b for b in self.bombs}
        wants, kicks = {}, defaultdict(list)
        old = {b.id for b in self.bombs}
        for p in alive:
            action = actions[p.id]
            if action in DIRS:
                dx, dy = DIRS[action]
                q = p.x + dx, p.y + dy
                if q in by_cell:
                    if p.can_kick:
                        kicks[by_cell[q].id].append((p.id, action))
                elif self._floor(q) and q not in occupied:
                    wants[p.id] = q
        counts = Counter(wants.values())
        for p in alive:
            if p.id in wants and counts[wants[p.id]] == 1:
                p.x, p.y = wants[p.id]
        for b in self.bombs:
            if b.id in kicks:
                requests = kicks[b.id]
                b.direction = requests[0][1] if len(requests) == 1 else None
                ev.append({"t": self.turn, "type": "kick", "bomb": b.id, "at": [b.x, b.y],
                           "ids": [i for i, _ in requests], "direction": b.direction,
                           "cancelled": len(requests) != 1})
        for p in alive:
            q = p.x, p.y
            kind = self.items.pop(q, None)
            if kind is not None:
                p.pickups += 1
                if kind == "fire":
                    p.radius = min(self.config["max_radius"], p.radius + 1)
                elif kind == "bomb":
                    p.bomb_limit = min(self.config["max_bombs"], p.bomb_limit + 1)
                else:
                    p.can_kick = True
                ev.append({"t": self.turn, "type": "pickup", "id": p.id, "at": list(q), "kind": kind})
        counts = Counter(b.owner for b in self.bombs)
        for p in alive:
            if actions[p.id] == "bomb" and counts[p.id] < p.bomb_limit and (p.x, p.y) not in by_cell:
                b = Bomb(self.next_bomb, p.id, p.x, p.y, self.config["bomb_fuse"], p.radius)
                self.next_bomb += 1
                self.bombs.append(b)
                p.bombs += 1
                ev.append({"t": self.turn, "type": "bomb", "id": p.id, "bomb": b.id, "at": [p.x, p.y]})
        # All sliding proposals use the same bomb snapshot; no following/swapping.
        blocked = {(b.x, b.y) for b in self.bombs} | {(p.x, p.y) for p in alive} | set(self.items)
        slides = {}
        for b in self.bombs:
            if b.direction is not None:
                dx, dy = DIRS[b.direction]
                q = b.x + dx, b.y + dy
                if self._floor(q) and q not in blocked:
                    slides[b.id] = q
                else:
                    b.direction = None
        counts = Counter(slides.values())
        for b in self.bombs:
            if b.id in slides:
                if counts[slides[b.id]] == 1:
                    b.x, b.y = slides[b.id]
                else:
                    b.direction = None
        by_cell = {(b.x, b.y): b for b in self.bombs}
        for b in self.bombs:
            if b.id in old:
                b.fuse -= 1
        pending = deque(sorted((b for b in self.bombs if b.fuse <= 0), key=lambda b: b.id))
        detonated, flames, broken = set(), {}, {}
        while pending:
            b = pending.popleft()
            if b.id in detonated:
                continue
            detonated.add(b.id)
            cells = [(b.x, b.y)]
            for dx, dy in DIRS.values():
                for d in range(1, b.radius + 1):
                    q = x, y = b.x + dx * d, b.y + dy * d
                    if not (0 <= x < self.width and 0 <= y < self.height) or self.grid[y][x] == "@":
                        break
                    cells.append(q)
                    if self.grid[y][x] == "#":
                        broken.setdefault(q, []).append(b)
                        break
                    other = by_cell.get(q)
                    if other is not None:
                        pending.append(other)
                        break
            for q in cells:
                flames.setdefault(q, []).append(b)
            ev.append({"t": self.turn, "type": "explode", "bomb": b.id, "id": b.owner,
                       "at": [b.x, b.y], "cells": [list(q) for q in cells]})
        # Destroy only previously exposed items. Newly revealed loot survives this phase.
        for q in sorted(set(self.items) & set(flames)):
            kind = self.items.pop(q)
            ev.append({"t": self.turn, "type": "item_destroy", "kind": kind, "at": list(q), "cause": "blast"})
        for (x, y), sources in sorted(broken.items()):
            owner = min(sources, key=lambda b: b.id).owner
            self.grid[y][x] = "."
            self.players[owner].bricks += 1
            ev.append({"t": self.turn, "type": "brick", "id": owner, "at": [x, y]})
            kind = self._hidden.pop((x, y), None)
            if kind is not None:
                self.items[x, y] = kind
                ev.append({"t": self.turn, "type": "reveal", "kind": kind, "at": [x, y]})
        for p in alive:
            sources = flames.get((p.x, p.y))
            if sources:
                owner = min(sources, key=lambda b: b.id).owner
                self._die(p, "blast", owner if owner != p.id else None, ev)
        self.bombs = [b for b in self.bombs if b.id not in detonated]
        self.flames = [list(q) for q in sorted(flames)]
        index = self.turn - self.config["crush_start"]
        if 0 <= index < len(self._spiral):
            q = x, y = self._spiral[index]
            removed = [b.id for b in self.bombs if (b.x, b.y) == q]
            item = self.items.pop(q, None)
            self._hidden.pop(q, None)
            self.bombs = [b for b in self.bombs if (b.x, b.y) != q]
            self.grid[y][x] = "@"
            self.crushed.append(q)
            ev.append({"t": self.turn, "type": "crush", "at": list(q), "bombs": removed, "item": item})
            for p in self.alive():
                if (p.x, p.y) == q:
                    self._die(p, "crush", None, ev)
        self.events.extend(ev)
        return ev

    def placements(self):
        keys = [(self.config["max_turns"] + self.turn + 1 if p.alive else p.death_turn, p.kills)
                for p in self.players]
        return [1 + sum(other > key for other in keys) for key in keys]

    def result(self):
        return {"n": self.n, "seed": self.seed, "turns": self.turn, "place": self.placements(),
                "death": [None if p.alive else [p.death_turn, p.death_cause, p.killer] for p in self.players],
                "kills": [p.kills for p in self.players], "bombs": [p.bombs for p in self.players],
                "bricks": [p.bricks for p in self.players], "pickups": [p.pickups for p in self.players],
                "play": [{"bombs": p.bombs, "bricks": p.bricks, "pickups": p.pickups} for p in self.players]}

    def frame(self):
        state = self.state_for(0)
        state.update(turn=self.turn, players=self._public_players(), flames=copy.deepcopy(self.flames))
        state.pop("you")
        return state


def _record_config(config):
    # Records predating follow-up 1 saved config but had an all-cell spiral.
    # New records always freeze this flag; unconfigured scripts use new rules.
    if (config is not None and "crush_skip_initial_steel" not in config
            and "crush_rotation" in config
            and all(key in config for key in DEFAULTS if key != "crush_skip_initial_steel")):
        return {"crush_skip_initial_steel": False, **config}
    return config


def replay(n, seed, rows, config=None):
    g = Game.new(n, seed, _record_config(config))
    for row in rows:
        g.step({i: FROM_LETTER[c] for i, c in enumerate(row) if c in FROM_LETTER})
    return g


def export_game(g, rows, seats):
    frames = [g.frame()]
    for row in rows:
        g.step({i: FROM_LETTER[c] for i, c in enumerate(row) if c in FROM_LETTER})
        frames.append(g.frame())
    return {"game": "bomb_party", "kind": "bomb_party", "n": g.n, "seed": g.seed, "w": g.width, "h": g.height,
            "turns": g.turn, "max_turns": g.config["max_turns"], "config": copy.deepcopy(g.config),
            "seats": list(seats), "place": g.placements(), "frames": frames, "events": copy.deepcopy(g.events),
            "death": g.result()["death"], "kills": [p.kills for p in g.players]}


def export(record, upto=None):
    rows = record["moves"] if upto is None else record["moves"][:max(0, upto)]
    return export_game(Game.new(record["n"], record["seed"], _record_config(record.get("config"))), rows, record["seats"])
