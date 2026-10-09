import asyncio
import io
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

import avatars
import cards
import config
from util import UserError, level_of, parse_iso, rgb

BOARDS = {
    "elo": "ELO",
    "goals": "Goals",
    "assists": "Assists",
    "clean_sheets": "Clean Sheets",
    "wins": "Wins",
}
SCOPES = [app_commands.Choice(name="This server", value="server"),
          app_commands.Choice(name="All servers", value="global")]


def block(s):
    return (f"**Level:** {level_of(s['elo']).number} ({s['elo']:,} ELO)\n"
            f"**Matches:** {s['matches']}\n"
            f"**W / D / L:** {s['wins']} / {s['draws']} / {s['losses']}\n"
            f"**Goals:** {s['goals']}\n"
            f"**Assists:** {s['assists']}\n"
            f"**Clean Sheets:** {s['clean_sheets']}")


class StatsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_member(self, guild, user_id):
        """The member in this server, or None. In the bot's DMs there is no server, so the user itself."""
        if guild is None:
            return self.bot.get_user(user_id)
        member = guild.get_member(user_id)
        if member:
            return member
        try:
            return await guild.fetch_member(user_id)
        except discord.HTTPException:
            return None

    @app_commands.command(name="info", description="Player profile and stats")
    @app_commands.describe(member="Discord member, you by default", roblox="Or a Roblox username")
    async def info(self, interaction: discord.Interaction, member: Optional[discord.User] = None,
                   roblox: Optional[str] = None):
        await interaction.response.defer()
        db, rbx, guild = self.bot.db, self.bot.rbx, interaction.guild
        if roblox:
            rb = await rbx.lookup_username(roblox.strip())
            if not rb:
                raise UserError("No Roblox user with that name.")
            player = await db.player_by_roblox(rb["id"])
            if not player:
                raise UserError(f"{rb['name']} is not linked to a Discord account.")
            member = await self.get_member(guild, player["discord_id"])
        else:
            member = member or interaction.user
            player = await db.get_player(member.id)
            if not player:
                raise UserError(f"{member.display_name} has not linked Roblox. Use /verify.")
        did, rid = player["discord_id"], player["roblox_id"]

        name, display, created = player["roblox_name"], player["display_name"], None
        live = await rbx.get_user(rid)
        if live:
            name, display = live["name"], live.get("displayName") or live["name"]
            if live.get("created"):
                created = parse_iso(live["created"])
            if (name, display) != (player["roblox_name"], player["display_name"]):
                await db.update_names(did, name, display)
        thumb = await rbx.avatar_url(rid)
        if not thumb and member:
            thumb = member.display_avatar.url

        # in the bot's DMs there is no server: everything is the total over all servers
        total = await db.stats(did)
        here = await db.stats(did, interaction.guild_id) if guild else total
        lv = level_of(here["elo"])

        roles = ([r.mention for r in reversed(member.roles) if not r.is_default()]
                 if isinstance(member, discord.Member) else [])
        roles_text = " ".join(roles) or "None"
        if len(roles_text) > 1000:
            roles_text = roles_text[:1000].rsplit(" ", 1)[0] + " ..."

        e = discord.Embed(title=f"Info: {name}", color=await db.accent(interaction.guild_id),
                          timestamp=discord.utils.utcnow())
        e.add_field(name="Player", value=f"[{name}](https://www.roblox.com/users/{rid}/profile)\n`{rid}`")
        e.add_field(name="Display Name", value=display)
        if created:
            stamp = int(created.timestamp())
            e.add_field(name="Account Created", value=f"<t:{stamp}:D> | <t:{stamp}:R>", inline=False)
        e.add_field(name="Discord", value=f"<@{did}>\n`{did}`")
        e.add_field(name="Level", value=f"{lv.number} ({here['elo']:,} ELO)")
        if guild:
            e.add_field(name="Server Roles", value=roles_text, inline=False)
            e.add_field(name="This Server", value=block(here))
        e.add_field(name="All Servers", value=block(total))
        if thumb:
            e.set_thumbnail(url=thumb)
        await interaction.followup.send(embed=e)

    @app_commands.command(name="stats", description="Stats card")
    @app_commands.describe(member="Discord member, you by default",
                           scope="This server or all servers (in DMs it is always all servers)")
    @app_commands.choices(scope=SCOPES)
    async def stats(self, interaction: discord.Interaction, member: Optional[discord.User] = None,
                    scope: str = "server"):
        await interaction.response.defer()
        db = self.bot.db
        member = member or interaction.user
        player = await db.get_player(member.id)
        if not player:
            raise UserError(f"{member.display_name} has not linked Roblox. Use /verify.")
        # in the bot's DMs there is no server, so it is always the card over all servers
        gid = interaction.guild_id if scope == "server" and interaction.guild_id else None
        st = await db.stats(member.id, gid)
        form = await db.recent_form(member.id, gid)
        standing = await db.standing(member.id, gid)
        imgs = await avatars.load(self.bot, [(member.id, player["roblox_id"])])
        color = await db.accent(interaction.guild_id)
        png = await asyncio.to_thread(
            cards.stats_card, name=player["display_name"], username=player["roblox_name"],
            scope="This server" if gid else "All servers",
            avatar=imgs.get(member.id), elo=st["elo"], st=st, form=form, standing=standing,
            accent=rgb(color))
        # the card sits in an embed so the stripe on the left has the server color too
        e = discord.Embed(color=color)
        e.set_image(url="attachment://stats.png")
        await interaction.followup.send(embed=e, file=discord.File(io.BytesIO(png), filename="stats.png"))

    @app_commands.command(name="leaderboard", description="Top players")
    @app_commands.describe(category="What to rank by", scope="This server or all servers")
    @app_commands.choices(category=[app_commands.Choice(name=v, value=k) for k, v in BOARDS.items()],
                          scope=SCOPES)
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction, category: str = "elo", scope: str = "server"):
        await interaction.response.defer()
        gid = interaction.guild_id if scope == "server" else None
        rows = await self.bot.db.leaderboard(category, gid, 10)
        imgs = await avatars.load(self.bot, [(r["discord_id"], r["roblox_id"]) for r in rows])
        color = await self.bot.db.accent(interaction.guild_id)
        png = await asyncio.to_thread(
            cards.leaderboard_card, title=f"LEADERBOARD - {BOARDS[category].upper()}",
            subtitle="This server" if gid else "All servers",
            rows=rows, images=imgs, show_rank=category == "elo", accent=rgb(color))
        e = discord.Embed(color=color)
        e.set_image(url="attachment://leaderboard.png")
        await interaction.followup.send(embed=e, file=discord.File(io.BytesIO(png), filename="leaderboard.png"))

    @app_commands.command(name="levels", description="Level ladder and ELO points")
    async def levels(self, interaction: discord.Interaction):
        base, step, top = config.START_ELO, config.LEVEL_STEP, config.MAX_LEVEL
        shown = top or 10
        lines = []
        for i in range(shown):
            low = base + i * step
            end = f"{low}+" if top and i + 1 == top else f"{low} - {low + step - 1}"
            lines.append(f"Level {i + 1:<2} {end}")
        if not top:
            lines.append(f"Level {shown + 1:<2} {base + shown * step}+ and so on")
        p = config.POINTS
        pts = (f"Goal {p['goal']:+d}\nAssist {p['assist']:+d}\nClean sheet (GK) {p['clean_sheet']:+d}\n"
               f"Win {p['win']:+d}\nDraw {p['draw']:+d}\nLoss {p['loss']:+d}")
        e = discord.Embed(title="Levels", color=await self.bot.db.accent(interaction.guild_id))
        e.add_field(name="Ladder", value="```\n" + "\n".join(lines) + "\n```")
        e.add_field(name="ELO points", value="```\n" + pts + "\n```")
        e.set_footer(text=f"Everyone starts at {base}. A new level every {step} ELO"
                          + (f", up to Level {top}." if top else "."))
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="help", description="Command list")
    async def help(self, interaction: discord.Interaction):
        e = discord.Embed(title=config.BOT_NAME, color=await self.bot.db.accent(interaction.guild_id),
                          description=f"Stats bot for {config.LEAGUE_NAME}\n"
                                      "`/stats` `/info` `/levels` `/help` also work in my DMs, there they show "
                                      "your numbers from all servers.")
        e.add_field(name="Players", inline=False, value=(
            "`/verify` link Roblox\n`/info` profile\n`/stats` stats card\n"
            "`/leaderboard` top players\n`/levels` level ladder\n`/lineup show` current lineup"))
        e.add_field(name="Admins: lineup", inline=False, value=(
            "`/lineup set` `/lineup remove` build the lineup\n`/lineup tactic` change the formation\n"
            "`/lineup end` close it, `/lineup reopen` open it again, `/lineup clear` throw it away"))
        e.add_field(name="Admins: points", inline=False, value=(
            "`/goal` `/assist` `/cleansheet` `/win` `/draw` `/loss`\n`/undo` take the last points back\n"
            "`/link` `/unlink`\n`/config admin_role` `/config verified_role` `/config show`"))
        e.add_field(name="Server owner", inline=False, value="`/color` color of the cards and embeds")
        await interaction.response.send_message(embed=e)


async def setup(bot):
    await bot.add_cog(StatsCog(bot))
