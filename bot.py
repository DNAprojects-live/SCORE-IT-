import asyncio
import logging

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands

import config
from db import DB
from roblox import Roblox
from util import UserError

log = logging.getLogger("rfl")

COGS = ["cogs.verify", "cogs.stats", "cogs.lineup", "cogs.points", "cogs.settings"]


class ScoreItBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix=commands.when_mentioned, intents=discord.Intents.default(),
                         help_command=None)
        self.db = DB(config.DB_PATH)
        self.session = None
        self.rbx = None
        self._cleaned = False

    async def setup_hook(self):
        self.session = aiohttp.ClientSession(headers={"User-Agent": "ScoreIt-Bot/2.0"})
        self.rbx = Roblox(self.session)
        self.tree.on_error = self.on_tree_error
        for ext in COGS:
            await self.load_extension(ext)
        if config.DEV_GUILD_ID:
            guild = discord.Object(id=config.DEV_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self):
        log.info("%s is online as %s, in %s servers", config.BOT_NAME, self.user, len(self.guilds))
        if not self._cleaned:
            self._cleaned = True
            self._cleanup = asyncio.create_task(self.clear_old_commands())  # keep a reference so it is not dropped

    async def clear_old_commands(self):
        """Older versions of the bot (the ones with /match and the home / away scores) may have registered
        their commands for single servers. The global sync above never touches those, so they would stay in
        the slash menu for ever, next to the real ones. Wipe them from every server. The dev server is skipped,
        it just got the current commands."""
        for guild in list(self.guilds):
            if guild.id == config.DEV_GUILD_ID:
                continue
            try:
                if await self.tree.fetch_commands(guild=guild):
                    # this bot has no commands of its own for a single server, so syncing sends an empty list
                    await self.tree.sync(guild=guild)
                    log.info("removed old commands from %s", guild.name)
            except discord.HTTPException as e:
                log.warning("could not clean the commands of %s: %s", guild.name, e)
            await asyncio.sleep(1)

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()

    async def on_tree_error(self, interaction, error):
        if isinstance(error, app_commands.CommandInvokeError):
            error = error.original
        if isinstance(error, UserError):
            msg = str(error)
        elif isinstance(error, app_commands.MissingPermissions):
            msg = "You need Manage Server for that."
        elif isinstance(error, app_commands.CheckFailure):
            msg = "Admins only."
        else:
            log.exception("command failed", exc_info=error)
            msg = "Something broke. Try again."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.HTTPException:
            pass


if __name__ == "__main__":
    if not config.TOKEN:
        raise SystemExit("DISCORD_TOKEN is empty, fill in .env")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ScoreItBot().run(config.TOKEN, log_handler=None)
