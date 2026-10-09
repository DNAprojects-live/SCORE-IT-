import secrets

import discord
from discord import app_commands
from discord.ext import commands

import config
from checks import admin_only
from util import UserError


async def give_role(bot, member):
    row = await bot.db.settings(member.guild.id)
    if not row or not row["verified_role_id"]:
        return
    role = member.guild.get_role(row["verified_role_id"])
    if role:
        try:
            await member.add_roles(role, reason=f"{config.BOT_NAME} verify")
        except discord.HTTPException:
            pass


class VerifyView(discord.ui.View):
    def __init__(self, bot, user_id, rb, code):
        super().__init__(timeout=900)
        self.bot, self.user_id, self.rb, self.code = bot, user_id, rb, code

    @discord.ui.button(label="Verify", style=discord.ButtonStyle.danger)
    async def verify(self, interaction, button):
        if interaction.user.id != self.user_id:
            return await interaction.response.send_message("Not yours.", ephemeral=True)
        await interaction.response.defer()
        data = await self.bot.rbx.get_user(self.rb["id"])
        if data is None:
            return await interaction.followup.send("Roblox didn't answer. Try again.", ephemeral=True)
        if self.code not in (data.get("description") or ""):
            return await interaction.followup.send(
                f"Code {self.code} is not in the About section of {data['name']}. "
                "Save the profile and press Verify again.", ephemeral=True)
        try:
            await self.bot.db.add_player(self.user_id, data["id"], data["name"],
                                         data.get("displayName") or data["name"])
        except UserError as e:
            return await interaction.followup.send(str(e), ephemeral=True)
        await give_role(self.bot, interaction.user)
        self.stop()
        embed = discord.Embed(title="Verified", color=await self.bot.db.accent(interaction.guild_id),
                              description=f"Linked to **{data['name']}**. You can remove the code from your profile.")
        await interaction.edit_original_response(embed=embed, view=None)


class VerifyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="verify", description="Link your Roblox account")
    @app_commands.describe(username="Your Roblox username")
    @app_commands.guild_only()
    async def verify(self, interaction: discord.Interaction, username: str):
        await interaction.response.defer(ephemeral=True)
        db = self.bot.db
        have = await db.get_player(interaction.user.id)
        if have:
            raise UserError(f"You are already linked to {have['roblox_name']}. An admin can unlink you.")
        rb = await self.bot.rbx.lookup_username(username.strip())
        if not rb:
            raise UserError("No Roblox user with that name.")
        if await db.player_by_roblox(rb["id"]):
            raise UserError("That Roblox account is linked to someone else.")
        code = "RFL-" + secrets.token_hex(3).upper()
        embed = discord.Embed(title="Verify Roblox", color=await db.accent(interaction.guild_id), description=(
            f"1. Open [{rb['name']}](https://www.roblox.com/users/{rb['id']}/profile)\n"
            f"2. Put this in your About section:\n```{code}```\n"
            "3. Save, then press Verify below. The code works for 15 minutes."))
        await interaction.followup.send(embed=embed, view=VerifyView(self.bot, interaction.user.id, rb, code),
                                        ephemeral=True)

    @app_commands.command(name="link", description="Admin: link a member to a Roblox account, no code")
    @app_commands.describe(member="Discord member", username="Roblox username")
    @app_commands.guild_only()
    @admin_only
    async def link(self, interaction: discord.Interaction, member: discord.Member, username: str):
        await interaction.response.defer(ephemeral=True)
        rb = await self.bot.rbx.lookup_username(username.strip())
        if not rb:
            raise UserError("No Roblox user with that name.")
        await self.bot.db.add_player(member.id, rb["id"], rb["name"], rb.get("displayName") or rb["name"])
        await give_role(self.bot, member)
        await interaction.followup.send(f"{member.mention} linked to {rb['name']}.", ephemeral=True)

    @app_commands.command(name="unlink", description="Admin: remove a member's Roblox link")
    @app_commands.describe(member="Discord member")
    @app_commands.guild_only()
    @admin_only
    async def unlink(self, interaction: discord.Interaction, member: discord.Member):
        if not await self.bot.db.remove_player(member.id):
            raise UserError("That member isn't linked.")
        await interaction.response.send_message(
            f"{member.mention} unlinked. Their matches stay and come back if they link again.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(VerifyCog(bot))
