import os

from dotenv import load_dotenv

load_dotenv()


def _int(name, default=0):
    try:
        return int(os.getenv(name, "") or default)
    except ValueError:
        return default


BOT_NAME = "Score It!"
LEAGUE_NAME = "Real Futbol League"

TOKEN = os.getenv("DISCORD_TOKEN", "")
DB_PATH = os.getenv("DB_PATH", "rfl.db")
DEV_GUILD_ID = _int("DEV_GUILD_ID")

START_ELO = 1000
# ELO has no ceiling and no floor. Put a number here (for example 0) if you ever want a floor back.
MIN_ELO = None
# Levels work like on FACEIT. Everyone is Level 1 from the start, every LEVEL_STEP ELO is the next level:
# Level 2 at 1500, Level 3 at 2000 ... Level 10 at 5500. MAX_LEVEL is the top, set it to None for levels
# that never end.
LEVEL_STEP = 500
MAX_LEVEL = 10

POINTS = {
    "goal": 5,
    "assist": 2,
    "clean_sheet": 10,
    "win": 20,
    "loss": -15,
    "draw": 5,
}

# only these positions can get a clean sheet
CLEAN_SHEET_POSITIONS = {"GK"}

# The server owner can change the color of the cards and embeds with /color, this is what a server gets
# before that. The level badge and its bar are not affected, they use LEVEL_COLORS and LEVEL_BARS.
DEFAULT_COLOR = 0xFFCC00
COLOR_PRESETS = {
    "red": 0xE11D2A,
    "orange": 0xFF8A1C,
    "yellow": 0xFFCC00,
    "green": 0x3CDC62,
    "cyan": 0x22D3EE,
    "blue": 0x3B82F6,
    "purple": 0x9B5CF6,
    "pink": 0xF472B6,
    "white": 0xF5F5F5,
}

# Colors of the level badge, one per level (Level 1 first). The number and the ring use this color.
# The last color is used for every level after the list. /color never touches these.
LEVEL_COLORS = [
    0xBEBEBE, 0x6CD662, 0x32C85A, 0xFFDE24, 0xFFC81E,
    0xFFB020, 0xFF9614, 0xFF7010, 0xFF5014, 0xF42305,
]

# The progress bar under the badge is a gradient, (left color, right color) for each level.
LEVEL_BARS = [
    (0x8E8E8E, 0xD8D8D8), (0x4CBF45, 0xB4EE7A), (0x22A84A, 0x7BE38A), (0xF2B705, 0xFFEE70),
    (0xFFA800, 0xFFE055), (0xFF9500, 0xFFD84F), (0xFF7A00, 0xFFCB40), (0xFF6200, 0xFFC83F),
    (0xFF5A00, 0xFFC83F), (0xFF5B00, 0xFECC3F),
]

# formation a server starts with until someone runs /lineup tactic
DEFAULT_TACTIC = "4-3-3"

# tactic -> (format, lines from the back to the front). GK is always added.
# D defenders, DM holding mid, M mids, AM attacking mids, F forwards
TACTICS = {
    "2-1-1": ("5v5", [("D", 2), ("M", 1), ("F", 1)]),
    "1-2-1": ("5v5", [("D", 1), ("M", 2), ("F", 1)]),
    "2-2": ("5v5", [("D", 2), ("F", 2)]),
    "2-2-1": ("6v6", [("D", 2), ("M", 2), ("F", 1)]),
    "2-1-2": ("6v6", [("D", 2), ("M", 1), ("F", 2)]),
    "3-1-1": ("6v6", [("D", 3), ("M", 1), ("F", 1)]),
    "3-2-1": ("7v7", [("D", 3), ("M", 2), ("F", 1)]),
    "2-3-1": ("7v7", [("D", 2), ("M", 3), ("F", 1)]),
    "2-2-2": ("7v7", [("D", 2), ("M", 2), ("F", 2)]),
    "4-3-3": ("11v11", [("D", 4), ("M", 3), ("F", 3)]),
    "4-4-2": ("11v11", [("D", 4), ("M", 4), ("F", 2)]),
    "4-2-3-1": ("11v11", [("D", 4), ("DM", 2), ("AM", 3), ("F", 1)]),
    "4-1-4-1": ("11v11", [("D", 4), ("DM", 1), ("M", 4), ("F", 1)]),
    "3-5-2": ("11v11", [("D", 3), ("M", 5), ("F", 2)]),
    "3-4-3": ("11v11", [("D", 3), ("M", 4), ("F", 3)]),
    "5-3-2": ("11v11", [("D", 5), ("M", 3), ("F", 2)]),
}

# position names for a line, left to right
POSITION_NAMES = {
    ("D", 1): ["CB"],
    ("D", 2): ["LB", "RB"],
    ("D", 3): ["LCB", "CB", "RCB"],
    ("D", 4): ["LB", "LCB", "RCB", "RB"],
    ("D", 5): ["LWB", "LCB", "CB", "RCB", "RWB"],
    ("DM", 1): ["CDM"],
    ("DM", 2): ["LDM", "RDM"],
    ("M", 1): ["CM"],
    ("M", 2): ["LCM", "RCM"],
    ("M", 3): ["LCM", "CM", "RCM"],
    ("M", 4): ["LM", "LCM", "RCM", "RM"],
    ("M", 5): ["LM", "LCM", "CM", "RCM", "RM"],
    ("AM", 3): ["LAM", "CAM", "RAM"],
    ("F", 1): ["ST"],
    ("F", 2): ["LS", "RS"],
    ("F", 3): ["LW", "ST", "RW"],
}
