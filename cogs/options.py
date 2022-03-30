import operator

import discord
from discord import commands

from utils import discordutils, pnwutils, config, dbbot


class OptionsCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

    options = commands.SlashCommandGroup('options', "Edit the bot's options", guild_ids=config.guild_ids,
                                         default_permission=False, permissions=[config.gov_role_permission])

    request_options = options.create_subgroup('request', 'Set options for request!')
    request_options.guild_ids = config.guild_ids

    @request_options.command(guild_ids=config.guild_ids)
    async def channel(self, ctx: discord.ApplicationContext,
                      kind: commands.Option(str, 'Channel type', name='type', choices=('process', 'withdraw'))
                      ) -> None:
        """Set this channel to either the finance process or the withdrawal channel"""
        finance_cog = self.bot.get_cog('FinanceCog')
        if kind == 'process':
            await finance_cog.process_channel.set(ctx.channel)
        else:
            await finance_cog.withdrawal_channel.set(ctx.channel)
        await ctx.respond(f'{kind.capitalize()} channel set!')

    @request_options.command(guild_ids=config.guild_ids)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def war_aid(self, ctx: discord.ApplicationContext) -> None:
        """Toggle the war aid option"""
        finance_cog = self.bot.get_cog('FinanceCog')
        await finance_cog.has_war_aid.transform(operator.not_)
        await ctx.respond(f'War Aid is now {(not await finance_cog.has_war_aid.get()) * "not "}available!')

    @request_options.command(guild_ids=config.guild_ids)
    async def infra_rebuild_cap(self, ctx: discord.ApplicationContext,
                                cap: commands.Option(int, 'What level to provide aid up to', min_value=0)) -> None:
        """Set the infra rebuild cap for war aid"""
        finance_cog = self.bot.get_cog('FinanceCog')
        await finance_cog.infra_rebuild_cap.set(50 * round(cap / 50))
        await ctx.respond('The infrastructure rebuild cap has been set to '
                          f'{await finance_cog.infra_rebuild_cap.get()}.')

    war_detector_options = options.create_subgroup('war_detector', "Options for the bot's war detector")
    war_detector_options.guild_ids = config.guild_ids

    @war_detector_options.command(name='channel', guild_ids=config.guild_ids)
    async def channel_(self, ctx: discord.ApplicationContext,
                       kind: commands.Option(str, 'Channel type', name='type',
                                             choices=('attack', 'defend', 'updates'))
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
            channel = war_detector_cog.updates_channel
            kind_text = 'Losing'
        await channel.set(ctx.channel)
        await ctx.respond(f'{kind_text} wars channel set!')

    market_options = options.create_subgroup('market', 'Options for the market system!')
    market_options.guild_ids = config.guild_ids

    @market_options.command(guild_ids=config.guild_ids)
    async def set_price(self, ctx: discord.ApplicationContext,
                        b_s: commands.Option(str, 'Buying or Selling price?', choices=('buying', 'selling')),
                        res_name: commands.Option(str, 'Resource to set price', choices=pnwutils.constants.market_res),
                        price: commands.Option(int, 'Resource price', min_value=0)):
        """Set the buying/selling price of a resource"""
        market_cog = self.bot.get_cog('MarketCog')
        values = await market_cog.market_values.get()
        values[b_s == 'selling'][pnwutils.constants.market_res.index(res_name)] = price
        await market_cog.market_values.set(values)
        await ctx.respond(f'The {b_s} price of {res_name} has been set to {price} ppu.')

    @market_options.command(guild_ids=config.guild_ids)
    async def set_stock(self, ctx: discord.ApplicationContext,
                        res_name: commands.Option(str, 'resource to set stock', choices=pnwutils.constants.market_res),
                        stock: commands.Option(int, 'Resource stock', min_value=0)):
        """Set the stocks of a resource"""
        market_cog = self.bot.get_cog('MarketCog')
        values = await market_cog.market_values.get()
        values[2][pnwutils.constants.market_res.index(res_name)] = stock
        await market_cog.market_values.set(values)
        await ctx.respond(f'The stock of {res_name} has been set to {stock} tons.')

    bank_options = options.create_subgroup('bank', 'Options for the bank system!')
    bank_options.guild_ids = config.guild_ids

    @bank_options.command(guild_ids=config.guild_ids)
    async def set_offshore(self, ctx: discord.ApplicationContext,
                           off_id: commands.Option(int, 'ID of the offshore alliance')):
        """Set the ID of the alliance's offshore."""
        bank_cog = self.bot.get_cog('BankCog')
        confirm_view = discordutils.Choices('Yes', 'No', user_id=ctx.author.id)
        await ctx.respond(f'Is this the offshore? [Link]({pnwutils.link.alliance(off_id)})',
                          view=confirm_view)
        if await confirm_view.result() == 'Yes':
            await bank_cog.offshore_id.set(str(off_id))
            await ctx.respond('Offshore id has been set!')
            return
        await ctx.respond('Aborting!')

    application_options = options.create_subgroup('application', 'Options for the application system!')
    application_options.guild_ids = config.guild_ids

    @application_options.command(guild_ids=config.guild_ids)
    async def set(self, ctx: discord.ApplicationContext,
                  kind: commands.Option(str, choices=('category', 'log'))):
        """Set the application category and logging channel"""
        application_cog = self.bot.get_cog('ApplicationCog')
        if kind == 'log':
            await application_cog.application_log.set(ctx.channel)
            await ctx.respond('Application log channel set!')
            return
        await application_cog.application_category.set(ctx.channel.category)
        await ctx.respond(f'Application category set to {ctx.channel.category.name}!')


def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(OptionsCog(bot))
