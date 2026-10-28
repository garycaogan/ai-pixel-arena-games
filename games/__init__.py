"""Game package discovery without importing bots or starting processes."""
from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class GamePackage:
    code: str
    path: Path
    engine: object

    @property
    def formats(self):
        return json.loads((self.path / "formats.json").read_text(encoding="utf-8"))

    @property
    def rules(self):
        return [line.strip().lstrip("- ") for line in (self.path / "rules.md").read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.lstrip().startswith("#")]

    def config(self, kind, overrides=None, n=None):
        if kind not in ("duel", "melee"):
            raise ValueError(f"Unknown format: {kind}")
        value = dict(self.formats[kind])
        value.update(overrides or {})
        value.pop("seats_per_game", None)  # 只管正赛怎么排座位（arena.tournament），不进引擎规则
        sizes = value.pop("sizes_by_players", None)
        if sizes and n is not None:
            value["size"] = next((size for upper, size in sizes if upper is None or n <= upper), value.get("size"))
        return value

    def bot_path(self, name, bots_dir=None):
        if bots_dir is not None:
            return Path(bots_dir).resolve() / f"{name}.py"
        if name == "baseline":
            return self.path / "baseline.py"
        return ROOT / self.formats.get("bots_dir", f"bots/{self.code}") / f"{name}.py"

    def demos(self):
        return importlib.import_module(f"games.{self.code}.demos").build()

    def analysis(self):
        """Optional package statistics; neutral arena metrics are the fallback."""
        if not (self.path / "analyze.py").is_file():
            return None
        return importlib.import_module(f"games.{self.code}.analyze")

    def export(self, rec, upto=None):
        return self.engine.export(rec, upto=upto)


@lru_cache(maxsize=None)
def load_game(code="snake"):
    code = code or "snake"
    if not re.fullmatch(r"[a-z][a-z0-9_]*", code):
        raise ValueError(f"Invalid game package code: {code!r}")
    path = Path(__file__).resolve().parent / code
    if not (path / "engine.py").is_file():
        raise ValueError(f"Game package not found: {code}")
    engine = importlib.import_module(f"games.{code}.engine")
    return GamePackage(code, path, engine)


def record_game(rec):
    """Old tank records predate the game field; snake records have length/ate."""
    return rec.get("game") or ("tank" if "hp" in rec and "play" in rec and "length" not in rec else "snake")
