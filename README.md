# Score It!

Discord bot for Real Futbol League (RFL). One bot for any number of servers. Players get ELO, a level and
stats, and there are leaderboards for each server and for all servers together. There are no teams, no clubs and
no match scores: you build a lineup and give points to players by hand.

## Run

    pip install -r requirements.txt
    cp .env.example .env      # put the token in
    python bot.py

The name shown on the cards and in `/help` is `BOT_NAME` in `config.py`. The name of the bot in Discord itself is
set in the Developer Portal (Applications > your app > Bot > Username).

Invite it with the `bot` and `applications.commands` scopes. It needs Send Messages, Embed Links and
Attach Files. No privileged intents. Manage Roles only if you want the verified role.

## Setup on a server

Members with Manage Server are admins. To give admin to a role: `/config admin_role`.
`/config verified_role` gives a role after `/verify`. The bot's role has to be above it.

`/color` is for the server owner only. Type a color code (`#3B82F6`, or a name: red, orange, yellow,
green, cyan, blue, purple, pink, white) and the stats card, leaderboard, lineup picture and the stripe of
every embed switch to it. Run it empty to go back to the default. The level badge and its bar keep their
own color, that one is set by the level (`LEVEL_COLORS` and `LEVEL_BARS` in `config.py`).
Every server has its own color.

## Playing a game

A game is just a lineup. There is nothing to create and nothing to pick.

1. `/lineup set` for every player and position. The first one starts the lineup and posts the pitch with
   everyone's Roblox icon on their position, after that the same picture updates by itself. The formation
   is 4-3-3 until you change it with `/lineup tactic`, the server keeps its formation.
2. Give points with the commands below while the lineup is open.
3. `/lineup end` closes the lineup. The picture stays in the chat. The next `/lineup set` starts a new one.

`/lineup reopen` opens the lineup you just closed again. `/lineup clear` throws away an open lineup that has
no points in it, it does not count as a match. `/lineup show` posts the current lineup again.

## Giving points

The player has to be in the open lineup. Everything is public so the channel sees who got what.

| Command | ELO | Notes |
|---|---|---|
| `/goal @player [amount]` | +5 each | |
| `/assist @player [amount]` | +2 each | |
| `/cleansheet [@player]` | +10 | goalkeeper only, empty = whoever is on GK, once per lineup |
| `/win [@player]` | +20 | empty = everyone in the lineup |
| `/draw [@player]` | +5 | empty = everyone in the lineup |
| `/loss [@player]` | -15 | empty = everyone in the lineup |

A player gets one result (win, draw or loss) and one clean sheet per lineup, a second one is refused.
`/undo` takes back everything the last command gave out, `/undo @player` takes back that player's last points.
Points are in `config.py`.

## ELO and levels

Everyone starts at 1000 ELO. ELO has no limit up or down. Levels work like on FACEIT: Level 1 is 1000-1499
(and anyone under 1000), then a new level every 500 ELO: Level 2 from 1500, Level 3 from 2000 ... Level 10
from 5500, which is the top. The step, the top level and the colors are in `config.py`
(`LEVEL_STEP`, `MAX_LEVEL`, `LEVEL_COLORS`, `LEVEL_BARS`). `MIN_ELO` (a floor, off by default) is there too.

## Stats card

`/stats` posts a banner in the look of a FACEIT widget. On the left: the ELO, a pill with the player's place
in the leaderboard and an arrow (green up = climbed, red down = dropped, grey dash = same place), and the
level badge with a progress bar to the next level. The ring of the badge fills up with the level, a full
ring is Level 10. On the right: the player's icon, name and tiles: Matches (lineups the player was in),
Wins, Draws, Losses, Goals, Assists, Clean Sheets, Win Rate (wins out of games with a result) and the
recent form.

The place is the player's place in `/leaderboard` (ELO), on this server or on all servers, the same as the
scope of the card. The arrow compares it with the leaderboard as it was before the last lineup that gave
points, so a player who got passed by someone else's points drops too. A player with no points yet shows
"Unranked".

## Commands

- `/verify` `/info` `/stats` `/leaderboard` `/levels` `/help`
- `/lineup set|remove|tactic|show|end|reopen|clear`
- `/goal` `/assist` `/cleansheet` `/win` `/draw` `/loss` `/undo`
- `/link` `/unlink`
- `/config admin_role|verified_role|show`
- `/color` (server owner)

Avatars come from Roblox, or from Discord when Roblox has none. Stats are summed from the points that were
given, nothing is stored twice. Everything is in one sqlite file, copy it to back up.

An `rfl.db` from the version with finished games and scores is converted when the bot starts: every
finished game becomes a lineup with its points, so nobody loses ELO. The old tables stay in the file as
`legacy_matches` and `legacy_match_players`.

## Old commands in the slash menu

If you still see commands like `match`, `home` or `away`, they are left over from an older version of the bot.
On every start the bot removes the old per-server commands from all the servers it is in (it can take a minute
on a big bot), and the global ones are replaced by the sync. Three things can keep them alive: an old copy
of the bot still running with the same token (stop it), `DEV_GUILD_ID` filled in on the real bot (leave it
empty), and the Discord app showing a cached list (press Ctrl+R, or restart the app).

## Bot DMs

`/stats`, `/info`, `/levels` and `/help` also work in a private chat with the bot. There is no server in a DM,
so `/stats` and `/info` show the numbers from all servers added up (the place on the card is the global one).
`/verify`, `/leaderboard` and everything for admins still need a server.
