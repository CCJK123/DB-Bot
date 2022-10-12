import asyncio

import discord

from utils import discordutils, pnwutils, dbbot, config


class MarketCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.market_table = self.bot.database.get_table('market')
        self.users_table = self.bot.database.get_table('users')

    async def on_ready(self):
        pass
        # to initialise the market table at first
        await self.market_table.insert_many('ordering', 'resource', values=enumerate(pnwutils.constants.market_res)
                                            ).on_conflict('(resource)').action_nothing()

    market = discord.app_commands.Group(name='market', description='A market to buy and sell resources from the bank')

    @market.command()
    async def prices(self, interaction: discord.Interaction):
        """List out the prices of resources in the market"""
        values = await self.market_table.select('ordering', 'buy_price', 'sell_price').order_by('1')
        print(values)
        await interaction.response.send_message(embeds=(
            discordutils.create_embed(pnwutils.constants.market_res_cap, map(lambda e: f"{e['buy_price']:,}", values),
                                      description='Buying Prices', title='Market Trading Prices'),
            discordutils.create_embed(pnwutils.constants.market_res_cap, map(lambda e: f"{e['sell_price']:,}", values),
                                      description='Selling Prices')
        ))

    @market.command()
    async def stocks(self, interaction: discord.Interaction):
        """List out the stocks of resources in the market"""
        values = await self.market_table.select('ordering', 'stock').order_by('1')
        print(values)
        await interaction.response.send_message(embed=discordutils.create_embed(
            pnwutils.constants.market_res_cap, map(lambda e: f"{e['stock']:,}", values), title='Market Stocks'))

    @market.command()
    @discord.app_commands.describe(
        res_name='Resource to buy',
        amt='How much to buy'
    )
    @discord.app_commands.choices(res_name=discordutils.make_choices(pnwutils.constants.market_res))
    async def buy(self, interaction: discord.Interaction,
                  res_name: str, amt: discord.app_commands.Range[int, 1, None]):
        """Purchase some amount of a resource for money"""
        await interaction.response.defer(ephemeral=True)
        bal_rec = await self.users_table.select_val('balance').where(discord_id=interaction.user.id)
        if bal_rec is None:
            await interaction.followup.send('You have not been registered!')
            return

        rec = await self.market_table.select_row('buy_price', 'stock').where(resource=res_name)
        if rec['buy_price'] is None:
            await interaction.followup.send(
                f'{res_name.title()} is not available for purchase at this time!', ephemeral=True
            )
            return
        if rec['stock'] < amt:
            await interaction.followup.send(
                f'The stocks are too low to buy that much {res_name}! '
                f'(Trying to purchase {amt:,} ton{"s" * (amt != 1)} out of '
                f'{rec["stock"]:,} ton{"s" * (amt != 1)} of stock remaining)',
                ephemeral=True)
            return

        res = pnwutils.Resources(**bal_rec)
        total_price = amt * rec['buy_price']
        if res.money < total_price:
            await interaction.followup.send(f'You do not have enough money deposited to do that! '
                                            f'(Trying to spend {total_price:,} out of {res.money:,} dollars)',
                                            ephemeral=True)
            return

        agree_terms = discordutils.Choices('Yes', 'No')
        await interaction.followup.send(
            'We provide below-market prices to help sustain our internal economy, '
            'so that all our members and the alliance as a whole can benefit. '
            'Thus, if you attempt to turn a profit by selling alliance-bought goods on the open market, '
            'you would be directly harming the alliance and your fellow assassins. '
            'Do you promise to not resell alliance-bought goods on the open market for personal gain?',
            view=agree_terms
        )
        try:
            if await agree_terms.result() == 'No':
                await interaction.followup.send('Exiting...', ephemeral=True)
                return None
        except asyncio.TimeoutError:
            await interaction.followup.send('You took too long to respond! Exiting...', ephemeral=True)
            return

        embed = discord.Embed()
        embed.add_field(name='Paying', value=f'{config.resource_emojis["money"]} {total_price}')
        embed.add_field(name='Receiving', value=f'{config.resource_emojis[res_name]} {amt}')
        embed.add_field(name='Price Per Unit', value=rec['buy_price'])
        confirm = discordutils.Choices('Yes', 'No')
        await interaction.followup.send(
            'Please confirm your transaction.',
            embed=embed, view=confirm, ephemeral=True
        )
        try:
            rej = await confirm.result() == 'No'
        except asyncio.TimeoutError:
            await interaction.followup.send('You took too long to respond! Exiting...', ephemeral=True)
            return
        if rej:
            await interaction.followup.send('Cancelling transaction and exiting...', ephemeral=True)
            return
        final_bal = pnwutils.Resources(
            **await self.users_table.update(
                f'balance.money = (balance).money - {total_price}, '
                f'balance.{res_name} = (balance).{res_name} + {amt}'
            ).where(discord_id=interaction.user.id).returning_val('balance'))
        await asyncio.gather(
            self.market_table.update(f'stock = stock - {amt}').where(resource=res_name),
            interaction.followup.send(
                'Transaction complete!', embed=final_bal.create_balance_embed(interaction.user),
                ephemeral=True),
            self.bot.log(embed=discordutils.create_embed(
                user=interaction.user,
                description=f'{interaction.user.mention} purchased {amt:,} ton{"s" * (amt != 1)} of {res_name} '
                            f'from the bank at {rec["buy_price"]} ppu for ${total_price:,}'))
        )
        return

    @market.command()
    @discord.app_commands.describe(
        res_name='Resource to sell',
        amt='How much to sell'
    )
    @discord.app_commands.choices(res_name=discordutils.make_choices(pnwutils.constants.market_res))
    async def sell(self, interaction: discord.Interaction,
                   res_name: str, amt: discord.app_commands.Range[int, 1, None]):
        """Sell some amount of a resource for money"""
        await interaction.response.defer(ephemeral=True)
        bal_amount = await self.users_table.select_val(f'(balance).{res_name}'
                                                       ).where(discord_id=interaction.user.id)
        if bal_amount is None:
            await interaction.followup.send('You have not been registered!')
            return
        price = await self.market_table.select_val('sell_price').where(resource=res_name)
        if price is None:
            await interaction.followup.send(
                f'{res_name.title()} is cannot be sold at this time!', ephemeral=True
            )
            return
        if bal_amount < amt:
            await interaction.followup.send(
                f'You do not have enough {res_name} deposited to do that! '
                f'(Trying to sell {amt:,} ton{"s" * (amt != 1)} when your balance only contains '
                f'{bal_amount:,} ton{"s" * (bal_amount != 1)})',
                ephemeral=True)
            return
        total_price = amt * price
        embed = discord.Embed()
        embed.add_field(name='Paying', value=f'{config.resource_emojis[res_name]} {amt}')
        embed.add_field(name='Receiving', value=f'{config.resource_emojis["money"]} {total_price}')
        embed.add_field(name='Price Per Unit', value=price)
        confirm = discordutils.Choices('Yes', 'No')
        await interaction.followup.send(
            'Please confirm your transaction.',
            embed=embed, view=confirm, ephemeral=True
        )
        try:
            rej = await confirm.result() == 'No'
        except asyncio.TimeoutError:
            await interaction.followup.send('You took too long to respond! Exiting...', ephemeral=True)
            return
        if rej:
            await interaction.followup.send('Cancelling transaction and exiting...', ephemeral=True)
            return

        final_bal = pnwutils.Resources(
            **await self.users_table.update(
                f'balance.money = (balance).money + {total_price}, '
                f'balance.{res_name} = (balance).{res_name} - {amt}'
            ).where(discord_id=interaction.user.id).returning_val('balance'))
        await self.market_table.update(f'stock = stock + {amt}').where(resource=res_name)
        await asyncio.gather(
            interaction.followup.send(
                'Transaction complete!', embed=final_bal.create_balance_embed(interaction.user),
                ephemeral=True),
            self.bot.log(embed=discordutils.create_embed(
                user=interaction.user,
                description=f'{interaction.user.mention} sold {amt:,} ton{"s" * (amt != 1)} of {res_name} to the bank '
                            f'at {price} ppu for ${total_price:,}'))
        )
        return


async def setup(bot: dbbot.DBBot):
    await bot.add_cog(MarketCog(bot))
