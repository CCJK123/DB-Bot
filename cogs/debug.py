from discord.ext import commands

import discordutils


class DebugCog(discordutils.CogBase):
    def __init__(self, bot: discordutils.DBBot):
        super().__init__(bot, __name__)
    
    @discordutils.gov_check
    @commands.command()
    async def get_keys(self, ctx: commands.Context):
        await ctx.send(await self.bot.db.keys())

    @discordutils.gov_check
    @commands.command()
    async def get_key(self, ctx: commands.Context, key: str):
        await ctx.send(await self.bot.db.get(key))

    @discordutils.gov_check
    @commands.command()
    async def del_key(self, ctx: commands.Context, key: str):
        await self.bot.db.delete(key)
        await ctx.send('done')

    @discordutils.gov_check
    @commands.command()
    async def set_key(self, ctx, key, val):
        await self.bot.db.set(key, eval(val))
        await ctx.send(f'{key} set to {eval(val)}')
    
    @discordutils.gov_check
    @commands.command()
    async def cheese(self, ctx: commands.Context):
        await ctx.send(dir(self))
    
    
    @discordutils.gov_check
    @commands.command()
    async def a(self, ctx, i):
        nations = self.bot.get_cog('UtilCog').nations
        await nations[ctx.author.id].set(i)
        await ctx.send('Done')


def setup(bot: discordutils.DBBot):
    bot.add_cog(DebugCog(bot))
