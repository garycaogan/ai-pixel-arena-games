"""Four actual-engine demonstrations with complete seekable frame arrays."""
from .engine import Bomb, Game, LETTER, Player, export_game, spiral


def setup(points, **config):
    g = Game.new(len(points), 0, {"size": 9, "max_turns": 30, "crush_start": 1000, **config})
    g.grid = [["."] * 9 for _ in range(9)]
    g._spiral = spiral(9)
    g._hidden = {}
    g.players = [Player(i, *p) for i, p in enumerate(points)]
    return g


def run(g, script):
    return export_game(g, ["".join(LETTER[a] for a in row) for row in script], ["baseline"] * g.n)


def build():
    loot = setup([(2, 4), (7, 7)])
    loot.grid[4][4] = "#"
    loot._hidden[4, 4] = "fire"
    kick = setup([(2, 4), (7, 7)])
    kick.items[3, 4] = "kick"
    kick.bombs = [Bomb(0, 1, 4, 4, 5, 2)]
    kick.next_bomb = 1
    chain = setup([(1, 1), (5, 5)])
    chain.bombs = [Bomb(0, 0, 2, 4, 1, 3), Bomb(1, 1, 5, 4, 8, 3)]
    chain.next_bomb = 2
    crush = setup([(1, 0), (4, 4)], crush_start=1)
    return {
        "loot": run(loot, [["bomb", "stay"], ["up", "stay"], ["right", "stay"],
                            ["right", "stay"], ["down", "stay"]]),
        "kick": run(kick, [["right", "stay"], ["right", "stay"], ["stay", "stay"],
                           ["stay", "stay"], ["stay", "stay"]]),
        "chain": run(chain, [["stay", "stay"]] * 2),
        "crush": run(crush, [["stay", "stay"]] * 6),
    }


make_all = all_demos = build
