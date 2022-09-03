import typing

import discord
from discord.ext import commands

from utils import discordutils, pnwutils, config, dbbot


class OptionsCog(commands.GroupCog, discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.channel_ids = bot.database.get_kv('channel_ids')

    async def on_ready(self):
        await self.bot.database.execute('INSERT INTO kv_bools(key, value) VALUES ($1, $2) ON CONFLICT (key) DO NOTHING',
                                        'has_war_aid', False)

    request_options = discord.app_commands.Group(name='request', description='Set options for request!')

    @request_options.command(name='channel')
    @discord.app_commands.rename(kind='type')
    @discord.app_commands.describe(kind='Channel Type')
    async def channel_request(self, interaction: discord.Interaction,
                              kind: typing.Literal['process', 'withdrawal']
                              ) -> None:
        """Set this channel to either the finance process or the withdrawal channel"""
        await self.channel_ids.set(f'{kind}_channel', interaction.channel_id)
        await interaction.response.send_message(f'{kind.capitalize()} channel set!')

    @request_options.command()
    @discord.app_commands.default_permissions()
    async def war_aid(self, interaction: discord.Interaction) -> None:
        """Toggle the war aid option"""
        now = await self.bot.database.get_kv('kv_bools').update('value = NOT value').where(
            key='has_war_aid').returning_val('value')
        await interaction.response.send_message(f'War Aid is now {(not now) * "not "}available!')

    new_war_detector_options = discord.app_commands.Group(name='war_detector',
                                                          description='Options for the new war detector')

    @new_war_detector_options.command(name='channel')
    @discord.app_commands.rename(kind='type')
    @discord.app_commands.describe(
        kind='Channel Type'
    )
    async def channel_new_war(
            self, interaction: discord.Interaction,
            kind: typing.Literal['offensive', 'defensive', 'updates']
    ) -> None:
        """Sets the attack, defend and update channels"""
        if kind == 'offensive':
            key = 'offensive_channel'
            kind_text = 'Offensive wars'
        elif kind == 'defensive':
            key = 'defensive_channel'
            kind_text = 'Defensive wars'
        else:
            key = 'updates_channel'
            kind_text = 'Updates'
        await self.channel_ids.set(key, interaction.channel_id)
        await interaction.response.send_message(f'{kind_text} channel set!')

    market_options = discord.app_commands.Group(name='market', description='Options for the market system!')
    market_options.guild_ids = config.guild_ids

    @market_options.command()
    @discord.app_commands.describe(
        action='Type of price',
        res_name='Resource to set price of',
        price='Resource price'
    )
    @discord.app_commands.choices(res_name=discordutils.make_choices(pnwutils.constants.market_res))
    async def set_price(self, interaction: discord.Interaction,
                        action: typing.Literal['buying', 'selling'],
                        res_name: discord.app_commands.Choice[str],
                        price: discord.app_commands.Range[int, 0, None]):
        """Set the buying/selling price of a resource"""
        market_table = self.bot.database.get_table('market')
        await market_table.update(f'{action.removesuffix("ing")}_price = {price}').where(resource=res_name)
        await interaction.response.send_message(f'The {action} price of {res_name} has been set to {price} ppu.')

    @market_options.command()
    @discord.app_commands.describe(
        res_name='Resource to set price of',
        stock='Resource stock'
    )
    @discord.app_commands.choices(res_name=discordutils.make_choices(pnwutils.constants.market_res))
    async def set_stock(self, interaction: discord.Interaction,
                        res_name: discord.app_commands.Choice[str],
                        stock: discord.app_commands.Range[int, 0, None]):
        """Set the stocks of a resource"""
        market_table = self.bot.database.get_table('market')
        await market_table.update(f'stock = {stock}').where(resource=res_name)
        await interaction.response.send_message(f'The stock of {res_name} has been set to {stock} tons.')

    # bank_options = options.create_subgroup('bank', 'Options for the bank system!')
    # bank_options.guild_ids = config.guild_ids

    application_options = discord.app_commands.Group(name='application',
                                                     description='Options for the application system!')

    @application_options.command(name='channel')
    async def channel_application(self, interaction: discord.Interaction,
                                  kind: typing.Literal['log', 'category']):
        """Set the application category and logging channel"""
        if kind == 'log':
            await self.channel_ids.set('application_log_channel', interaction.channel_id)
            await interaction.response.send_message('Application log channel set!')
            return
        if interaction.channel.category is None:
            await interaction.response.send_message('This channel is not in a category! Aborting...')
            return
        await self.channel_ids.set('application_category', interaction.channel.category.id)
        await interaction.response.send_message(f'Application category set to {interaction.channel.category.name}!')

    logging_options = discord.app_commands.Group(name='logging', description='Options for the logging system!')
    logging_options.guild_ids = config.guild_ids

    @logging_options.command()
    async def channel(self, interaction: discord.Interaction):
        """Set the logging channel"""
        await self.channel_ids.set('logging_channel', interaction.channel_id)
        await interaction.response.send_message('Logging channel set!')


async def setup(bot: dbbot.DBBot) -> None:
    await bot.add_cog(OptionsCog(bot))
