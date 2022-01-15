from collections import defaultdict
import operator
import datetime

import discord
from discord.ext import commands

from utils import discordutils, pnwutils
import dbbot


class UtilCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.nations: discordutils.MappingProperty[int, str] = discordutils.MappingProperty[int, str](self, 'nations')

    @commands.command()
    async def set_nation(self, ctx: commands.Context, nation_id: str = ''):
        '''Use to manually add your nation to the database'''
        await self.nations.initialise()
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
        nation_id.removeprefix(nation_prefix)

        try:
            int(nation_id)
        except ValueError:
            await ctx.send("That isn't a number!")
            return

        nation_query_str = '''
        query nation_info($nation_id: [Int]) {
            nations(id: $nation_id, first: 1) {
                data {
                    alliance_id
                }
            }
        }
        '''
        data = await pnwutils.API.post_query(self.bot.session, nation_query_str,
                                             {'nation_id': nation_id},
                                             'nations')
        data = data['data']
        if not data:
            # nation does not exist, empty list returned
            await ctx.send('This nation does not exist!')
            return
        # nation exists, is in one elem list
        if data[0]['alliance_id'] not in (pnwutils.Config.aa_id, '9322'):
            await ctx.send(f'This nation is not in {pnwutils.Config.aa_name}!')
            return

        nation_confirm_choice = discordutils.Choices('Yes', 'No', user_id=ctx.author.id)
        await ctx.send(f'Is this your nation? ' + pnwutils.Link.nation(nation_id), view=nation_confirm_choice)
        if await nation_confirm_choice.result() == 'Yes':
            await self.nations[ctx.author.id].set(nation_id)
            await ctx.send('You have been registered to our database!')
        else:
            await ctx.send('Aborting!')

    @discordutils.gov_check
    @commands.command()
    async def list_registered(self, ctx: commands.Context):
        '''List all nations registered in our database. Be wary, this will fill the screen and more!'''
        nations = await self.nations.get()
        if nations:
            strings = (f'<@{disc_id}> - {pnwutils.Link.nation(nation_id)}'
                       for disc_id, nation_id in nations.items())
            for m in discordutils.split_blocks('\n', strings, 2000):
                await ctx.send(m, allowed_mentions=discord.AllowedMentions.none())
            return
        await ctx.send('There are no registrations!')

    @discordutils.gov_check
    @commands.command()
    async def check_ran_out(self, ctx: commands.Context):
        '''Use to list all nations thart have run out of food or uranium in the alliance.'''
        aa_query_str = '''
        query alliance_res($alliance_id: [Int], $page: Int){
          nations(alliance_id: $alliance_id, first: 500, page: $page){
            paginatorInfo {
              hasMorePages
            }
            data {
              alliance_position
              vmode
              id
              food
              uranium
              cities {
                nuclearpower
              }
            }
          }
        }
        '''
        data = (await pnwutils.API.post_query(self.bot.session, aa_query_str, {'alliance_id': pnwutils.Config.aa_id},
                                              'nations', True))['data']
        result = defaultdict(str)
        for nation in data:
            if nation['alliance_position'] == 'APPLICANT' or nation['vmode'] > 0:
                continue
            has_food = not nation['food']
            has_ura = not nation['uranium'] and any(map(operator.itemgetter('nuclearpower'), nation['cities']))

            if has_food:
                result[nation['id']] += 'food'
            if has_food and has_ura:
                result[nation['id']] += ' and '
            if has_ura:
                result[nation['id']] += 'uranium'

        out_discord = {}
        nations = await self.nations.get()
        for i, n in nations.items():
            if n in result.keys():
                out_discord[n] = i
        for m in discordutils.split_blocks('\n', (f'<@{d_id}> has ran out of {result[n]}!' for n, d_id in
                                                  out_discord.items()), 2000):
            await ctx.send(m)
        for m in discordutils.split_blocks('\n', (f'{pnwutils.Link.nation(n)} has ran out of {result[n]}!'
                                                  for n in (set(result.keys()) - out_discord.keys())), 2000):
            await ctx.send(m)

    @commands.check_any(commands.has_role(383815082473291778), discordutils.gov_check)
    @commands.command()
    async def activity_check(self, ctx: commands.Context):
        aa_query_str = '''
        query alliance_activity($alliance_id: [Int], $page: Int){
          nations(alliance_id: $alliance_id, first: 500, page: $page){
            paginatorInfo {
              hasMorePages
            }
            data {
              alliance_position
              vmode
              id
              last_active
            }
          }
        }
        '''
        data = (await pnwutils.API.post_query(self.bot.session, aa_query_str, {'alliance_id': pnwutils.Config.aa_id},
                                              'nations', True))['data']

        inactives = set()
        now = datetime.datetime.now()
        for nation in data:
            if nation['alliance_position'] == 'APPLICANT' or nation['vmode'] > 0:
                continue
            time_since_active = now - datetime.datetime.fromisoformat(nation['last_active'])
            if time_since_active >= datetime.timedelta(days=3):
                inactives.add(nation['id'])

        inactives_discord = {}
        nations = await self.nations.get()
        for i, n in nations.items():
            if n in inactives:
                inactives_discord[n] = i

        await ctx.send('Inactives:')
        for m in discordutils.split_blocks('\n', (f'<@{d_id}>' for d_id in inactives_discord.values()), 2000):
            await ctx.send(m)
        for m in discordutils.split_blocks('\n',
                                           (pnwutils.Link.nation(n) for n in inactives - inactives_discord.keys()),
                                           2000):
            await ctx.send(m)

    @discordutils.gov_check
    @commands.command()
    async def add_members(self, ctx: commands.Context):
        count = await self._add_members(ctx.guild.members)
        await ctx.send(f'{count} members have been added to the database.')

    async def _add_members(self, members):
        count = 0
        nations = await self.nations.get()
        for member in members:
            if str(member.id) not in nations.keys() and '/' in member.display_name:
                try:
                    int(nation_id := member.display_name.split('/')[1])
                except ValueError:
                    continue
                nations[str(member.id)] = nation_id
                count += 1

        await self.nations.set(nations)
        return count

    @commands.command()
    async def nation(self, ctx: commands.Context, member: discord.Member = None):
        if member is None:
            member = await discordutils.get_member_from_context(ctx)
        
        nation_id = await self.nations[member.id].get(None)
        if nation_id is None:
            await ctx.send('This user does not have their nation registered!')
            return
        await ctx.send(f"{member.mention}'s nation:",
                       view=discordutils.LinkView('Nation Link', pnwutils.Link.nation(nation_id)),
                       allowed_mentions=discord.AllowedMentions.none())

    @discordutils.gov_check
    @commands.command(aliases=('reload',))
    async def reload_ext(self, ctx: commands.Context, extension: str) -> None:
        try:
            self.bot.reload_extension(f'cogs.{extension}')
        except commands.ExtensionNotLoaded:
            await ctx.send(f'The extension {extension} was not previously loaded!')
            return
        await ctx.send(f'Extension {extension} reloaded!')


# Setup Utility Cog as an extension
def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(UtilCog(bot))
