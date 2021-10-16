# Import external python modules
import aiohttp
from collections import defaultdict
import operator

# Import discord.py and related modules
from discord.ext import commands

# Import own modules
import pnwutils



class UtilCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

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
def setup(bot: commands.Bot) -> None:
    bot.add_cog(UtilCog(bot))