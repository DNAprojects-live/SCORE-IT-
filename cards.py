import io
import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont, ImageOps

from util import fit, level_bar, level_color, level_of, mix, rgb
import config

BG = (10, 10, 10)
PANEL = (20, 20, 20)
PANEL2 = (32, 32, 32)
EDGE = (58, 58, 58)
TEXT = (245, 245, 245)
MUTED = (128, 128, 128)
ACCENT = rgb(config.DEFAULT_COLOR)
GREEN = (58, 220, 98)
RED = (255, 62, 62)
GREY = (150, 150, 150)
DARK = (12, 12, 12)

# stats card (FACEIT widget look)
CARD = (30, 30, 32)
TILE = (44, 44, 47)
MUTED2 = (150, 150, 156)
GREEN2 = (74, 222, 128)
RED2 = (248, 84, 84)

FONTS_BOLD = ["assets/font-bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "C:/Windows/Fonts/arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
              "arialbd.ttf", "DejaVuSans-Bold.ttf"]
FONTS_REG = ["assets/font.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
             "C:/Windows/Fonts/arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
             "arial.ttf", "DejaVuSans.ttf"]


@lru_cache(maxsize=128)
def font(size, bold=True):
    for path in (FONTS_BOLD if bold else FONTS_REG):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default(size)


class Canvas:
    # everything is drawn at 2x and shrunk at the end so edges stay clean
    def __init__(self, w, h, bg=BG, scale=2):
        self.w, self.h, self.s = w, h, scale
        if bg is None:  # transparent, for cards with rounded corners
            self.img = Image.new("RGBA", (w * scale, h * scale), (0, 0, 0, 0))
        else:
            self.img = Image.new("RGB", (w * scale, h * scale), bg)
        self.d = ImageDraw.Draw(self.img)

    def box(self, b):
        x0, y0, x1, y1 = b
        return [min(x0, x1) * self.s, min(y0, y1) * self.s, max(x0, x1) * self.s, max(y0, y1) * self.s]

    def rect(self, b, fill=None, outline=None, width=2):
        self.d.rectangle(self.box(b), fill=fill, outline=outline, width=width * self.s)

    def ellipse(self, b, fill=None, outline=None, width=2):
        self.d.ellipse(self.box(b), fill=fill, outline=outline, width=width * self.s)

    def line(self, pts, fill, width=2):
        self.d.line([v * self.s for v in pts], fill=fill, width=width * self.s)

    def text(self, xy, text, size, fill=TEXT, anchor="la", bold=True, stroke=0):
        self.d.text((xy[0] * self.s, xy[1] * self.s), str(text), font=font(int(size * self.s), bold),
                    fill=fill, anchor=anchor, stroke_width=stroke * self.s, stroke_fill=(0, 0, 0))

    def width(self, text, size, bold=True):
        return self.d.textlength(str(text), font=font(int(size * self.s), bold)) / self.s

    def avatar(self, data, x, y, size, edge=EDGE):
        px = int(size * self.s)
        tile = Image.new("RGB", (px, px), PANEL2)
        if data:
            try:
                tile = ImageOps.fit(Image.open(io.BytesIO(data)).convert("RGB"), (px, px), Image.LANCZOS)
            except Exception:
                pass
        self.img.paste(tile, (int(x * self.s), int(y * self.s)))
        self.rect((x, y, x + size, y + size), outline=edge, width=3)

    def rrect(self, b, radius, fill=None, outline=None, width=2):
        self.d.rounded_rectangle(self.box(b), radius=radius * self.s, fill=fill, outline=outline,
                                 width=width * self.s)

    def level_badge(self, cx, cy, r, level, color, track=(52, 52, 55)):
        """FACEIT style level icon: a dark disc, a ring that is open at the bottom, and the level number
        in the middle. The higher the level, the more of the ring is lit: Level 10 is the whole ring."""
        k = self.s
        self.d.ellipse([(cx - r) * k, (cy - r) * k, (cx + r) * k, (cy + r) * k], fill=(18, 18, 20))
        thick = max(r * 0.17, 2)
        ro = r * 0.80                       # outer radius of the ring
        mid = ro - thick / 2
        bb = [(cx - ro) * k, (cy - ro) * k, (cx + ro) * k, (cy + ro) * k]
        top = config.MAX_LEVEL or 10
        start, full = 120, 300              # degrees, clockwise from 3 o'clock: starts bottom left, gap at the bottom
        sweep = full * min(max(level, 1), top) / top

        def arc(length, fill):
            self.d.arc(bb, start, start + length, fill=fill, width=int(thick * k))
            for ang in (start, start + length):     # round ends
                x = cx + mid * math.cos(math.radians(ang))
                y = cy + mid * math.sin(math.radians(ang))
                self.d.ellipse([(x - thick / 2) * k, (y - thick / 2) * k,
                                (x + thick / 2) * k, (y + thick / 2) * k], fill=fill)
        arc(full, track)
        arc(sweep, color)
        text = str(level)
        self.text((cx, cy + r * 0.02), text, self.fit_size(text, r * 0.72, 2 * (ro - thick) - 4), color, "mm")

    def avatar_round(self, data, cx, cy, size, ring, gap=3, ring_w=3, bg=CARD):
        k = self.s
        px = int(size * k)
        tile = Image.new("RGB", (px, px), PANEL2)
        if data:
            try:
                tile = ImageOps.fit(Image.open(io.BytesIO(data)).convert("RGB"), (px, px), Image.LANCZOS)
            except Exception:
                pass
        mask = Image.new("L", (px, px), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, px - 1, px - 1), fill=255)
        self.img.paste(tile, (int((cx - size / 2) * k), int((cy - size / 2) * k)), mask)
        o = size / 2 + gap + ring_w
        self.d.ellipse([(cx - o) * k, (cy - o) * k, (cx + o) * k, (cy + o) * k], outline=ring, width=ring_w * k)

    def gradient_bar(self, b, c0, c1, radius, t_end=1.0):
        """Rounded bar filled with a left to right gradient. With t_end below 1 the gradient stops part of
        the way, so a short bar looks like the start of a full one."""
        k = self.s
        x0, y0, x1, y1 = [int(v) for v in self.box(b)]  # box() is already scaled
        w, h = max(x1 - x0, 1), max(y1 - y0, 1)
        grad = Image.new("RGB", (w, h))
        gd = ImageDraw.Draw(grad)
        for x in range(w):
            gd.line([(x, 0), (x, h)], fill=mix(c0, c1, t_end * x / max(w - 1, 1)))
        mask = Image.new("L", (w, h), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=min(radius * k, h // 2), fill=255)
        self.img.paste(grad, (x0, y0), mask)

    def arrow(self, cx, cy, size, up, fill, width=5):
        """Thick arrow with round ends, pointing up or down."""
        half = size / 2
        sign = -1 if up else 1
        tip = cy + sign * half
        tail = cy - sign * half
        wing = size * 0.46
        self.line((cx, tail, cx, tip), fill, width)
        self.line((cx - wing, tip - sign * wing, cx, tip, cx + wing, tip - sign * wing), fill, width)
        for px, py in ((cx, tail), (cx - wing, tip - sign * wing), (cx + wing, tip - sign * wing)):
            r = width / 2
            self.ellipse((px - r, py - r, px + r, py + r), fill=fill, width=0)

    def trend_icon(self, x, y, w, h, fill, width=5):
        """The little zigzag with dots that sits next to the ELO number."""
        pts = [(x, y + h * 0.78), (x + w * 0.30, y + h * 0.30), (x + w * 0.62, y + h * 0.74), (x + w, y + h * 0.22)]
        self.line([v for p in pts for v in p], fill, width)
        for px, py in pts:
            r = width * 1.15
            self.ellipse((px - r, py - r, px + r, py + r), fill=fill, width=0)

    def fit_size(self, text, size, max_w, bold=True, floor=9):
        """Biggest font size, not above `size`, where the text still fits in max_w."""
        while size > floor and self.width(text, size, bold) > max_w:
            size -= 1
        return size

    def png(self):
        out = self.img.resize((self.w, self.h), Image.LANCZOS)
        buf = io.BytesIO()
        out.save(buf, "PNG")
        return buf.getvalue()


def stats_card(*, name, username, scope, avatar, elo, st, form, standing, accent=ACCENT):
    """Banner in the look of a FACEIT widget: big ELO, a pill with the leaderboard place and an arrow, the
    level badge and its bar. The right side is the player: icon, name and the stat tiles. `accent` is the
    server color from /color. The level badge and its bar have their own colors and never change with it.
    `standing` comes from DB.standing: the place, and move +1 (climbed) / -1 (dropped) / 0."""
    W, H = 960, 400
    c = Canvas(W, H, bg=None, scale=3)
    lv = level_of(elo)
    rc = level_color(lv.number)
    bar0, bar1 = level_bar(lv.number)
    c.rrect((0, 0, W, H), 46, fill=CARD)
    c.rrect((1, 1, W - 2, H - 2), 45, outline=mix(accent, CARD, 0.5), width=2)

    # left: the widget
    lx, lw = 50, 372
    c.text((lx, 38), config.BOT_NAME.upper(), 24, accent)
    txt = f"{elo:,}"
    size = c.fit_size(txt, 100, lw - 54 - 20)
    c.text((lx, 122), txt, size, TEXT, "lm")
    c.trend_icon(lx + c.width(txt, size) + 22, 106, 48, 40, (235, 235, 235))

    # pill: place in the leaderboard, the arrow says if the player climbed or dropped
    place, move = standing["place"], standing["move"]
    if place is None:
        pill, col, num = (50, 50, 53), (150, 150, 156), "Unranked"
    else:
        pill, col, num = {1: ((24, 64, 40), (62, 224, 114), f"{place:,}"),
                          -1: ((68, 26, 34), (255, 62, 84), f"{place:,}"),
                          0: ((50, 50, 53), (150, 150, 156), f"{place:,}")}[move]
    nsize = c.fit_size(num, 32, 150)
    icon = place is not None
    pw = 28 + (26 + 12 if icon else 0) + c.width(num, nsize) + 28
    c.rrect((lx, 172, lx + pw, 226), 27, fill=pill)
    tx = lx + 28
    if icon:
        if move:
            c.arrow(lx + 28 + 13, 199, 24, move > 0, col)
        else:
            c.line((lx + 28, 199, lx + 54, 199), col, 5)
        tx = lx + 28 + 26 + 12
    c.text((tx, 199), num, nsize, col, "lm")
    if place is not None:
        c.text((lx + pw + 18, 199), "SERVER PLACE" if scope == "This server" else "GLOBAL PLACE", 14, MUTED2, "lm")

    # level badge on the left end of the bar, the bar runs from behind it
    br = 40
    bx, by = lx + br, 296
    bar_vis0, bar_x1 = bx + br, lx + lw
    c.rrect((bx, by - 12, bar_x1, by + 12), 12, fill=(52, 52, 55))
    fill_end = bar_vis0 + (bar_x1 - bar_vis0) * lv.progress
    c.gradient_bar((bx, by - 12, max(fill_end, bar_vis0 + 24), by + 12), bar0, bar1, 12,
                   t_end=max(lv.progress, 0.12))
    c.level_badge(bx, by, br, lv.number, rc)
    label = lv.name if lv.maxed else f"{lv.name}   |   {lv.need:,} ELO to Level {lv.number + 1}"
    c.text(((bar_vis0 + bar_x1) / 2, by + 50), label, c.fit_size(label, 19, bar_x1 - bar_vis0 + 20, False),
           MUTED2, "mm", bold=False)

    # right: the player
    x0, x1 = 474, 916
    c.text((x1, 30), scope.upper(), 13, mix(accent, MUTED2, 0.35), "ra")
    c.avatar_round(avatar, x0 + 36, 78, 64, accent, bg=CARD)
    nx = x0 + 36 + 32 + 6 + 16
    shown = fit(name, 20)
    c.text((nx, 50), shown, c.fit_size(shown, 31, x1 - nx), TEXT)
    sub = f"@{fit(username, 22)}"
    c.text((nx, 92), sub, 17, MUTED2, bold=False)
    c.text((nx + c.width(sub, 17, False) + 14, 92), lv.name, 17, rc)
    c.line((x0, 130, x1, 130), mix(accent, CARD, 0.62), 2)

    rows = [
        [("Matches", st["matches"], TEXT), ("Wins", st["wins"], GREEN2),
         ("Draws", st["draws"], TEXT), ("Losses", st["losses"], RED2)],
        [("Goals", st["goals"], TEXT), ("Assists", st["assists"], TEXT),
         ("Clean Sheets", st["clean_sheets"], TEXT), ("Win Rate", f"{st['winrate']}%", TEXT)],
    ]
    tw, gap = 105, 7
    for ri, row in enumerate(rows):
        y = 144 + ri * 88
        for ci, (label, value, vcol) in enumerate(row):
            x = x0 + ci * (tw + gap)
            c.rrect((x, y, x + tw, y + 78), 16, fill=TILE)
            c.text((x + tw / 2, y + 31), value, c.fit_size(str(value), 32, tw - 16), vcol, "mm")
            c.text((x + tw / 2, y + 59), label, c.fit_size(label, 14, tw - 12, False), MUTED2, "mm", bold=False)

    c.text((x0, 328), "RECENT FORM", 13, mix(accent, MUTED2, 0.35))
    if not form:
        c.text((x0, 362), "No results yet", 16, MUTED2, "lm", bold=False)
    for i, res in enumerate(form):
        x = x0 + i * 36
        fcol = {"win": GREEN2, "loss": RED2}.get(res, MUTED2)
        c.rrect((x, 348, x + 28, 376), 8, fill=fcol)
        c.text((x + 14, 362), {"win": "W", "loss": "L"}.get(res, "D"), 15, CARD, "mm")
    return c.png()


PODIUM = [(255, 200, 40), (200, 205, 215), (205, 127, 50)]


def leaderboard_card(*, title, subtitle, rows, images, show_rank, accent=ACCENT):  # show_rank: draw level badges
    n = max(len(rows), 1)
    c = Canvas(760, 112 + n * 66 + 16)
    c.rect((0, 0, 760, 10), fill=accent)
    c.text((28, 30), title, 30, TEXT)
    c.text((28, 72), subtitle.upper(), 14, MUTED)
    if not rows:
        c.text((380, 150), "NO STATS YET", 18, MUTED, "mm")
    for i, r in enumerate(rows):
        y = 106 + i * 66
        c.rect((24, y, 736, y + 58), fill=PANEL, outline=EDGE)
        top = PODIUM[i] if i < 3 else None
        c.rect((24, y, 72, y + 58), fill=top or PANEL2, outline=EDGE)
        c.text((48, y + 29), i + 1, 24, DARK if top else MUTED, "mm")
        c.avatar(images.get(r["discord_id"]), 84, y + 7, 44, edge=top or EDGE)
        c.text((142, y + 8), fit(r["display_name"], 22), 20, TEXT)
        c.text((142, y + 35), fit(f"@{r['roblox_name']}  |  {r['matches']} matches", 40), 14, MUTED, bold=False)
        if show_rank:
            lv = level_of(r["elo"])
            c.level_badge(533, y + 29, 22, lv.number, level_color(lv.number))
        c.text((716, y + 29), f"{r['value']:,}", 28, TEXT, "rm")
    return c.png()


def pitch_card(*, tactic, fmt, status, slots, placed, images, accent=ACCENT):
    W, H = 760, 1000
    c = Canvas(W, H)
    c.rect((0, 0, W, 10), fill=accent)
    c.text((28, 26), "LINEUP", 36, TEXT)
    c.text((28, 76), f"{tactic}   |   {fmt.upper()}", 16, MUTED)
    c.text((732, 30), "LIVE" if status == "open" else "ENDED", 24, accent if status == "open" else MUTED, "ra")
    c.text((732, 70), f"{len(placed)} / {len(slots)} PLAYERS", 14, MUTED, "ra")

    x0, y0, x1, y1 = 24, 116, 736, 976
    c.rect((x0, y0, x1, y1), fill=(14, 38, 26))
    band = (y1 - y0) / 10
    for i in range(0, 10, 2):
        c.rect((x0, y0 + i * band, x1, y0 + (i + 1) * band), fill=(17, 44, 30))
    chalk = (178, 196, 184)
    ix0, iy0, ix1, iy1 = x0 + 14, y0 + 14, x1 - 14, y1 - 14
    cx, cy = (ix0 + ix1) / 2, (iy0 + iy1) / 2
    c.rect((ix0, iy0, ix1, iy1), outline=chalk)
    c.line((ix0, cy, ix1, cy), chalk)
    c.ellipse((cx - 70, cy - 70, cx + 70, cy + 70), outline=chalk)
    for ey, sign in ((iy0, 1), (iy1, -1)):
        c.rect((cx - 150, ey, cx + 150, ey + sign * 130), outline=chalk)
        c.rect((cx - 66, ey, cx + 66, ey + sign * 46), outline=chalk)
    c.rect((x0, y0, x1, y1), outline=EDGE, width=3)

    span_x, top, span_y = ix1 - ix0, iy0 + 56, (iy1 - iy0) - 150
    size = 60
    for pos, px, py in slots:
        x = ix0 + px * span_x
        y = top + (py - 0.1) / 0.84 * span_y
        p = placed.get(pos)
        if p:
            c.avatar_round(images.get(p["discord_id"]), x, y, size, accent, gap=2, ring_w=3)
            c.text((x, y + size / 2 + 22), fit(p["name"], 13), 14, TEXT, "mm", stroke=2)
            bits = []
            if p["goals"]:
                bits.append(f"{p['goals']}G")
            if p["assists"]:
                bits.append(f"{p['assists']}A")
            if p["clean_sheet"]:
                bits.append("CS")
            if bits:
                c.text((x, y + size / 2 + 40), " ".join(bits), 13, accent, "mm", stroke=2)
            w = c.width(pos, 12) + 14
            c.rrect((x - w / 2, y - size / 2 - 25, x + w / 2, y - size / 2 - 9), 6, fill=DARK)
            c.text((x, y - size / 2 - 17), pos, 12, TEXT, "mm")
        else:
            c.ellipse((x - size / 2, y - size / 2, x + size / 2, y + size / 2), fill=(10, 28, 19), outline=chalk)
            c.text((x, y), pos, 15, chalk, "mm")
    return c.png()
