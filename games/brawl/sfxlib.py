"""像素拳斗音效合成（打击、防御、必杀、超必杀、投、KO），样片工具 tools/sfx.py 和正片 video/build.py 共用。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "video"))
from chiptune import SR, tone, env, lowpass, noise, add, note  # noqa: E402,F401


def punch(buf, t, big, seed):
    n = noise(0.09 if not big else 0.16, seed)
    add(buf, t, lowpass(n, 0.35 if big else 0.55) * env(len(n), 0.001, 0, 7), 0.55 if big else 0.35)
    m = int(SR * (0.16 if big else 0.08))
    f = np.linspace(180 if big else 260, 50, m)
    add(buf, t, np.sin(2 * np.pi * np.cumsum(f) / SR) * env(m, 0.001, 0, 5), 0.7 if big else 0.4)


def block(buf, t, seed):
    n = noise(0.05, seed)
    add(buf, t, (n - lowpass(n, 0.2)) * env(len(n), 0.001, 0, 9), 0.35)
    s = tone(1800, 0.05, kind="sine")
    add(buf, t, s * env(len(s), 0.001, 0, 8), 0.12)


def whoosh(buf, t, seed, hi=False):
    n = noise(0.22, seed)
    e = np.sin(np.linspace(0, np.pi, len(n)))
    add(buf, t, lowpass(n, 0.12 if not hi else 0.3) * e, 0.35)


def rise(buf, t):
    for k, m in enumerate((72, 76, 79, 84, 88)):
        s = 0.6 * tone(note(m), 0.09, duty=0.25) + 0.4 * tone(note(m + 12), 0.09, kind="tri")
        add(buf, t + k * 0.06, s * env(len(s), 0.002, 0.3, 3), 0.18)
    whoosh(buf, t + 0.3, 99, True)


def slam(buf, t):
    punch(buf, t, True, 5)
    n = noise(0.5, 11)
    add(buf, t, lowpass(n, 0.06) * env(len(n), 0.002, 0, 3), 0.8)


def ko(buf, t):
    slam(buf, t)
    for k, m in enumerate((60, 55, 48)):
        s = tone(note(m), 0.35, duty=0.5)
        add(buf, t + 0.15 + k * 0.22, lowpass(s, 0.2) * env(len(s), 0.002, 0.2, 2), 0.25)


def event(buf, t, e, seed):
    """回放里一帧的一个事件 → 声音，放在 t 秒。"""
    k = e["type"]
    if k == "hit":
        punch(buf, t, e.get("big") or e.get("counter"), seed)
    elif k == "block":
        block(buf, t, seed)
    elif k == "special":
        whoosh(buf, t, seed)
    elif k == "super":
        rise(buf, t)
    elif k == "throw":
        whoosh(buf, t, seed)
        slam(buf, t + 0.45)
    elif k == "armor":
        punch(buf, t, True, seed)
        block(buf, t, seed + 1)
    elif k == "fight":
        rise(buf, t)
    elif k in ("crush", "clash"):
        block(buf, t, seed)
        punch(buf, t, True, seed)
    elif k == "round":
        ko(buf, t)
