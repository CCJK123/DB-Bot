import operator

import discord
from discord import commands

from utils import discordutils, pnwutils, config, dbbot


class MarketCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.market_table = self.bot.database.get_table('market')
        self.users_table = self.bot.database.get_table('users')

    async def on_ready(self):
        pass
        #await self.market_table.insert_many('resource', values=pnwutils.constants.market_res
        #                                    ).on_conflict('(resource)').action_nothing()

    market = commands.SlashCommandGroup('market', 'A market to buy and sell resources from the bank',
                                        guild_ids=config.guild_ids)

    @market.command(guild_ids=config.guild_ids, hidden=True)
    async def prices(self, ctx: discord.ApplicationContext):
        """List out the prices of resources in the market"""
        values = await self.market_table.select('buy_price', 'sell_price')
        await ctx.respond(embeds=(
            discordutils.create_embed(pnwutils.constants.market_res, map(operator.itemgetter('buy_price'), values),
                                      description='Buying Prices', title='Bank Trading Prices'),
            discordutils.create_embed(pnwutils.constants.market_res, map(operator.itemgetter('sell_price'), values))
        ))

    @market.command(guild_ids=config.guild_ids)
    async def stocks(self, ctx: discord.ApplicationContext):
        """List out the stocks of resources in the market"""
        values = await self.market_table.select('stock')
        await ctx.respond(embed=discordutils.create_embed(
            pnwutils.constants.market_res, map(operator.itemgetter('stock'), values), title='Bank Stocks'))

    @market.command(guild_ids=config.guild_ids)
    async def buy(self, ctx: discord.ApplicationContext,
                  res_name: discord.Option(str, 'Choose resource to buy', choices=pnwutils.constants.market_res),
                  amt: discord.Option(int, 'How much to buy', min_value=0)):
        """Purchase some amount of a resource for money"""
        bal_rec = await self.users_table.select_val('balance').where(discord_id=ctx.author.id)
        if bal_rec is None:
            await ctx.respond('You have not been registered!')
            return

        rec = await self.market_table.select_row('buy_price', 'stock').where(resource=res_name)
        if rec['stock'] < amt:
            await ctx.respond(f'The stocks are too low to buy that much {res_name}! '
                              f'(Requested to purchase {amt} out of {rec["stock"]} stock remaining))',
                              ephemeral=True)
            return

        res = pnwutils.Resources(**await bal_rec)
        total_price = amt * rec['buy_price']
        if res.money < total_price:
            await ctx.respond(f'You do not have enough money deposited to do that! '
                              f'(Trying to spend {total_price} out of {res.money} dollars)',
                              ephemeral=True)
            return
        final_bal = pnwutils.Resources(
            **await self.users_table.update(f'balance.money = balance.money - {total_price}, '
                                            f'balance.{res_name} = balance.{res_name} + {amt}'
                                            ).where(discord_id=ctx.author.id).returning_val('balance'))
        await self.market_table.update(f'stock = stock - {amt}').where(resource=res_name)
        await ctx.respond('Transaction complete!', embed=final_bal.create_balance_embed(ctx.author),
                          ephemeral=True)
        return

    @market.command(guild_ids=config.guild_ids)
    async def sell(self, ctx: discord.ApplicationContext,
                   res_name: discord.Option(str, 'Choose resource to sell', choices=pnwutils.constants.market_res),
                   amt: discord.Option(int, 'How much to sell', min_value=0)):
        """Sell some amount of a resource for money"""
        bal_amount = await self.users_table.select_val(f'balance.{res_name}').where(discord_id=ctx.author.id)
        if bal_amount is None:
            await ctx.respond('You have not been registered!')
            return
        price = await self.market_table.select_row('sell_price').where(resource=res_name)
        if bal_amount < amt:
            await ctx.respond(f'You do not have enough {res_name} deposited to do that! '
                              f'(Trying to sell {amt} when balance only contains {bal_amount})',
                              ephemeral=True)
            return
        final_bal = pnwutils.Resources(
            **await self.users_table.update(f'balance.money = balance.money + {amt * price}, '
                                            f'balance.{res_name} = balance.{res_name} - {amt}'
                                            ).where(discord_id=ctx.author.id).returning_val('balance'))
        await self.market_table.update(f'stock = stock + {amt}').where(resource=res_name)
        await ctx.respond('Transaction complete!', embed=final_bal.create_balance_embed(ctx.author),
                          ephemeral=True)
        return


def setup(bot: dbbot.DBBot):
    bot.add_cog(MarketCog(bot))
