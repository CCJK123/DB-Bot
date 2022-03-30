import discord
from discord import commands

from cogs.bank import BankCog
from utils import discordutils, config, dbbot


class DebugCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
    
    @commands.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def get_keys(self, ctx: discord.ApplicationContext):
        """Get all the keys in the DB"""
        await ctx.respond(await self.bot.database.keys())

    @commands.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def get_key(self, ctx: discord.ApplicationContext, key: str):
        """Get the value of a certain key in the DB"""
        print(a := await self.bot.database.get(key))
        await ctx.respond(a)

    @commands.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def del_key(self, ctx: discord.ApplicationContext, key: str):
        """Delete a key in the DB"""
        await self.bot.database.delete(key)
        await ctx.respond('done')

    @commands.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def set_key(self, ctx: discord.ApplicationContext, key: str, val: str):
        """Set a key in the DB to a value"""
        await self.bot.database.set(key, eval(val))
        await ctx.respond(f'{key} set to {eval(val)}')

    @commands.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def views(self, ctx: discord.ApplicationContext):
        """Temp test command"""
        await ctx.respond(self.bot.views.value)
        await ctx.respond(await self.bot.views.get())
        await ctx.respond(await self.bot.views.get_views())

    @commands.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def del_nation(self, ctx: discord.ApplicationContext):
        """Delete your nation from the registry"""
        cog = self.bot.get_cog('UtilCog')
        await cog.nations[ctx.author.id].delete()
        await ctx.respond('done')

    @commands.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def fix_types(self, ctx: discord.ApplicationContext):
        bank_cog = self.bot.get_cog('BankCog')
        assert isinstance(bank_cog, BankCog)

        n = await bank_cog.nations.get()
        new = {}
        for k, v in n.items():
            new[int(k)] = int(v)
        await bank_cog.nations.set(new)

        b = await bank_cog.balances.get()
        new = {}
        for k, v in b.items():
            new[int(k)] = v
        await bank_cog.balances.set(new)

        l = await self.bot.get_cog('FinanceCog').loans.get()
        new = {}
        for k, v in l.items():
            new[int(k)] = v
        await self.bot.get_cog('FinanceCog').loans.set(new)

        await ctx.respond('Complete!')


def setup(bot: dbbot.DBBot):
    bot.add_cog(DebugCog(bot))
