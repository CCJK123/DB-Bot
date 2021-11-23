import aiohttp
from collections import defaultdict
import operator

import discord
from discord.ext import commands

import pnwutils
import discordutils



class UtilCog(discordutils.CogBase):
    def __init__(self, bot: discordutils.DBBot):
        super().__init__(bot, __name__)
        self.nations = discordutils.MappingProperty(self, 'nations')



    @commands.command()
    async def set_nation(self, ctx: commands.Context, nation_id: str = ''):
        if await self.nations.get(None) is None:
            await self.nations.set({})
        if nation_id == '':
            if '/' in ctx.author.display_name:
                try:
                    int(nation_id := ctx.author.display_name.split('/')[1])
                except ValueError:
                    await ctx.send('Please provide your nation id!')
                    return
                await self.nations[ctx.author.id].set(nation_id)
                await ctx.send('You have been registered to our database!')
                return
            await ctx.send('Please provide your nation id!')
            return

        
        nation_prefix = pnwutils.Constants.base_url + 'nation/id='
        if nation_id.startswith(nation_prefix):
            nation_id = nation_id[len(nation_prefix):]
        
        try: 
            int(nation_id)
        except ValueError:
            await ctx.send("That isn't a number!")
            return
        
        nation_confirm_choice = discordutils.Choices('Yes', 'No', user_id=ctx.author.id)
        await ctx.send(f'Is this your nation? ' + pnwutils.Link.nation(nation_id), view=nation_confirm_choice)
        if await nation_confirm_choice.result() == 'Yes':
            await self.nations[ctx.author.id].set(nation_id)
            await ctx.send('You have been registered to our database!')

    @commands.command()
    async def list_registered(self, ctx: commands.Context):
        m = '\n'.join(f'<@{disc_id}> - {pnwutils.Link.nation(nation_id)}' 
            for disc_id, nation_id in (await self.nations.get()).items())
        await ctx.send(m if m else 'There are no registrations!',
             allowed_mentions=discord.AllowedMentions.none())
            

    @commands.command()
    async def check_ran_out(self, ctx: commands.Context):
        aa_query_str = '''
        query alliance_res($alliance_id: [Int], $page: Int){
          nations(alliance_id: $alliance_id, first: 500, page: $page){
            paginatorInfo {
              hasMorePages
            }
            data{
              id
              food
              uranium
              cities{
                nuclearpower
              }
            }
          }
        }
        '''
        async with aiohttp.ClientSession() as session:
            data = (await pnwutils.API.post_query(session, aa_query_str, {'alliance_id': pnwutils.Config.aa_id},
                                                  'nations', True))['data']
        result = defaultdict(str)
        for nation in data:
            has_food = not nation['food']
            has_ura = not nation['uranium'] and any(map(operator.itemgetter('nuclearpower'), nation['cities']))

            if has_food:
                result[nation['id']] += 'food'
            if has_food and has_ura:
                result[nation['id']] += ' and '
            if has_ura:
                result[nation['id']] += 'uranium'

        await ctx.send('\n'.join(f'{pnwutils.nation_link(n)} has ran out of {ran_out_string}!'
                                 for n, ran_out_string in result.items()))



# Setup Utility Cog as an extension
def setup(bot: discordutils.DBBot) -> None:
    bot.add_cog(UtilCog(bot))