from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import config
from checks import admin_only
from panel import current, refresh_panel, sync_panel
from util import UserError, level_of

P = config.POINTS

# what the bot calls each thing in its replies
TITLES = {"goal": "Goal", "assist": "Assist", "clean_sheet": "Clean sheet",
          "win": "Win", "draw": "Draw", "loss": "Loss"}


def _bits(kind, amount):
    return f"{TITLES[kind]} x{amount}" if amount > 1 else TITLES[kind]


class PointsCog(commands.Cog):
    """Points are given by hand, one command per thing. The player has to be in the current lineup."""

    def __init__(self, bot):
        self.bot = bot

    async def _give(self, interaction, kind, targets, amount=1):
        """targets is a list of members, or None for everyone in the lineup (cleansheet: the GK).
        Checks and the database come first, the slow part (the picture) after the defer, so a mistake
        is answered privately and only a real award is posted to the channel."""
        db = self.bot.db
        m = await current(self.bot, interaction.guild_id)
        rows = {r["discord_id"]: r for r in await db.lineup(m["id"])}
        if targets is None:
            if kind == "clean_sheet":
                ids = [d for d, r in rows.items() if r["position"] in config.CLEAN_SHEET_POSITIONS]
                if not ids:
                    raise UserError("There is no goalkeeper in the lineup.")
            else:
                ids = list(rows)
                if not ids:
                    raise UserError("The lineup is empty.")
        else:
            ids = [t.id for t in targets]
            missing = [t.display_name for t in targets if t.id not in rows]
            if missing:
                raise UserError(f"{', '.join(missing)} is not in the lineup. Put them in with /lineup set.")
            if kind == "clean_sheet":
                wrong = [t.display_name for t in targets
                         if rows[t.id]["position"] not in config.CLEAN_SHEET_POSITIONS]
                if wrong:
                    raise UserError(f"{', '.join(wrong)} is not a goalkeeper. Only "
                                    f"{'/'.join(sorted(config.CLEAN_SHEET_POSITIONS))} can get a clean sheet.")

        given, skipped = await db.give(m["id"], interaction.guild_id, ids, kind, amount, interaction.user.id)
        if not given:
            raise UserError(f"Nobody got it: {self._why(skipped, rows, kind)}. /undo takes the old one back.")

        await interaction.response.defer()
        lines = []
        for did in given:
            r = rows[did]
            elo = (await db.stats(did, interaction.guild_id))["elo"]
            lines.append(f"`{r['position']:<4}` **{r['roblox_name'] or 'Unknown'}** | "
                         f"**{P[kind] * amount:+d}** | {elo:,} ELO (Level {level_of(elo).number})")
        text = "\n".join(lines)
        if skipped:
            text += f"\n\nSkipped: {self._why(skipped, rows, kind)}."
        await sync_panel(self.bot, interaction, m["id"])
        await interaction.followup.send(embed=discord.Embed(
            title=_bits(kind, amount), color=await db.accent(interaction.guild_id), description=text))

    @staticmethod
    def _why(skipped, rows, kind):
        again = "already has a clean sheet" if kind == "clean_sheet" else "already has a result"
        return ", ".join(f"{rows[d]['roblox_name'] or 'Unknown'} {again if why == 'again' else 'is not in the lineup'}"
                         for d, why in skipped)

    @app_commands.command(name="goal", description=f"Admin: give a goal ({P['goal']:+d} ELO)")
    @app_commands.describe(player="Player from the lineup", amount="How many goals, 1 by default")
    @app_commands.guild_only()
    @admin_only
    async def goal(self, interaction: discord.Interaction, player: discord.Member,
                   amount: app_commands.Range[int, 1, 20] = 1):
        await self._give(interaction, "goal", [player], amount)

    @app_commands.command(name="assist", description=f"Admin: give an assist ({P['assist']:+d} ELO)")
    @app_commands.describe(player="Player from the lineup", amount="How many assists, 1 by default")
    @app_commands.guild_only()
    @admin_only
    async def assist(self, interaction: discord.Interaction, player: discord.Member,
                     amount: app_commands.Range[int, 1, 20] = 1):
        await self._give(interaction, "assist", [player], amount)

    @app_commands.command(name="cleansheet", description=f"Admin: give a clean sheet to the GK ({P['clean_sheet']:+d} ELO)")
    @app_commands.describe(player="The goalkeeper. Empty = whoever is on GK")
    @app_commands.guild_only()
    @admin_only
    async def cleansheet(self, interaction: discord.Interaction, player: Optional[discord.Member] = None):
        await self._give(interaction, "clean_sheet", [player] if player else None)

    @app_commands.command(name="win", description=f"Admin: give a win ({P['win']:+d} ELO)")
    @app_commands.describe(player="Player from the lineup. Empty = everyone in the lineup")
    @app_commands.guild_only()
    @admin_only
    async def win(self, interaction: discord.Interaction, player: Optional[discord.Member] = None):
        await self._give(interaction, "win", [player] if player else None)

    @app_commands.command(name="draw", description=f"Admin: give a draw ({P['draw']:+d} ELO)")
    @app_commands.describe(player="Player from the lineup. Empty = everyone in the lineup")
    @app_commands.guild_only()
    @admin_only
    async def draw(self, interaction: discord.Interaction, player: Optional[discord.Member] = None):
        await self._give(interaction, "draw", [player] if player else None)

    @app_commands.command(name="loss", description=f"Admin: give a loss ({P['loss']:+d} ELO)")
    @app_commands.describe(player="Player from the lineup. Empty = everyone in the lineup")
    @app_commands.guild_only()
    @admin_only
    async def loss(self, interaction: discord.Interaction, player: Optional[discord.Member] = None):
        await self._give(interaction, "loss", [player] if player else None)

    @app_commands.command(name="undo", description="Admin: take back the last points that were given")
    @app_commands.describe(player="Take back the last points of this player. Empty = the whole last command")
    @app_commands.guild_only()
    @admin_only
    async def undo(self, interaction: discord.Interaction, player: Optional[discord.Member] = None):
        db = self.bot.db
        removed = await db.undo(interaction.guild_id, player.id if player else None)
        if not removed:
            raise UserError("Nothing to take back." if not player else f"{player.display_name} has no points.")
        await interaction.response.defer()
        lines = []
        for r in removed:
            p = await db.get_player(r["discord_id"])
            elo = (await db.stats(r["discord_id"], interaction.guild_id))["elo"]
            lines.append(f"**{p['roblox_name'] if p else r['discord_id']}** | {_bits(r['kind'], r['amount'])} | "
                         f"**{-r['points']:+d}** | {elo:,} ELO (Level {level_of(elo).number})")
        await interaction.followup.send(embed=discord.Embed(
            title="Taken back", color=await db.accent(interaction.guild_id), description="\n".join(lines)))
        # the pitch shows goals and assists, so it has to follow
        for lid in dict.fromkeys(r["lineup_id"] for r in removed):
            await refresh_panel(self.bot, lid)


async def setup(bot):
    await bot.add_cog(PointsCog(bot))
