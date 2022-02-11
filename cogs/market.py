import dbbot

import discord
from discord import commands

from utils import discordutils, pnwutils, config


class MarketCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.market_values = discordutils.CogProperty[list[list[int]]](self, 'market.values')

    @property
    def nations(self) -> discordutils.MappingProperty[int, str]:
        return self.bot.get_cog('UtilCog').nations  # type: ignore

    @property
    def balances(self) -> discordutils.MappingProperty[int, str]:
        return self.bot.get_cog('BankCog').balances  # type: ignore

    market = commands.SlashCommandGroup('market', 'A market to buy and sell resources from the bank',
                                        guild_ids=config.guild_ids)
    market.guild_ids = config.guild_ids

    @market.command(name='prices', guild_ids=config.guild_ids, hidden=True)
    async def _prices(self, ctx: discord.ApplicationContext):
        """List out the prices of resources in the market"""
        if await self.market_values.get(None) is None:
            await self.market_values.set([[0] * len(pnwutils.constants.market_res)] * 3)
        values = await self.market_values.get()
        await ctx.respond(embeds=(
            discordutils.construct_embed(pnwutils.constants.market_res, values[0], description='Buying Prices',
                                         title='Bank Trading Prices'),
            discordutils.construct_embed(pnwutils.constants.market_res, values[1], description='Selling Prices')
        ))

    @market.command(name='stocks', guild_ids=config.guild_ids)
    async def _stocks(self, ctx: discord.ApplicationContext):
        """List out the stocks of resources in the market"""
        values = await self.market_values.get()
        await ctx.respond(embed=discordutils.construct_embed(pnwutils.constants.market_res,
                                                             values[2], title='Bank Stocks'))

    @market.command(guild_ids=config.guild_ids)
    async def buy(self, ctx: discord.ApplicationContext,
                  res_name: commands.Option(str, 'Choose resource to buy', choices=pnwutils.constants.market_res),
                  amt: commands.Option(int, 'How much to buy', min_value=0)):
        """Purchase some amount of a resource for money"""
        values = await self.market_values.get()
        res_index = pnwutils.constants.market_res.index(res_name)
        if values[2][res_index] < amt:
            await ctx.respond('The stocks are too low to buy that much!')
            return

        bal = self.balances[await self.nations[ctx.author.id].get()]
        res = pnwutils.Resources(**await bal.get())
        res.money -= amt * values[0][res_index]
        if res.money < 0:
            await ctx.respond('You do not have enough money deposited to do that!')
            return
        res[res_name] += amt
        await bal.set(res.to_dict())
        values = await self.market_values.get()
        values[2][res_index] -= amt
        await self.market_values.set(values)
        await ctx.respond('Transaction complete!', embed=res.create_balance_embed(ctx.author.name))
        return

    @market.command(guild_ids=config.guild_ids)
    async def sell(self, ctx: discord.ApplicationContext,
                   res_name: commands.Option(str, 'Choose resource to sell', choices=pnwutils.constants.market_res),
                   amt: commands.Option(int, 'How much to sell', min_value=0)):
        """Sell some amount of a resource for money"""
        values = await self.market_values.get()
        res_index = pnwutils.constants.market_res.index(res_name)
        bal = self.balances[await self.nations[ctx.author.id].get()]
        res = pnwutils.Resources(**await bal.get())
        res[res_name.lower()] -= amt
        if res[res_name.lower()] < 0:
            await ctx.respond('You do not have enough money deposited to do that!')
            return
        res.money += amt * values[1][res_index]
        await bal.set(res.to_dict())
        values = await self.market_values.get()
        values[2][res_index] += amt
        await self.market_values.set(values)
        await ctx.respond('Transaction complete!', embed=res.create_balance_embed(ctx.author.name))
        return


def setup(bot: dbbot.DBBot):
    bot.add_cog(MarketCog(bot))
