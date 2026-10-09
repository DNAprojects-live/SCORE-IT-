from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import config
from util import UserError, parse_color


@app_commands.guild_only()
@app_commands.default_permissions(manage_guild=True)
class SettingsCog(commands.GroupCog, group_name="config", group_description="Server settings"):
    def __init__(self, bot):
        self.bot = bot
        super().__init__()

    async def _save(self, interaction, key, role, label):
        if key == "verified_role_id" and role and role >= interaction.guild.me.top_role:
            raise UserError("The bot's role has to sit above that role.")
        await self.bot.db.set_setting(interaction.guild_id, key, role.id if role else None)
        await interaction.response.send_message(f"{label}: {role.mention if role else 'none'}", ephemeral=True)

    @app_commands.command(name="admin_role", description="Role allowed to run the admin commands. Empty clears it")
    @app_commands.describe(role="Admin role")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def admin_role(self, interaction: discord.Interaction, role: Optional[discord.Role] = None):
        await self._save(interaction, "admin_role_id", role, "Admin role")

    @app_commands.command(name="verified_role", description="Role given after /verify. Empty clears it")
    @app_commands.describe(role="Verified role")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def verified_role(self, interaction: discord.Interaction, role: Optional[discord.Role] = None):
        await self._save(interaction, "verified_role_id", role, "Verified role")

    @app_commands.command(name="show", description="Current server settings")
    async def show(self, interaction: discord.Interaction):
        db = self.bot.db
        row = await db.settings(interaction.guild_id)
        color = await db.accent(interaction.guild_id)

        def role(key):
            return f"<@&{row[key]}>" if row and row[key] else "none"

        e = discord.Embed(title="Settings", color=color)
        e.add_field(name="Admin role", value=role("admin_role_id"))
        e.add_field(name="Verified role", value=role("verified_role_id"))
        e.add_field(name="Color", value=f"#{color:06X}")
        e.add_field(name="Formation", value=await db.default_tactic(interaction.guild_id))
        await interaction.response.send_message(embed=e, ephemeral=True)


class ColorCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="color", description="Server owner: color of this server's cards and embeds")
    @app_commands.describe(code="Color code like #FFCC00. Leave empty to go back to the default")
    @app_commands.guild_only()
    @app_commands.default_permissions(administrator=True)
    async def color(self, interaction: discord.Interaction, code: Optional[str] = None):
        owner_id = interaction.guild.owner_id if interaction.guild else None
        if interaction.user.id != owner_id:
            raise UserError("Only the server owner can change the color.")
        value = parse_color(code) if code else None
        await self.bot.db.set_setting(interaction.guild_id, "color", value)
        shown = value if value is not None else config.DEFAULT_COLOR
        text = (f"Color is now #{shown:06X}. The stats card, leaderboard, lineup and every embed use it. "
                "The level badge keeps its own color." if value is not None
                else f"Color reset to #{shown:06X}.")
        await interaction.response.send_message(embed=discord.Embed(description=text, color=shown),
                                                ephemeral=True)


async def setup(bot):
    await bot.add_cog(SettingsCog(bot))
    await bot.add_cog(ColorCog(bot))
