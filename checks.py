import discord
from discord import app_commands

from util import slots


async def is_admin(interaction):
    m = interaction.user
    if not isinstance(m, discord.Member):
        return False
    p = m.guild_permissions
    if p.administrator or p.manage_guild:
        return True
    row = await interaction.client.db.settings(interaction.guild_id)
    role_id = row["admin_role_id"] if row else None
    return bool(role_id) and any(r.id == role_id for r in m.roles)


admin_only = app_commands.check(is_admin)


async def position_ac(interaction, current):
    db = interaction.client.db
    cur = await db.latest_open(interaction.guild_id)
    tactic = cur["tactic"] if cur else await db.default_tactic(interaction.guild_id)
    return [app_commands.Choice(name=p, value=p) for p, _, _ in slots(tactic)
            if current.upper() in p][:25]
