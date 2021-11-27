from __future__ import annotations

from discord.ext import commands
import discord

import discordutils
import pnwutils
import financeutils


class BankCog(discordutils.CogBase):
    def __init__(self, bot: discordutils.DBBot):
        super().__init__(bot, __name__)
        self.balances = discordutils.MappingProperty(self, 'balances')

    @property
    def nations(self):
        return self.bot.get_cog('UtilCog').nations

    async def resolve_balance(self, i: int) -> pnwutils.Resources:
        return pnwutils.Resources()

    @commands.group(invoke_without_command=True)
    async def bank(self, ctx: commands.Context):
        await ctx.send('Usage: ')

    @bank.command(aliases=('bal',))
    async def balance(self, ctx: commands.Context):
        if await self.nations.get(None) is None:
            await self.nations.set({})
        nation_id = await self.nations[ctx.author.id].get(None)
        if nation_id is None:
            await ctx.send('Your nation id has not been set!')
            return

        resources = await self.balances[nation_id].get(None)
        if resources is None:
            # calculate balance
            resources = await self.resolve_balance(nation_id)
            await ctx.send(f"{ctx.author.mention}'s Balance has been calculated to be:",
                           embed=resources.create_embed(),
                           allowed_mentions=discord.AllowedMentions.none())
            await ctx.send('If you know these values to be erroneous, '
                           'this might due to a transaction occurring more than 14 days ago.'
                           'Please ask a Bank Guardian to help adjust these values.')

        await ctx.send(f"{ctx.author.mention}'s Balance",
                       embed=resources.create_embed(),
                       allowed_mentions=discord.AllowedMentions.none())

    @bank.command()
    async def adjust(self, ctx: commands.Context, member: discord.Member):
        nation_id = await self.nations[member.id].get(None)
        if nation_id is None:
            await ctx.send(f"{member.mention}'s nation id has not been set!")
            return

        res_select_view = financeutils.ResourceSelectView(ctx.author.id)
        await ctx.send('What resources would you like to adjust?', view=res_select_view)
        for res in await res_select_view.result():
            await ctx.send(f'How much would you like to adjust {res} by?')

        resources = await self.balances[nation_id].get(None)
        if resources is None:
            pass

    @bank.command()
    async def set(self, ctx: commands.Context, member: discord.Member):
        nation_id = await self.nations[ctx.author.id].get(None)
        if nation_id is None:
            await ctx.send(f"{member.mention}'s nation id has not been set!",
                           allowed_mentions=discord.AllowedMentions.none())
            return

        res_select_view = financeutils.ResourceSelectView(ctx.author.id)
        await ctx.send('What resources would you like to set?', view=res_select_view)
        for res in await res_select_view.result():
            await ctx.send(f'What would you like to set {res} to?')


def setup(bot: discordutils.DBBot):
    bot.add_cog(BankCog(bot))
