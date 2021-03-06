"""Statistics reporting for bot lists.

Carbonitex and bots.discord.pw
"""

import json
import logging

import aiohttp
import discord
from dango import dcog, Cog

log = logging.getLogger(__name__)

OWNER_ID = "86607397321207808"
CARBONITEX_API_BOTDATA = "https://www.carbonitex.net/discord/data/botdata.php"
DISCORD_BOTS_API = "https://bots.discord.pw/api"


@dcog(pass_bot=True)
class Vanity(Cog):
    """Cog for updating carbonitex.net bot information."""

    def __init__(self, bot, config):
        self.bot = bot
        self.oauth_client_id = config.register("oauth_client_id")
        self.carbon_api_key = config.register("carbon_api_key", default="")
        self.discord_bots_api_key = config.register("discord_bots_api_key", default="")

        self._owner = None

    async def find_owner(self):
        if self._owner:
            return self._owner
        me = self.bot.get_user(OWNER_ID)

        if not me:
            me = await self.bot.fetch_user(OWNER_ID)

        self._owner = (me.name, me.id) if me else (None, None)
        return self._owner

    def features(self):
        "<br/>".join([
            "{}: {}".format(command.name, command.short_doc or "")
            for command in set(self.bot.all_commands.values()) if not command.hidden
        ])

    async def _update_carbon(self):
        if not self.carbon_api_key():
            return
        me_name, me_id = await self.find_owner

        server_count = len(self.bot.guilds)

        async with aiohttp.ClientSession() as sess:
            async with sess.post(
                    CARBONITEX_API_BOTDATA,
                    data=dict(
                        key=self.carbon_api_key(),
                        botname=self.bot.user.name,
                        botid=self.bot.user.id,
                        logoid=self.bot.user.avatar,
                        ownername=me_name,
                        ownerid=me_id,
                        oauthurl=discord.utils.oauth_url(
                            self.oauth_client_id(), discord.Permissions.all()),
                        features=self.features(),
                        servercount=server_count)):
                pass

        log.debug("Sent carbonitex update.")

    async def _update_dbots(self):
        if not self.discord_bots_api_key():
            return

        server_count = len(self.bot.guilds)
        async with aiohttp.ClientSession() as sess:
            async with sess.post(
                    '{0}/bots/{1.user.id}/stats'.format(DISCORD_BOTS_API, self.bot),
                    headers={
                        'authorization': self.discord_bots_api_key(),
                        'content-type': 'application/json'
                    },
                    data=json.dumps({
                        'server_count': server_count
                    })):
                pass

        log.debug("Sent discord bots update.")

    async def update(self):
        await self._update_carbon()
        await self._update_dbots()

    @Cog.listener()
    async def on_guild_join(self, server):
        await self.update()

    @Cog.listener()
    async def on_guild_leave(self, server):
        await self.update()

    @Cog.listener()
    async def on_ready(self):
        await self.update()
