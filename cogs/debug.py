from discord.ext import commands

import discordutils


class DebugCog(discordutils.CogBase):
    def __init__(self, bot: discordutils.DBBot):
        super().__init__(bot, __name__)
    
    @commands.command()
    async def get_keys(self, ctx: commands.Context):
        await ctx.send(await self.bot.db.keys())

    @commands.command()
    async def get_key(self, ctx: commands.Context, key: str):
        await ctx.send(await self.bot.db.get(key))

    @commands.command()
    async def del_key(self, ctx: commands.Context, key: str):
        await self.bot.db.delete(key)
        await ctx.send('done')

    @commands.command()
    async def set_key(self, ctx, key, val):
        await self.bot.db.set(key, eval(val))
        await ctx.send(f'{key} set to {eval(val)}')
    
    @commands.command()
    async def cheese(self, ctx: commands.Context):
        await ctx.send(dir(self))
    
    @commands.command()
    async def test(self, ctx, o):
        nations = self.bot.get_cog('UtilCog').nations
        if o == '0':
            await ctx.send(await nations['1'].get() or 'A')
        elif o == '1':
            await ctx.send(await nations['1'].set('1') or 'A')
        elif o == '2':
            await ctx.send(await nations['1'].delete() or 'A')
        elif o == '3':
            await ctx.send(await nations['1'].get(None) or 'A')
        else:
            await ctx.send(await nations.get())
    
    @commands.command()
    async def a(self, ctx, i):
        nations = self.bot.get_cog('UtilCog').nations
        await nations[ctx.author.id].set(i)
        await ctx.send('Done')


def setup(bot: discordutils.DBBot):
    bot.add_cog(DebugCog(bot))
