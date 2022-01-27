import operator

import discord
from discord import commands

from utils import discordutils, pnwutils, config
import dbbot


class OptionsCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

    options = commands.SlashCommandGroup('options', "Edit the bot's options", guild_ids=config.guild_ids,
                                         default_permission=False, permissions=[commands.permissions.CommandPermission(
                                             config.gov_role_id, type=2, permission=True)])

    request_options = options.create_subgroup('request', 'Set options for request!')
    request_options.guild_ids = config.guild_ids

    @request_options.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def channel(self, ctx: discord.ApplicationContext,
                      kind: commands.Option(str, 'Channel type', name='type', choices=('process', 'withdraw'))
                      ) -> None:
        finance_cog = self.bot.get_cog('FinanceCog')
        """Set this channel to either the process or the withdrawal channel"""
        if kind == 'process':
            await finance_cog.set(ctx.channel)
        else:
            await finance_cog.withdrawal_channel.set(ctx.channel)
        await ctx.respond(f'{kind.capitalize()} channel set!')

    @request_options.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def war_aid(self, ctx: discord.ApplicationContext) -> None:
        """Toggle the war aid option"""
        finance_cog = self.bot.get_cog('FinanceCog')
        await finance_cog.has_war_aid.transform(operator.not_)
        await ctx.respond(f'War Aid is now {(not await finance_cog.has_war_aid.get()) * "not "}available!')

    @request_options.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def infra_rebuild_cap(self, ctx: discord.ApplicationContext,
                                cap: commands.Option(int, 'What level to provide aid up to', min_value=0)) -> None:
        """Set the infra rebuild cap for war aid"""
        finance_cog = self.bot.get_cog('FinanceCog')
        await finance_cog.infra_rebuild_cap.set(50 * round(cap / 50))
        await ctx.respond('The infrastructure rebuild cap has been set to '
                          f'{await finance_cog.infra_rebuild_cap.get()}.')

    war_detector_options = options.create_subgroup('war_detector', "Options for the bot's war detector")
    war_detector_options.guild_ids = config.guild_ids

    @war_detector_options.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def losing(self, ctx: discord.ApplicationContext) -> None:
        """Toggles whether or not to check for losing wars"""
        war_detector_cog = self.bot.get_cog('WarDetectorCog')
        await ctx.send(f'Losing wars will now {"not " * await war_detector_cog.check_losing.get()}be checked!')
        await war_detector_cog.check_losing.transform(operator.not_)

    @war_detector_options.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def channel(self, ctx: discord.ApplicationContext,
                      kind: commands.Option(str, 'Channel type', name='type',
                                            choices=('attack', 'defend', 'lose'))
                      ) -> None:
        """Sets the attack, defend and lose channels"""
        war_detector_cog = self.bot.get_cog('WarDetectorCog')
        if kind == 'attack':
            channel = war_detector_cog.att_channel
            kind_text = 'Offensive'
        elif kind == 'defend':
            channel = war_detector_cog.def_channel
            kind_text = 'Defensive'
        else:
            channel = war_detector_cog.lose_channel
            kind_text = 'Losing'
        await channel.set(ctx.channel)
        await ctx.respond(f'{kind_text} wars channel set!')

    market_options = options.create_subgroup('market', 'Edit the market options!')
    market_options.guild_ids = config.guild_ids

    @market_options.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def open(self, ctx: discord.ApplicationContext):
        """Open or close the market"""
        bank_cog = self.bot.get_cog('BankCog')
        await bank_cog.market_open.transform(operator.not_)
        s = 'open' if await bank_cog.market_open.get() else 'closed'
        await ctx.respond(f'The market is now {s}!')

    @market_options.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def set_price(self, ctx: discord.ApplicationContext,
                        b_s: commands.Option(str, 'Buying or Selling price?', choices=('buying', 'selling')),
                        res_name: commands.Option(str, 'Resource to set price', choices=pnwutils.constants.market_res),
                        price: commands.Option(int, 'Resource price', min_value=0)):
        """Set the buying/selling price of a resource"""
        bank_cog = self.bot.get_cog('BankCog')
        values = await bank_cog.market_values.get()
        values[b_s == 'selling'][pnwutils.constants.market_res.index(res_name)] = price
        await bank_cog.market_values.request_options(values)
        await ctx.respond(f'The {b_s} price of {res_name} has been set to {price} ppu.')

    @market_options.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def set_stock(self, ctx: discord.ApplicationContext,
                        res_name: commands.Option(str, 'resource to set stock', choices=pnwutils.constants.market_res),
                        stock: commands.Option(int, 'Resource stock', min_value=0)):
        """Set the stocks of a resource"""
        bank_cog = self.bot.get_cog('BankCog')
        values = await bank_cog.market_values.get()
        values[2][pnwutils.constants.market_res.index(res_name)] = stock
        await bank_cog.market_values.request_options(values)
        await ctx.respond(f'The stock of {res_name} has been set to {stock} tons.')


def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(OptionsCog(bot))
