import asyncio

import discord


async def discord_avatar(bot, user_id):
    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        return await user.display_avatar.replace(size=128, format="png").read()
    except (discord.DiscordException, ValueError):
        return None


async def load(bot, people):
    """people is a list of (discord_id, roblox_id). Roblox first, discord avatar if that fails."""
    rb_ids = [rid for _, rid in people if rid]
    rb = await bot.rbx.images(rb_ids) if rb_ids else {}
    out = {did: (rb.get(rid) if rid else None) for did, rid in people}
    missing = [did for did, data in out.items() if data is None]
    if missing:
        fetched = await asyncio.gather(*(discord_avatar(bot, d) for d in missing))
        out.update(zip(missing, fetched))
    return out
