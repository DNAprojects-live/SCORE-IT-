import re
from datetime import datetime, timezone
from functools import lru_cache
from typing import NamedTuple

import config


class UserError(Exception):
    pass


class Level(NamedTuple):
    number: int       # 1, 2, 3 ...
    progress: float   # 0..1 inside the current level, 1 at the top level
    need: int         # ELO left to the next level, 0 at the top level
    maxed: bool = False   # True when this is MAX_LEVEL

    @property
    def name(self):
        return f"Level {self.number}"


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_iso(value):
    value = re.sub(r"\.\d+", "", value).replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def elo_from_delta(delta):
    elo = config.START_ELO + int(delta)
    return elo if config.MIN_ELO is None else max(config.MIN_ELO, elo)


def level_of(elo):
    """Level 1 from 1000 to 1499, Level 2 from 1500 ... every LEVEL_STEP is a new one, up to MAX_LEVEL.
    Anyone under 1000 is still Level 1."""
    step, top = config.LEVEL_STEP, config.MAX_LEVEL
    idx = max(0, (elo - config.START_ELO) // step)
    if top and idx >= top - 1:
        return Level(top, 1.0, 0, True)
    low = config.START_ELO + idx * step
    prog = max(0.0, min(1.0, (elo - low) / step))
    return Level(idx + 1, prog, low + step - elo)


def rgb(value):
    return (value >> 16) & 255, (value >> 8) & 255, value & 255


def level_color(level):
    """Fixed color of a level badge as (r, g, b). Not affected by /color."""
    cols = config.LEVEL_COLORS
    return rgb(cols[min(max(level, 1), len(cols)) - 1])


def level_bar(level):
    """(left, right) colors of the progress bar gradient of a level, as (r, g, b)."""
    bars = config.LEVEL_BARS
    a, b = bars[min(max(level, 1), len(bars)) - 1]
    return rgb(a), rgb(b)


def mix(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def parse_color(text):
    """'#ffcc00', 'ffcc00', '#fc0' or a name from COLOR_PRESETS -> 0xRRGGBB"""
    t = text.strip().lower().lstrip("#")
    if t in config.COLOR_PRESETS:
        return config.COLOR_PRESETS[t]
    if re.fullmatch(r"[0-9a-f]{3}", t):
        t = "".join(ch * 2 for ch in t)
    if not re.fullmatch(r"[0-9a-f]{6}", t):
        raise UserError("That is not a color code. Use hex like #FFCC00 or a name: "
                        + ", ".join(config.COLOR_PRESETS) + ".")
    value = int(t, 16)
    r, g, b = rgb(value)
    if 0.299 * r + 0.587 * g + 0.114 * b < 60:
        raise UserError("That color is too dark, it would vanish on the dark cards. Pick a brighter one.")
    return value


def fit(text, limit):
    text = str(text)
    return text if len(text) <= limit else text[:limit - 2] + ".."


@lru_cache(maxsize=None)
def slots(tactic):
    lines = config.TACTICS[tactic][1]
    out = [("GK", 0.5, 0.92)]
    spread = {2: 0.42, 3: 0.62, 4: 0.78, 5: 0.86}
    for i, (kind, count) in enumerate(lines):
        y = 0.72 - 0.59 * i / (len(lines) - 1) if len(lines) > 1 else 0.45
        for j, pos in enumerate(config.POSITION_NAMES[(kind, count)]):
            x = 0.5 if count == 1 else 0.5 - spread[count] / 2 + spread[count] * j / (count - 1)
            out.append((pos, x, y))
    return out


def tactic_label(tactic):
    return f"{tactic} ({config.TACTICS[tactic][0]})"
