import discord
from discord import commands

from utils import discordutils, pnwutils, config, dbbot


class OptionsCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.channel_ids = bot.database.get_kv('channel_ids')

    async def on_ready(self):
        await self.bot.database.execute('INSERT INTO kv_bools(key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING',
                                        'has_war_aid', False)

    options = commands.SlashCommandGroup('options', "Edit the options of the bot!", guild_ids=config.guild_ids,
                                         default_member_permissions=discord.Permissions())

    request_options = options.create_subgroup('request', 'Set options for request!')
    request_options.guild_ids = config.guild_ids

    @request_options.command(name='channel', guild_ids=config.guild_ids)
    async def channel_request(self, ctx: discord.ApplicationContext,
                              kind: discord.Option(str, 'Channel type', name='type', choices=('process', 'withdrawal'))
                              ) -> None:
        """Set this channel to either the finance process or the withdrawal channel"""
        await self.channel_ids.set(f'{kind}_channel', ctx.channel.id)
        await ctx.respond(f'{kind.capitalize()} channel set!')

    @request_options.command(guild_ids=config.guild_ids)
    @commands.default_permissions()
    async def war_aid(self, ctx: discord.ApplicationContext) -> None:
        """Toggle the war aid option"""
        now = await self.bot.database.get_kv('kv_bools').update('value = NOT value').where(
            key='has_war_aid').returning_val('value')
        await ctx.respond(f'War Aid is now {(not now) * "not "}available!')

    @request_options.command(guild_ids=config.guild_ids)
    async def infra_rebuild_cap(self, ctx: discord.ApplicationContext,
                                cap: discord.Option(int, 'What level to provide aid up to', min_value=0)) -> None:
        """Set the infra rebuild cap for war aid"""
        ints_table = self.bot.database.get_kv('kv_ints')
        cap = 100 * (cap // 100)
        await ints_table.set('infra_rebuild_cap', cap)
        await ctx.respond(f'The infrastructure rebuild cap has been set to {cap}.')

    new_war_detector_options = options.create_subgroup('war_detector', "Options for the new war detector")
    new_war_detector_options.guild_ids = config.guild_ids

    @new_war_detector_options.command(name='channel', guild_ids=config.guild_ids)
    async def channel_new_war(self, ctx: discord.ApplicationContext,
                              kind: discord.Option(str, 'Channel type', name='type',
                                                   choices=('offensive', 'defensive', 'updates'))
                              ) -> None:
        """Sets the attack, defend and lose channels"""
        if kind == 'offensive':
            key = 'offensive_channel'
            kind_text = 'Offensive wars'
        elif kind == 'defensive':
            key = 'defensive_channel'
            kind_text = 'Defensive wars'
        else:
            key = 'updates_channel'
            kind_text = 'Updates'
        await self.channel_ids.set(key, ctx.channel_id)
        await ctx.respond(f'{kind_text} channel set!')

    market_options = options.create_subgroup('market', 'Options for the market system!')
    market_options.guild_ids = config.guild_ids

    @market_options.command(guild_ids=config.guild_ids)
    async def set_price(self, ctx: discord.ApplicationContext,
                        b_s: discord.Option(str, 'Buying or Selling price?', choices=('buying', 'selling')),
                        res_name: discord.Option(str, 'Resource to set price', choices=pnwutils.constants.market_res),
                        price: discord.Option(int, 'Resource price', min_value=0)):
        """Set the buying/selling price of a resource"""
        market_table = self.bot.database.get_table('market')
        await market_table.update(f'{b_s.removesuffix("ing")}_price = {price}').where(resource=res_name)
        await ctx.respond(f'The {b_s} price of {res_name} has been set to {price} ppu.')

    @market_options.command(guild_ids=config.guild_ids)
    async def set_stock(self, ctx: discord.ApplicationContext,
                        res_name: discord.Option(str, 'resource to set stock', choices=pnwutils.constants.market_res),
                        stock: discord.Option(int, 'Resource stock', min_value=0)):
        """Set the stocks of a resource"""
        market_table = self.bot.database.get_table('market')
        await market_table.update(f'stock = {stock}').where(resource=res_name)
        await ctx.respond(f'The stock of {res_name} has been set to {stock} tons.')

    # bank_options = options.create_subgroup('bank', 'Options for the bank system!')
    # bank_options.guild_ids = config.guild_ids

    application_options = options.create_subgroup('application', 'Options for the application system!')
    application_options.guild_ids = config.guild_ids

    @application_options.command(name='channel', guild_ids=config.guild_ids)
    async def channel_application(self, ctx: discord.ApplicationContext,
                                  kind: discord.Option(str, choices=('category', 'log'))):
        """Set the application category and logging channel"""
        if kind == 'log':
            await self.channel_ids.set('application_log_channel', ctx.channel_id)
            await ctx.respond('Application log channel set!')
            return
        if ctx.channel.category is None:
            await ctx.respond('This channel is not in a category! Aborting...')
            return
        await self.channel_ids.set('application_category', ctx.channel.category.id)
        await ctx.respond(f'Application category set to {ctx.channel.category.name}!')

    logging_options = options.create_subgroup('logging', 'Options for the logging system!')
    logging_options.guild_ids = config.guild_ids

    @logging_options.command(guild_ids=config.guild_ids)
    async def channel(self, ctx: discord.ApplicationContext):
        """Set the logging channel"""
        await self.channel_ids.set('logging_channel', ctx.channel_id)
        await ctx.respond('Logging channel set!')


def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(OptionsCog(bot))
