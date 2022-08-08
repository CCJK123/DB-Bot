import discord
from discord import commands

from utils import discordutils, config, dbbot


class DebugCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
    
    @commands.command(guild_ids=config.guild_ids)
    @commands.default_permissions()
    async def get_views(self, ctx: commands.ApplicationContext):
        s = ''
        async for view in self.bot.view_table.get_all():
            s += view + ', '
        await ctx.respond(s[:-2])

    @commands.command(guild_ids=config.guild_ids)
    @commands.default_permissions()
    async def a(self, ctx: commands.ApplicationContext):
        embed = discord.Embed(title='Title!',
                              description=f'Ran the command `a` at {discord.utils.format_dt(discord.utils.utcnow())}')
        embed.set_author(name=ctx.author.name, icon_url=ctx.author.avatar.url)
        embed.set_footer(text=f'footer text {ctx.author.mention}', icon_url=ctx.author.avatar.url)
        embed.set_thumbnail(url=ctx.author.avatar.url)
        await ctx.respond(embed=embed)


def setup(bot: dbbot.DBBot):
    bot.add_cog(DebugCog(bot))
