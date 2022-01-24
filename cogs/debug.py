import discord
from discord import commands

import dbbot
from utils import discordutils, config


class DebugCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

    @commands.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def get_keys(self, ctx: discord.ApplicationContext):
        await ctx.respond(await self.bot.database.keys())

    @commands.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def get_key(self, ctx: discord.ApplicationContext, key: str):
        print(a := await self.bot.database.get(key))
        await ctx.respond(a)

    @commands.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def del_key(self, ctx: discord.ApplicationContext, key: str):
        await self.bot.database.delete(key)
        await ctx.respond('done')

    @commands.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def set_key(self, ctx: discord.ApplicationContext, key: str, val: str):
        await self.bot.database.set(key, eval(val))
        await ctx.respond(f'{key} set to {eval(val)}')


def setup(bot: dbbot.DBBot):
    bot.add_cog(DebugCog(bot))
