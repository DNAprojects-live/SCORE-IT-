import asyncio
import sqlite3
import threading

import config
from util import UserError, elo_from_delta, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS players(
  discord_id INTEGER PRIMARY KEY,
  roblox_id INTEGER NOT NULL UNIQUE,
  roblox_name TEXT NOT NULL,
  display_name TEXT NOT NULL,
  linked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS guilds(
  guild_id INTEGER PRIMARY KEY,
  admin_role_id INTEGER,
  verified_role_id INTEGER,
  color INTEGER,
  tactic TEXT
);
CREATE TABLE IF NOT EXISTS lineups(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id INTEGER NOT NULL,
  tactic TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  channel_id INTEGER,
  message_id INTEGER,
  created_by INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  closed_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_lineups_guild ON lineups(guild_id);
CREATE TABLE IF NOT EXISTS lineup_players(
  lineup_id INTEGER NOT NULL,
  discord_id INTEGER NOT NULL,
  position TEXT NOT NULL,
  PRIMARY KEY (lineup_id, discord_id),
  UNIQUE (lineup_id, position)
);
CREATE INDEX IF NOT EXISTS ix_lp_player ON lineup_players(discord_id);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  guild_id INTEGER NOT NULL,
  lineup_id INTEGER NOT NULL,
  discord_id INTEGER NOT NULL,
  kind TEXT NOT NULL,
  amount INTEGER NOT NULL DEFAULT 1,
  points INTEGER NOT NULL,
  batch INTEGER NOT NULL,
  created_by INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_events_player ON events(discord_id, guild_id);
CREATE INDEX IF NOT EXISTS ix_events_lineup ON events(lineup_id);
CREATE INDEX IF NOT EXISTS ix_events_batch ON events(batch);
"""

# Every point ever given is one row in `events`. Stats and ELO are summed from them, nothing is stored twice.
RESULTS = ("win", "draw", "loss")
# a player gets at most one of these per lineup: one result, one clean sheet
ONCE = {"win": RESULTS, "draw": RESULTS, "loss": RESULTS, "clean_sheet": ("clean_sheet",)}

EVENT_COLUMNS = """
  COALESCE(SUM(CASE WHEN kind='goal' THEN amount END), 0) AS goals,
  COALESCE(SUM(CASE WHEN kind='assist' THEN amount END), 0) AS assists,
  COALESCE(SUM(CASE WHEN kind='clean_sheet' THEN amount END), 0) AS clean_sheets,
  COALESCE(SUM(CASE WHEN kind='win' THEN amount END), 0) AS wins,
  COALESCE(SUM(CASE WHEN kind='draw' THEN amount END), 0) AS draws,
  COALESCE(SUM(CASE WHEN kind='loss' THEN amount END), 0) AS losses,
  COALESCE(SUM(points), 0) AS delta
"""

BOARDS = {
    "elo": "delta",
    "goals": "goals",
    "assists": "assists",
    "clean_sheets": "clean_sheets",
    "wins": "wins",
}


def _sum_of(kind):
    return (f"COALESCE((SELECT SUM(e.amount) FROM events e WHERE e.lineup_id=lp.lineup_id "
            f"AND e.discord_id=lp.discord_id AND e.kind='{kind}'), 0)")


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        old = self.conn.execute("SELECT 1 FROM sqlite_master WHERE name='teams'").fetchone()
        if old:
            raise SystemExit(f"{path} is from an old version of the bot. "
                             "Delete it or set DB_PATH to a new file.")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        have = {r["name"] for r in self.conn.execute("PRAGMA table_info(guilds)")}
        for col, kind in (("color", "INTEGER"), ("tactic", "TEXT")):
            if col not in have:
                self.conn.execute(f"ALTER TABLE guilds ADD COLUMN {col} {kind}")
        self._migrate_games()
        self.conn.commit()
        self.lock = threading.Lock()

    def _migrate_games(self):
        """The version with finished games and scores kept them in `matches`. Turn every finished game
        into lineups + events so nobody loses ELO, then rename the old tables so this runs only once."""
        c = self.conn
        if not c.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='matches'").fetchone():
            return
        pts = config.POINTS
        with c:
            newest_open = {}
            for g in c.execute("SELECT id, guild_id FROM matches WHERE status='open' ORDER BY id"):
                newest_open[g["guild_id"]] = g["id"]
            games = c.execute("SELECT * FROM matches WHERE status='finished' OR id IN (%s) "
                              "ORDER BY COALESCE(finished_at, created_at), id"
                              % (",".join(str(i) for i in newest_open.values()) or "0")).fetchall()
            batch = 0
            for g in games:
                is_open = g["status"] == "open"
                c.execute("INSERT INTO lineups(id,guild_id,tactic,status,channel_id,message_id,created_by,"
                          "created_at,closed_at) VALUES(?,?,?,?,?,?,?,?,?)",
                          (g["id"], g["guild_id"], g["tactic"], "open" if is_open else "closed",
                           g["channel_id"], g["message_id"], g["created_by"], g["created_at"],
                           None if is_open else g["finished_at"]))
                when = g["finished_at"] or g["created_at"]
                for r in c.execute("SELECT * FROM match_players WHERE match_id=?", (g["id"],)).fetchall():
                    c.execute("INSERT INTO lineup_players(lineup_id,discord_id,position) VALUES(?,?,?)",
                              (g["id"], r["discord_id"], r["position"]))
                    if is_open:
                        continue
                    rows = []
                    if r["goals"]:
                        rows.append(("goal", r["goals"], r["goals"] * pts["goal"]))
                    if r["assists"]:
                        rows.append(("assist", r["assists"], r["assists"] * pts["assist"]))
                    if r["clean_sheet"]:
                        rows.append(("clean_sheet", 1, pts["clean_sheet"]))
                    if r["result"] in RESULTS:
                        # whatever is left of the stored change, so the old ELO comes out exactly the same
                        rows.append((r["result"], 1, r["elo_change"] - sum(x[2] for x in rows)))
                    for kind, amount, points in rows:
                        batch += 1
                        c.execute("INSERT INTO events(guild_id,lineup_id,discord_id,kind,amount,points,batch,"
                                  "created_by,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                                  (g["guild_id"], g["id"], r["discord_id"], kind, amount, points, batch,
                                   g["created_by"], when))
            c.execute("ALTER TABLE matches RENAME TO legacy_matches")
            c.execute("ALTER TABLE match_players RENAME TO legacy_match_players")

    def _run(self, fn):
        with self.lock:
            try:
                res = fn(self.conn)
                self.conn.commit()
                return res
            except Exception:
                self.conn.rollback()
                raise

    async def run(self, fn):
        return await asyncio.to_thread(self._run, fn)

    async def q(self, sql, args=()):
        return await self.run(lambda c: c.execute(sql, args).fetchall())

    async def q1(self, sql, args=()):
        return await self.run(lambda c: c.execute(sql, args).fetchone())

    async def x(self, sql, args=()):
        return await self.run(lambda c: c.execute(sql, args).lastrowid)

    # players

    async def get_player(self, discord_id):
        return await self.q1("SELECT * FROM players WHERE discord_id=?", (discord_id,))

    async def player_by_roblox(self, roblox_id):
        return await self.q1("SELECT * FROM players WHERE roblox_id=?", (roblox_id,))

    async def add_player(self, discord_id, roblox_id, name, display):
        try:
            await self.x("INSERT INTO players(discord_id,roblox_id,roblox_name,display_name,linked_at) "
                         "VALUES(?,?,?,?,?)", (discord_id, roblox_id, name, display, now_iso()))
        except sqlite3.IntegrityError:
            raise UserError("That Discord or Roblox account is already linked.")

    async def update_names(self, discord_id, name, display):
        await self.x("UPDATE players SET roblox_name=?, display_name=? WHERE discord_id=?",
                     (name, display, discord_id))

    async def remove_player(self, discord_id):
        return await self.run(lambda c: c.execute("DELETE FROM players WHERE discord_id=?",
                                                  (discord_id,)).rowcount > 0)

    # per server settings

    async def settings(self, guild_id):
        return await self.q1("SELECT * FROM guilds WHERE guild_id=?", (guild_id,))

    async def set_setting(self, guild_id, key, value):
        if key not in ("admin_role_id", "verified_role_id", "color", "tactic"):
            raise ValueError(key)

        def fn(c):
            c.execute("INSERT OR IGNORE INTO guilds(guild_id) VALUES(?)", (guild_id,))
            c.execute(f"UPDATE guilds SET {key}=? WHERE guild_id=?", (value, guild_id))
        await self.run(fn)

    async def accent(self, guild_id):
        """The server's color as 0xRRGGBB."""
        row = await self.settings(guild_id) if guild_id else None
        return row["color"] if row and row["color"] is not None else config.DEFAULT_COLOR

    async def default_tactic(self, guild_id):
        row = await self.settings(guild_id) if guild_id else None
        tactic = row["tactic"] if row else None
        return tactic if tactic in config.TACTICS else config.DEFAULT_TACTIC

    # lineups. There is at most one open lineup per server and nobody ever picks one by hand,
    # the open one is always the current lineup. Setting the first player starts it.

    async def create_lineup(self, guild_id, tactic, created_by):
        return await self.x("INSERT INTO lineups(guild_id,tactic,created_by,created_at) VALUES(?,?,?,?)",
                            (guild_id, tactic, created_by, now_iso()))

    async def get_lineup(self, lineup_id):
        return await self.q1("SELECT * FROM lineups WHERE id=?", (lineup_id,))

    async def latest_open(self, guild_id):
        return await self.q1("SELECT * FROM lineups WHERE guild_id=? AND status='open' ORDER BY id DESC LIMIT 1",
                             (guild_id,))

    async def last_lineup(self, guild_id):
        return await self.q1("SELECT * FROM lineups WHERE guild_id=? ORDER BY id DESC LIMIT 1", (guild_id,))

    async def set_tactic(self, lineup_id, tactic):
        await self.x("UPDATE lineups SET tactic=? WHERE id=?", (tactic, lineup_id))

    async def close_lineup(self, lineup_id):
        await self.x("UPDATE lineups SET status='closed', closed_at=? WHERE id=?", (now_iso(), lineup_id))

    async def reopen_lineup(self, lineup_id):
        await self.x("UPDATE lineups SET status='open', closed_at=NULL WHERE id=?", (lineup_id,))

    async def discard_lineup(self, lineup_id):
        def fn(c):
            c.execute("DELETE FROM lineup_players WHERE lineup_id=?", (lineup_id,))
            c.execute("DELETE FROM lineups WHERE id=?", (lineup_id,))
        await self.run(fn)

    async def set_panel(self, lineup_id, channel_id, message_id):
        await self.x("UPDATE lineups SET channel_id=?, message_id=? WHERE id=?",
                     (channel_id, message_id, lineup_id))

    async def lineup(self, lineup_id):
        return await self.q(
            f"SELECT lp.discord_id, lp.position, p.roblox_id, p.roblox_name, p.display_name, "
            f"{_sum_of('goal')} AS goals, {_sum_of('assist')} AS assists, "
            f"{_sum_of('clean_sheet')} AS clean_sheet "
            f"FROM lineup_players lp LEFT JOIN players p ON p.discord_id = lp.discord_id "
            f"WHERE lp.lineup_id=?", (lineup_id,))

    async def has_events(self, lineup_id, discord_id=None):
        if discord_id is None:
            return bool(await self.q1("SELECT 1 FROM events WHERE lineup_id=? LIMIT 1", (lineup_id,)))
        return bool(await self.q1("SELECT 1 FROM events WHERE lineup_id=? AND discord_id=? LIMIT 1",
                                  (lineup_id, discord_id)))

    async def place(self, lineup_id, discord_id, position):
        # returns the player who got pushed off the position, if any
        def fn(c):
            occ = c.execute("SELECT lp.*, p.roblox_name FROM lineup_players lp "
                            "LEFT JOIN players p ON p.discord_id = lp.discord_id "
                            "WHERE lp.lineup_id=? AND lp.position=? AND lp.discord_id!=?",
                            (lineup_id, position, discord_id)).fetchone()
            if occ:
                if c.execute("SELECT 1 FROM events WHERE lineup_id=? AND discord_id=? LIMIT 1",
                             (lineup_id, occ["discord_id"])).fetchone():
                    raise UserError(f"{occ['roblox_name']} is on {position} and already has points in this "
                                    "lineup. Take them back with /undo first.")
                c.execute("DELETE FROM lineup_players WHERE lineup_id=? AND discord_id=?",
                          (lineup_id, occ["discord_id"]))
            cur = c.execute("UPDATE lineup_players SET position=? WHERE lineup_id=? AND discord_id=?",
                            (position, lineup_id, discord_id))
            if cur.rowcount == 0:
                c.execute("INSERT INTO lineup_players(lineup_id,discord_id,position) VALUES(?,?,?)",
                          (lineup_id, discord_id, position))
            return occ
        return await self.run(fn)

    async def unplace(self, lineup_id, discord_id):
        await self.x("DELETE FROM lineup_players WHERE lineup_id=? AND discord_id=?", (lineup_id, discord_id))

    # points

    async def give(self, lineup_id, guild_id, discord_ids, kind, amount, by):
        """Give points to players of a lineup. Returns (given, skipped), skipped is a list of
        (discord_id, why) where why is 'missing' (not in the lineup) or 'again' (already has it)."""
        if kind not in config.POINTS:
            raise ValueError(kind)
        points = config.POINTS[kind] * amount

        def fn(c):
            batch = c.execute("SELECT COALESCE(MAX(batch), 0) + 1 FROM events").fetchone()[0]
            given, skipped = [], []
            for did in dict.fromkeys(discord_ids):
                if not c.execute("SELECT 1 FROM lineup_players WHERE lineup_id=? AND discord_id=?",
                                 (lineup_id, did)).fetchone():
                    skipped.append((did, "missing"))
                    continue
                if kind in ONCE:
                    marks = ",".join("?" * len(ONCE[kind]))
                    if c.execute(f"SELECT 1 FROM events WHERE lineup_id=? AND discord_id=? AND kind IN ({marks})",
                                 (lineup_id, did, *ONCE[kind])).fetchone():
                        skipped.append((did, "again"))
                        continue
                c.execute("INSERT INTO events(guild_id,lineup_id,discord_id,kind,amount,points,batch,created_by,"
                          "created_at) VALUES(?,?,?,?,?,?,?,?,?)",
                          (guild_id, lineup_id, did, kind, amount, points, batch, by, now_iso()))
                given.append(did)
            return given, skipped
        return await self.run(fn)

    async def undo(self, guild_id, discord_id=None):
        """Take points back. With a player: that player's latest event. Without: everything the last
        command gave out (a /win for the whole lineup comes back in one go). Returns the removed rows."""
        def fn(c):
            if discord_id is not None:
                last = c.execute("SELECT * FROM events WHERE guild_id=? AND discord_id=? ORDER BY id DESC LIMIT 1",
                                 (guild_id, discord_id)).fetchone()
                rows = [last] if last else []
            else:
                last = c.execute("SELECT batch FROM events WHERE guild_id=? ORDER BY id DESC LIMIT 1",
                                 (guild_id,)).fetchone()
                rows = c.execute("SELECT * FROM events WHERE guild_id=? AND batch=? ORDER BY id",
                                 (guild_id, last["batch"])).fetchall() if last else []
            for r in rows:
                c.execute("DELETE FROM events WHERE id=?", (r["id"],))
            return rows
        return await self.run(fn)

    # stats

    async def stats(self, discord_id, guild_id=None):
        def fn(c):
            g, ga = (" AND guild_id=?", [guild_id]) if guild_id else ("", [])
            d = dict(c.execute(f"SELECT {EVENT_COLUMNS} FROM events WHERE discord_id=?{g}",
                               [discord_id] + ga).fetchone())
            d["matches"] = c.execute(
                "SELECT COUNT(*) FROM lineup_players lp JOIN lineups l ON l.id=lp.lineup_id "
                "WHERE lp.discord_id=?" + (" AND l.guild_id=?" if guild_id else ""),
                [discord_id] + ga).fetchone()[0]
            # ELO change of the newest lineup this player got points in, it is the arrow on the card
            last = c.execute(f"SELECT lineup_id FROM events WHERE discord_id=?{g} ORDER BY id DESC LIMIT 1",
                             [discord_id] + ga).fetchone()
            d["last_change"] = c.execute("SELECT COALESCE(SUM(points), 0) FROM events "
                                         "WHERE discord_id=? AND lineup_id=?",
                                         (discord_id, last["lineup_id"])).fetchone()[0] if last else 0
            return d
        d = await self.run(fn)
        d["elo"] = elo_from_delta(d["delta"])
        decided = d["wins"] + d["draws"] + d["losses"]
        d["winrate"] = round(100 * d["wins"] / decided) if decided else 0
        return d

    async def standing(self, discord_id, guild_id=None):
        """Place in the ELO leaderboard (same order as /leaderboard) and the place the player had before the
        newest lineup that gave points (on this server, or anywhere for the global board). Returns
        {"place", "before", "move"}. `place` is None while the player has no points yet. `move` is +1
        (climbed), -1 (dropped) or 0 (same place, or nothing to compare with, like a first appearance on the
        board). The 'before' board is the same board with every point of that lineup left out, so a player
        who was overtaken by someone else's points drops too."""
        def board(c, skip=None):
            guild = " AND l.guild_id=?" if guild_id else ""
            skip_m = " AND lp.lineup_id!=?" if skip else ""
            where = ["1=1"]
            args = []
            if guild_id:
                args.append(guild_id)
            if skip:
                args.append(skip)
            if guild_id:
                where.append("e.guild_id=?")
                args.append(guild_id)
            if skip:
                where.append("e.lineup_id!=?")
                args.append(skip)
            rows = c.execute(
                f"SELECT p.discord_id, SUM(e.points) AS delta, p.roblox_name, "
                f"(SELECT COUNT(*) FROM lineup_players lp JOIN lineups l ON l.id=lp.lineup_id "
                f"WHERE lp.discord_id=p.discord_id{guild}{skip_m}) AS matches "
                f"FROM events e JOIN players p ON p.discord_id=e.discord_id "
                f"WHERE {' AND '.join(where)} GROUP BY p.discord_id "
                f"ORDER BY delta DESC, matches DESC, p.roblox_name", args).fetchall()
            for i, r in enumerate(rows):
                if r["discord_id"] == discord_id:
                    return i + 1
            return None

        def fn(c):
            last = c.execute("SELECT lineup_id FROM events" + (" WHERE guild_id=?" if guild_id else "") +
                             " ORDER BY id DESC LIMIT 1", [guild_id] if guild_id else []).fetchone()
            place = board(c)
            before = board(c, last["lineup_id"]) if last and place else None
            return place, before

        place, before = await self.run(fn)
        move = 0
        if place and before:
            move = 1 if place < before else -1 if place > before else 0
        return {"place": place, "before": before, "move": move}

    async def recent_form(self, discord_id, guild_id=None, n=5):
        sql = "SELECT kind FROM events WHERE discord_id=? AND kind IN ('win','draw','loss')"
        args = [discord_id]
        if guild_id:
            sql += " AND guild_id=?"
            args.append(guild_id)
        rows = await self.q(sql + " ORDER BY id DESC LIMIT ?", args + [n])
        return [r["kind"] for r in reversed(rows)]

    async def leaderboard(self, category, guild_id=None, limit=10):
        order = BOARDS[category]
        where, args, sub = ["1=1"], [], ""
        if guild_id:
            where.append("e.guild_id=?")
            args.append(guild_id)
            sub = " AND l.guild_id=?"
        rows = await self.q(
            f"SELECT p.discord_id, p.roblox_id, p.roblox_name, p.display_name, {EVENT_COLUMNS}, "
            f"(SELECT COUNT(*) FROM lineup_players lp JOIN lineups l ON l.id=lp.lineup_id "
            f"WHERE lp.discord_id=p.discord_id{sub}) AS matches "
            f"FROM events e JOIN players p ON p.discord_id=e.discord_id "
            f"WHERE {' AND '.join(where)} GROUP BY p.discord_id "
            f"ORDER BY {order} DESC, matches DESC, p.roblox_name LIMIT ?",
            ([guild_id] if guild_id else []) + args + [limit])
        out = []
        for r in rows:
            d = dict(r)
            d["elo"] = elo_from_delta(d["delta"])
            d["value"] = d["elo"] if category == "elo" else d[order]
            out.append(d)
        return out
