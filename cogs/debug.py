from discord.ext import commands

import dbbot
from utils import discordutils


class DebugCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

    @discordutils.gov_check
    @commands.command()
    async def get_keys(self, ctx: commands.Context):
        await ctx.send(await self.bot.database.keys())

    @discordutils.gov_check
    @commands.command()
    async def get_key(self, ctx: commands.Context, key: str):
        print(a := await self.bot.database.get(key))
        await ctx.send(a)

    @discordutils.gov_check
    @commands.command()
    async def del_key(self, ctx: commands.Context, key: str):
        await self.bot.database.delete(key)
        await ctx.send('done')

    @discordutils.gov_check
    @commands.command()
    async def set_key(self, ctx, key, val):
        await self.bot.database.set(key, eval(val))
        await ctx.send(f'{key} set to {eval(val)}')


def setup(bot: dbbot.DBBot):
    bot.add_cog(DebugCog(bot))
