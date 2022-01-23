import discord
from discord.ext import commands

from utils import discordutils, financeutils
import dbbot


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
    
    @discordutils.gov_check
    @commands.command()
    async def cid(self, ctx):
        await ctx.send(ctx.channel.id)
    
    @discordutils.gov_check
    @commands.command()
    async def a(self, ctx):
        await ctx.send(self.bot._connection._view_store.persistent_views)

    @discordutils.gov_check
    @commands.command()
    async def b(self, ctx):
        await ctx.send(list(view.is_dispatching() for view in self.bot._connection._view_store.persistent_views))

    @discordutils.gov_check
    @commands.command()
    async def d(self, ctx):
        await ctx.send(embed=discordutils.construct_embed({'F': ctx.author.mention}))

def setup(bot: dbbot.DBBot):
    bot.add_cog(DebugCog(bot))
