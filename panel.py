"""The lineup picture: one message per lineup that is edited in place as players and points change."""
import asyncio
import io
import logging

import discord

import avatars
import cards
import config
from util import UserError, rgb, slots

log = logging.getLogger("rfl.panel")


async def current(bot, guild_id):
    m = await bot.db.latest_open(guild_id)
    if not m:
        raise UserError("No lineup yet. Start with /lineup set.")
    return m


async def build_panel(bot, lineup_id):
    m = await bot.db.get_lineup(lineup_id)
    rows = await bot.db.lineup(lineup_id)
    color = await bot.db.accent(m["guild_id"])
    imgs = await avatars.load(bot, [(r["discord_id"], r["roblox_id"]) for r in rows])
    placed = {r["position"]: {"discord_id": r["discord_id"], "name": r["roblox_name"] or "Unknown",
                              "goals": r["goals"], "assists": r["assists"], "clean_sheet": r["clean_sheet"]}
              for r in rows}
    sl = slots(m["tactic"])
    png = await asyncio.to_thread(
        cards.pitch_card, tactic=m["tactic"], fmt=config.TACTICS[m["tactic"]][0], status=m["status"],
        slots=sl, placed=placed, images=imgs, accent=rgb(color))
    title = "Lineup" if m["status"] == "open" else "Lineup (ended)"
    e = discord.Embed(title=title, color=color, description=f"{m['tactic']} | {len(rows)}/{len(sl)} placed")
    e.set_image(url="attachment://lineup.png")
    return e, discord.File(io.BytesIO(png), filename="lineup.png")


async def refresh_panel(bot, lineup_id):
    """Edit the panel message in place. False means there is no panel to edit (never posted or deleted)."""
    m = await bot.db.get_lineup(lineup_id)
    if not m or not m["channel_id"] or not m["message_id"]:
        return False
    embed, file = await build_panel(bot, lineup_id)
    try:
        channel = bot.get_channel(m["channel_id"]) or await bot.fetch_channel(m["channel_id"])
        await channel.get_partial_message(m["message_id"]).edit(embed=embed, attachments=[file])
        return True
    except (discord.NotFound, discord.Forbidden):
        return False
    except discord.HTTPException as e:
        log.warning("panel for lineup %s not updated: %s", lineup_id, e)
        return True


async def post_panel(bot, interaction, lineup_id):
    embed, file = await build_panel(bot, lineup_id)
    try:
        msg = await interaction.channel.send(embed=embed, file=file)
    except (discord.HTTPException, AttributeError):
        raise UserError("I can't post in this channel. I need Send Messages, Embed Links and Attach Files.")
    await bot.db.set_panel(lineup_id, interaction.channel_id, msg.id)


async def sync_panel(bot, interaction, lineup_id):
    """Update the lineup picture, or post it in this channel if it was never posted or got deleted."""
    if not await refresh_panel(bot, lineup_id):
        await post_panel(bot, interaction, lineup_id)


async def delete_panel(bot, m):
    if not m["channel_id"] or not m["message_id"]:
        return
    try:
        channel = bot.get_channel(m["channel_id"]) or await bot.fetch_channel(m["channel_id"])
        await channel.get_partial_message(m["message_id"]).delete()
    except discord.HTTPException:
        pass
