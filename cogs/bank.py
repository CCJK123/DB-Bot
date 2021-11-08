from __future__ import annotations

from discord.ext import commands
import discord

import util
import discordutils
import pnwutils



class BankCog(discordutils.CogBase):
    def __init__(self, bot: discordutils.DBBot):
        super().__init__(bot, __name__)
        self.balances = discordutils.MappingProperty[str, pnwutils.Resources](self, 'balances')
        if await self.nations.get(None) is None:
            await self.nations.set({})
    

    @property
    def nations(self):
        return self.bot.get_cog('UtilCog').nations
    

    @commands.group(invoke_without_command=True)
    async def bank(self, ctx: commands.Context):
        await ctx.send('Usage: ')
    

    @bank.command(aliases=('bal',))
    async def balance(self, ctx: commands.Context):
        nation_id = await self.nations[ctx.author.id].get(None)
        if nation_id is None:
            await ctx.send('Your nation id is not set!')
            return
        
        resources = await self.balances[nation_id].get(None)
        if resources is None:
            # calculate balance
            pass
        
        await ctx.send(f"{ctx.author.mention}'s Balance",
                       embed=resources.create_embed(),
                       allowed_mentions=discord.AllowedMentions.none())



def setup(bot: discordutils.DBBot):
    bot.add_cog(BankCog(bot))