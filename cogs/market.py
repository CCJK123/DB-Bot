import asyncio
import operator

import discord

from utils import discordutils, pnwutils, dbbot


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
            discordutils.create_embed(pnwutils.constants.market_res_cap, map(operator.itemgetter('buy_price'), values),
                                      description='Buying Prices', title='Bank Trading Prices'),
            discordutils.create_embed(pnwutils.constants.market_res_cap, map(operator.itemgetter('sell_price'), values),
                                      description='Selling Prices')
        ))

    @market.command()
    async def stocks(self, interaction: discord.Interaction):
        """List out the stocks of resources in the market"""
        values = await self.market_table.select('ordering', 'stock').order_by('1')
        print(values)
        await interaction.response.send_message(embed=discordutils.create_embed(
            pnwutils.constants.market_res_cap, map(operator.itemgetter('stock'), values), title='Bank Stocks'))

    @market.command()
    @discord.app_commands.describe(
        res_name='Resource to buy',
        amt='How much to buy'
    )
    @discord.app_commands.choices(res_name=discordutils.make_choices(pnwutils.constants.market_res))
    async def buy(self, interaction: discord.Interaction,
                  res_name: str, amt: discord.app_commands.Range[int, 0, None]):
        """Purchase some amount of a resource for money"""
        await interaction.response.defer()
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
                f'(Requested to purchase {amt} out of {rec["stock"]} stock remaining))',
                ephemeral=True)
            return

        res = pnwutils.Resources(**bal_rec)
        total_price = amt * rec['buy_price']
        if res.money < total_price:
            await interaction.followup.send(f'You do not have enough money deposited to do that! '
                                                    f'(Trying to spend {total_price} out of {res.money} dollars)',
                                                    ephemeral=True)
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
            self.bot.log(embeds=(
                discordutils.create_embed(
                    user=interaction.user,
                    description=f"{interaction.user.mention} purchased {amt} tons of {res_name} for ${total_price}"),
                final_bal.create_embed(title='Final Balance')))
        )
        return

    @market.command()
    @discord.app_commands.describe(
        res_name='Resource to sell',
        amt='How much to sell'
    )
    @discord.app_commands.choices(res_name=discordutils.make_choices(pnwutils.constants.market_res))
    async def sell(self, interaction: discord.Interaction,
                   res_name: str, amt: discord.app_commands.Range[int, 0, None]):
        """Sell some amount of a resource for money"""
        await interaction.response.defer()
        bal_amount = await self.users_table.select_val(f'(balance).{res_name}'
                                                       ).where(discord_id=interaction.user.id)
        if bal_amount is None:
            await interaction.followup.send('You have not been registered!')
            return
        price = await self.market_table.select_val('sell_price').where(resource=res_name)
        print(price)
        if price is None:
            await interaction.followup.send(
                f'{res_name.title()} is not available for selling at this time!', ephemeral=True
            )
            return
        if bal_amount < amt:
            await interaction.followup.send(f'You do not have enough {res_name} deposited to do that! '
                                                    f'(Trying to sell {amt} when balance only contains {bal_amount})',
                                                    ephemeral=True)
            return
        final_bal = pnwutils.Resources(
            **await self.users_table.update(
                f'balance.money = (balance).money + {amt * price}, '
                f'balance.{res_name} = (balance).{res_name} - {amt}'
            ).where(discord_id=interaction.user.id).returning_val('balance'))
        await self.market_table.update(f'stock = stock + {amt}').where(resource=res_name)
        await asyncio.gather(
            interaction.followup.send(
                'Transaction complete!', embed=final_bal.create_balance_embed(interaction.user),
                ephemeral=True),
            self.bot.log(embeds=(
                discordutils.create_embed(
                    user=interaction.user,
                    description=f"{interaction.user.mention} sold {amt} tons of {res_name} for ${amt * price}"),
                final_bal.create_embed(title='Final Balance')))
        )
        return


async def setup(bot: dbbot.DBBot):
    await bot.add_cog(MarketCog(bot))
