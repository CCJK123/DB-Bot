import os

from aiohttp import web

from utils import dbbot, discordutils


class Webserver(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.bot = bot

        app = web.Application()
        routes = web.RouteTableDef()

        @routes.get('/')
        async def welcome(_):
            return web.Response(text=os.environ['MYSQLCONNSTR_ONLINE_MSG'])

        app.add_routes(routes)

        self.runner = web.AppRunner(app)

    async def on_ready(self):
        await self.runner.setup()
        site = web.TCPSite(self.runner, '0.0.0.0', int(os.environ['PORT']))
        print('starting site')
        await site.start()

    async def on_cleanup(self):
        await self.runner.cleanup()


def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(Webserver(bot))
