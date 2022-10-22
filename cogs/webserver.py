import os

from aiohttp import web

from utils import dbbot, discordutils


class Webserver(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.bot = bot
        self.start = True

        app = web.Application()
        routes = web.RouteTableDef()

        @routes.get('/')
        async def welcome(_):
            return web.Response(text=os.environ['MYSQLCONNSTR_ONLINE_MSG'])

        app.add_routes(routes)

        self.runner = web.AppRunner(app)

    async def cog_load(self) -> None:
        if self.start:
            self.start = False
            await self.runner.setup()
            site = web.TCPSite(self.runner, '0.0.0.0', 8000)
            print('Starting Site')
            await site.start()

    async def on_cleanup(self):
        await self.runner.cleanup()


async def setup(bot: dbbot.DBBot) -> None:
    await bot.add_cog(Webserver(bot))
