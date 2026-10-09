import logging

import discord
from discord import app_commands
from discord.ext import commands

import config
from checks import admin_only, position_ac
from panel import build_panel, current, delete_panel, refresh_panel, sync_panel
from util import UserError, slots, tactic_label

log = logging.getLogger("rfl.lineup")

TACTIC_CHOICES = [app_commands.Choice(name=tactic_label(t), value=t) for t in config.TACTICS]


@app_commands.guild_only()
class LineupCog(commands.GroupCog, group_name="lineup", group_description="Admin: build the lineup"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    @app_commands.command(name="set", description="Put a player on a position. The first one starts the lineup")
    @app_commands.describe(player="Player", position="Position of the formation")
    @app_commands.autocomplete(position=position_ac)
    @admin_only
    async def set_position(self, interaction: discord.Interaction, player: discord.Member, position: str):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db
        m = await db.latest_open(interaction.guild_id)
        tactic = m["tactic"] if m else await db.default_tactic(interaction.guild_id)
        pos = position.strip().upper()
        valid = [p for p, _, _ in slots(tactic)]
        if pos not in valid:
            raise UserError(f"{pos} is not in {tactic}. Positions: {', '.join(valid)}")
        row = await db.get_player(player.id)
        if not row:
            raise UserError(f"{player.display_name} has no Roblox linked.")
        lid = m["id"] if m else await db.create_lineup(interaction.guild_id, tactic, interaction.user.id)
        pushed = await db.place(lid, player.id, pos)
        await sync_panel(self.bot, interaction, lid)
        msg = f"{row['roblox_name']} is on {pos}."
        if pushed:
            msg += f" {pushed['roblox_name']} came off."
        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(name="remove", description="Take a player out of the lineup")
    @app_commands.describe(player="Player")
    @admin_only
    async def remove_player(self, interaction: discord.Interaction, player: discord.Member):
        await interaction.response.defer(ephemeral=True)
        m = await current(self.bot, interaction.guild_id)
        if not any(r["discord_id"] == player.id for r in await self.bot.db.lineup(m["id"])):
            raise UserError(f"{player.display_name} is not in the lineup.")
        if await self.bot.db.has_events(m["id"], player.id):
            raise UserError("That player already has points in this lineup. Take them back with /undo first.")
        await self.bot.db.unplace(m["id"], player.id)
        await sync_panel(self.bot, interaction, m["id"])
        await interaction.followup.send(f"{player.display_name} removed.", ephemeral=True)

    @app_commands.command(name="tactic", description="Change the formation of this server")
    @app_commands.describe(formation="Formation")
    @app_commands.choices(formation=TACTIC_CHOICES)
    @admin_only
    async def set_tactic(self, interaction: discord.Interaction, formation: str):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db
        m = await db.latest_open(interaction.guild_id)
        dropped = []
        if m and m["tactic"] != formation:
            fits = {p for p, _, _ in slots(formation)}
            out = [r for r in await db.lineup(m["id"]) if r["position"] not in fits]
            stuck = [r["roblox_name"] or "Unknown" for r in out if await db.has_events(m["id"], r["discord_id"])]
            if stuck:
                raise UserError(f"{', '.join(stuck)} have points on positions that {formation} "
                                "does not have. Take those back with /undo first.")
            for r in out:
                await db.unplace(m["id"], r["discord_id"])
            dropped = [r["roblox_name"] or "Unknown" for r in out]
            await db.set_tactic(m["id"], formation)
        await db.set_setting(interaction.guild_id, "tactic", formation)
        if m:
            await sync_panel(self.bot, interaction, m["id"])
        msg = f"Formation is {tactic_label(formation)}."
        if dropped:
            msg += f" No position for {', '.join(dropped)}, they came off."
        await interaction.followup.send(msg, ephemeral=True)

    @app_commands.command(name="end", description="Close the lineup. The next /lineup set starts a new one")
    @admin_only
    async def end(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db
        m = await current(self.bot, interaction.guild_id)
        if not await db.lineup(m["id"]):
            await delete_panel(self.bot, m)
            await db.discard_lineup(m["id"])
            return await interaction.followup.send("The lineup was empty, it is gone.", ephemeral=True)
        await db.close_lineup(m["id"])
        await refresh_panel(self.bot, m["id"])
        await interaction.followup.send("Lineup closed. The next /lineup set starts a new one.", ephemeral=True)

    @app_commands.command(name="reopen", description="Open the lineup you just closed again")
    @admin_only
    async def reopen(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db
        if await db.latest_open(interaction.guild_id):
            raise UserError("A lineup is already open.")
        last = await db.last_lineup(interaction.guild_id)
        if not last:
            raise UserError("Nothing to reopen.")
        await db.reopen_lineup(last["id"])
        await sync_panel(self.bot, interaction, last["id"])
        await interaction.followup.send("The lineup is open again.", ephemeral=True)

    @app_commands.command(name="clear", description="Throw the open lineup away. It does not count as a match")
    @admin_only
    async def clear(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db
        m = await current(self.bot, interaction.guild_id)
        if await db.has_events(m["id"]):
            raise UserError("Points were already given in this lineup. Take them back with /undo, "
                            "or close it with /lineup end.")
        await delete_panel(self.bot, m)
        await db.discard_lineup(m["id"])
        await interaction.followup.send("Lineup cleared.", ephemeral=True)

    @app_commands.command(name="show", description="Show the current lineup")
    async def show(self, interaction: discord.Interaction):
        await interaction.response.defer()
        m = await self.bot.db.last_lineup(interaction.guild_id)
        if not m:
            raise UserError("No lineup yet.")
        embed, file = await build_panel(self.bot, m["id"])
        await interaction.followup.send(embed=embed, file=file)


async def setup(bot):
    await bot.add_cog(LineupCog(bot))
