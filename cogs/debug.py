from __future__ import annotations

from discord.ext import commands

import discordutils



class DebugCog(discordutils.CogBase):
    def __init__(self, bot: discordutils.DBBot):
        super().__init__(bot, __name__)
    

    @commands.command()
    async def get_keys(self, ctx: commands.Context):
        await ctx.send(await self.bot.db.items())


    @commands.command()
    async def del_key(self, ctx: commands.Context, key: str):
        await self.bot.db.delete(key)
        await ctx.send('done')


    @commands.command()
    async def set_key(self, ctx, key, val):
        await self.bot.db.set(key, eval(val))
        await ctx.send(f'{key} set to {eval(val)}')
    


def setup(bot: discordutils.DBBot):
    bot.add_cog(DebugCog(bot))