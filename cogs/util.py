import collections
import datetime
import io
import itertools
import operator
import re

import matplotlib.pyplot as plt
import numpy as np
import discord
from discord import commands
from discord.ext import pages

from utils import discordutils, pnwutils, config, help_command, dbbot
from utils.queries import (nation_register_query, alliance_member_res_query,
                           alliance_activity_query, alliance_tiers_query, nation_info_query)


class UtilCog(discordutils.CogBase):
    nation_link_pattern = re.compile(rf'{pnwutils.constants.base_url}nation/id=(\d+)')

    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.users_table = self.bot.database.get_table('users')

    register = commands.SlashCommandGroup('register', 'Commands related to the user to nation registry the bot keeps!',
                                          guild_ids=config.guild_ids)

    @register.command(guild_ids=config.guild_ids)
    async def nation(self, ctx: discord.ApplicationContext,
                     nation_id: discord.Option(int, 'Your Nation ID', default=None),
                     nation_link: discord.Option(str, 'Your Nation ID', default=None)):
        """Use to manually add your nation to the database, with either an ID or a link"""
        if await self.users_table.exists(discord_id=ctx.author.id):
            await ctx.respond('You are already registered!', ephemeral=True)
            return

        if nation_id is None and nation_link is None:
            if '/' in ctx.author.display_name:
                try:
                    nation_id = int(ctx.author.display_name.split('/')[-1])
                except ValueError:
                    await ctx.respond('Please provide your nation id!')
                    return
                await self.users_table.insert(discord_id=ctx.author.id, nation_id=nation_id)
                await ctx.respond('You have been registered to our database!', ephemeral=True)
                return
            await ctx.respond('Please provide your nation id!', ephemeral=True)
            return
        elif nation_id is None:
            try:
                nation_id = int(nation_link.removeprefix(f'{pnwutils.constants.base_url}nation/id='))
            except ValueError:
                await ctx.respond("The given ID isn't a number!", ephemeral=True)
                return

        data = await nation_register_query.query(self.bot.session, nation_id=nation_id)
        data = data['data']
        if not data:
            # nation does not exist, empty list returned
            await ctx.respond('This nation does not exist!', ephemeral=True)
            return
        data = data[0]
        # nation exists, is in one elem list
        if data['alliance_id'] != config.alliance_id:
            off_id = await self.bot.get_offshore_id()
            if data['alliance_id'] != off_id:
                await ctx.respond(f'This nation is not in {config.alliance_name}!')
                return
        username = f'{ctx.author.name}#{ctx.author.discriminator}'
        if data['discord'] != username:
            await ctx.respond('Your Discord Username is not set! Please edit your nation and set your discord tag to '
                              f'{username}, then try this command again.', ephemeral=True)
            return
        await self.users_table.insert(discord_id=ctx.author.id, nation_id=nation_id)
        await ctx.respond('You have been registered to our database!', ephemeral=True)
        return

    @register.command(name='list', guild_ids=config.guild_ids)
    async def register_list(self, ctx: discord.ApplicationContext):
        """List all nations registered in our database"""
        await ctx.defer()
        nation_pages = []
        async with self.bot.database.acquire() as conn:
            async with conn.transaction():
                nations_cursor = await self.users_table.select('discord_id', 'nation_id').cursor(conn)
                while chunk := await nations_cursor.fetch(25):
                    embed = discord.Embed()
                    for rec in chunk:
                        embed.add_field(name=pnwutils.link.nation(rec['nation_id']), value=f'<@{rec["discord_id"]}>')
                    nation_pages.append(embed)
        if nation_pages:
            await pages.Paginator(nation_pages, timeout=config.timeout).respond(ctx.interaction, ephemeral=True)
            return
        await ctx.respond('There are no registrations!', ephemeral=True)

    _register = commands.SlashCommandGroup('_register', 'Government Registry commands', guild_ids=config.guild_ids,
                                           default_member_permissions=discord.Permissions())

    @_register.command(name='update', guild_ids=config.guild_ids, default_permission=False)
    @commands.default_permissions()
    async def register_update(self, ctx: discord.ApplicationContext):
        """Update registry using the / separated nation ids in nicknames"""
        count = 0
        await ctx.defer()
        async with self.bot.database.acquire() as conn:
            async with conn.transaction():
                nation_ids = [rec['nation_id'] async for rec in self.users_table.select('nation_id').cursor(conn)]
                for member in ctx.guild.members:
                    if '/' in member.display_name:
                        try:
                            nation_id = int(member.display_name.split('/')[-1])
                        except ValueError:
                            continue
                        if nation_id not in nation_ids:
                            count += 1
                            await self.users_table.insert(discord_id=member.id, nation_id=nation_id)
        # there are no await statements between get and set, so this is fine
        await ctx.respond(f'{count} members have been added to the database.')

    @_register.command(name='other', guild_ids=config.guild_ids, default_permission=False)
    @commands.default_permissions()
    async def register_other(self, ctx: discord.ApplicationContext, member: discord.Member, nation_id: int):
        """Update someone else's nation in the registry for them"""
        if await self.users_table.exists_or(discord_id=member.id, nation_id=nation_id):
            await ctx.respond('A user with this discord ID or nation ID has already been registered!')
            return

        data = await nation_register_query.query(self.bot.session, nation_id=nation_id)
        data = data['data']
        if not data:
            # nation does not exist, empty list returned
            await ctx.respond('This nation does not exist!', ephemeral=True)
            return
        data = data[0]
        # nation exists, is in one elem list
        if data['alliance_id'] != config.alliance_id:
            off_id = await self.bot.get_offshore_id()
            if data['alliance_id'] != off_id:
                await ctx.respond(f'This nation is not in {config.alliance_name}!')
                return
        username = f'{member.name}#{member.discriminator}'
        if data['discord'] != username:
            await ctx.respond(
                "This nation's Discord Username is not set! "
                f'Please ask {member.mention} to edit their nation and set their discord tag to {username}, '
                'then try this command again.', ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            return
        await self.users_table.insert(discord_id=member.id, nation_id=nation_id)
        await ctx.respond(f'{member.mention} has been registered to our database!',
                          ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        return

    @_register.command(name='purge', guild_ids=config.guild_ids, default_permission=False)
    async def register_purge(self, ctx: discord.ApplicationContext):
        """Purge accounts that are not in the server from the database"""
        ids = ', '.join(str(member.id) for member in ctx.guild.members)
        _, n = (await self.bot.database.execute(f'DELETE FROM users WHERE discord_id NOT IN ({ids})')).split(' ')
        await ctx.respond(f'{n} accounts not in the server have been purged!')

    check = commands.SlashCommandGroup(
        'check', 'Various checks on members of the alliance', guild_ids=config.guild_ids,
        default_permission=False, default_member_permissions=discord.Permissions())

    @check.command(name='resources', guild_ids=config.guild_ids)
    async def check_resources(self, ctx: discord.ApplicationContext):
        """List all nations that have run out of food or uranium in the alliance."""
        data = await alliance_member_res_query.query(self.bot.session, alliance_id=config.alliance_id)
        data = data['data']
        result = {'Food': [], 'Food And Uranium': [], 'Uranium': []}
        ids = set()
        for nation in data:
            if nation['alliance_position'] == 'APPLICANT' or nation['vacation_mode_turns'] > 0:
                continue
            has_food = not nation['food']
            # check for nuclear power and uranium amounts
            has_ura = not nation['uranium'] and any(map(operator.itemgetter('nuclear_power'), nation['cities']))

            if has_food and has_ura:
                result['Food And Uranium'].append((nation['id'], nation['nation_name']))
            elif has_food:
                result['Food'].append((nation['id'], nation['nation_name']))
            elif has_ura:
                result['Uranium'].append((nation['id'], nation['nation_name']))
            ids.add(nation['id'])

        if ids:
            async with self.bot.database.acquire() as conn:
                async with conn.transaction():
                    map_discord = {rec['nation_id']: rec['discord_id'] async for rec in
                                   self.users_table.select('discord_id', 'nation_id').where(
                                       f'nation_id IN ({",".join(map(str, ids))})').cursor(conn)}

            embed = discord.Embed(title='Ran Out Of...')
            for k, ns in result.items():
                string = '\n'.join((f'<@{d_id}>' if (d_id := map_discord.get(na[0])) else
                                    f'[{na[1]}/{na[0]}]({pnwutils.link.nation(na[0])})') for na in ns)
                if string:
                    embed.add_field(name=k, value=string)
            await ctx.respond(embed=embed)
        else:
            await ctx.respond('No one has ran out of food or uranium!')

    @check.command(name='activity', guild_ids=config.guild_ids)
    async def check_activity(self, ctx: discord.ApplicationContext,
                             days: discord.Option(int, 'How many days inactive', default=3)):
        """Lists nations that have not been active in the last n days (defaults to 3 days)"""
        data = (await alliance_activity_query.query(self.bot.session, alliance_id=config.alliance_id))
        data = data['data']

        inactives = set()
        nation_names = {}
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        for nation in data:
            if nation['alliance_position'] == 'APPLICANT':
                continue
            time_since_active = now - datetime.datetime.fromisoformat(nation['last_active'])
            if time_since_active >= datetime.timedelta(days=days):
                inactives.add(nation['id'])
                nation_names[nation['id']] = nation['nation_name']

        async with self.bot.database.acquire() as conn:
            async with conn.transaction():
                map_discord = {rec['nation_id']: rec['discord_id'] async for rec in
                               self.users_table.select('discord_id', 'nation_id').where(
                                   f'nation_id IN ({",".join(map(str, inactives))})').cursor(conn)}

        for m in discordutils.split_blocks('\n', itertools.chain(
                ('Inactives:',), (f'<@{d_id}>' for d_id in map_discord.values()))):
            await ctx.respond(m)
        await ctx.respond(inactives)
        await ctx.respond(map_discord)
        for m in discordutils.split_blocks('\n', (f'[{nation_names[n]}/{n}](<{pnwutils.link.nation(n)}>)'
                                                  for n in (inactives - map_discord.keys()))):
            await ctx.respond(m)

    @check.command(name='military', guild_ids=config.guild_ids)
    async def check_military(self, ctx: discord.ApplicationContext):
        """Not implemented as of now. Check back soon!"""
        await ctx.respond('Not Implemented!')

    @commands.user_command(guild_ids=config.guild_ids)
    async def nation(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Get the nation of this member"""
        nation_id = await self.users_table.select_val('nation_id').where(discord_id=member.id)
        if nation_id is None:
            await ctx.respond('This user does not have their nation registered!')
            return
        data = await nation_info_query.query(self.bot.session, nation_id=nation_id)
        if not data['data']:
            await ctx.respond("This member's registered nation does not exist! Aborting...")
            return
        data = data['data'][0]
        embed = discord.Embed(title=data['nation_name'], description=f"{member.mention}'s Nation")
        embed.add_field(name='Score', value=data['score'])
        embed.add_field(name='Domestic Policy', value=data['domestic_policy'])
        embed.add_field(name='War Policy', value=data['war_policy'])
        wars = [w for w in data['wars'] if w['turns_left'] > 0]
        if wars:
            offensive = sum(w['att_id'] == nation_id for w in wars)
            block = any(w['naval_blockade'] not in (nation_id, 0) for w in wars)
            s = ''
            if offensive:
                s = f'{offensive} Offensive Wars\n'
            if defensive := len(wars) - offensive:
                s += f'{defensive} Defensive Wars\n'
            if block:
                s += 'Currently under a naval blockade!'
            embed.add_field(name='Current Wars', value=s)
        await ctx.respond(embed=embed, view=discordutils.LinkView('Nation Link', pnwutils.link.nation(nation_id)))

    @commands.message_command(guild_ids=config.guild_ids)
    async def discords(self, ctx: discord.ApplicationContext, message: discord.Message):
        """Look for the discord accounts of the nation links in the message!"""
        nation_ids = list(map(int, self.nation_link_pattern.findall(message.content)))
        if not nation_ids:
            await ctx.respond('No nation links found in this message!')
        found = await self.users_table.select('discord_id', 'nation_id').where(f'nation_id IN [{nation_ids}]')

        if found:
            await ctx.respond(embed=discord.Embed(
                title='Discord Accounts Found:',
                description='\n'.join(
                    f'{pnwutils.link.nation(rec["nation_id"])} - <@{rec["discord_id"]}>' for rec in found)))
        else:
            await ctx.respond('No discord accounts associated with those nations found in our registry!')

    plot = commands.SlashCommandGroup('plot', 'Plotting commands!', guild_ids=config.guild_ids)

    @plot.command()
    async def alliance_tiers(self, ctx: discord.ApplicationContext,
                             alliances: discord.Option(str, 'Comma separated string of alliance ids',
                                                       default=config.alliance_id)):
        try:
            alliance_ids = map(int, alliances.split(','))
        except ValueError:
            await ctx.respond('Improper input! Please provide a comma separated list of ids, e.g. `4221,1234`')
            return
        fig, ax = plt.subplots(figsize=(20, 12))
        data = await alliance_tiers_query.query(self.bot.session, alliance_ids=alliance_ids)
        max_i = 0
        for aa in data['data']:
            counter = collections.Counter(nation['num_cities'] for nation in aa['nations']
                                          if nation['alliance_position'] != 'APPLICANT')
            i = 1
            n = len(counter)
            values = []
            while n > 0:
                if counter[i]:
                    values.append(counter[i])
                    n -= 1
                else:
                    values.append(0)
                i += 1
            ax.bar(np.arange(1, i), values, width=1, edgecolor='white', alpha=0.7, label=aa['name'])
            max_i = max(i, max_i)
        ax.set(xlabel='City Count', ylabel='Nation Count', xlim=(1, max_i), xticks=np.arange(1, max_i))
        ax.legend()
        for item in (ax.title, ax.xaxis.label, ax.yaxis.label, *ax.get_xticklabels(), *ax.get_yticklabels(),
                     *ax.get_legend().get_texts()):
            item.set_fontsize(18)
        buf = io.BytesIO()
        fig.savefig(buf)
        buf.seek(0)
        await ctx.respond(file=discord.File(buf, 'tiers.png'))

    @commands.command(guild_ids=config.guild_ids)
    async def time_in(self, ctx: discord.ApplicationContext, turns: discord.Option(int, 'Time in how many turns')):
        """Express the time in n turns"""
        s = pnwutils.time_after_turns(turns)
        await ctx.respond(f'It would be {s} (`{s}`) in {turns} turns.')

    @commands.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.default_permissions(manage_guild=True)
    async def reload(self, ctx: discord.ApplicationContext, cog: str) -> None:
        """Reload the given cog"""
        try:
            self.bot.reload_extension(f'cogs.{cog}')
        except discord.ExtensionNotLoaded:
            await ctx.respond(f'The cog `{cog}` was not previously loaded!')
            return
        await ctx.respond(f'The cog `{cog}` has been reloaded!')


    # im not sure if I should impl this
    '''
    formulas = commands.SlashCommandGroup('formulas', 'List of formulas for reference!', guild_ids=config.guild_ids)

    war_formulas = formulas.create_subgroup('application', 'Options for the application system!')
    war_formulas.guild_ids = config.guild_ids

    @war_formulas.command()
    async def ground(self, ctx: discord.ApplicationContext):
        """Information on ground battles."""
        embed = discord.Embed(title='Ground Battle Formulas')
        embed.add_field(name='Army Strength',
                        value='Unarmed Soldiers - 1\nArmedSoldiers - 1.75\nTank - 40\n\n'
                              'A tank is worth approximately 23 armed soldiers.\n\n'
                              'Note: A defender has population / 400 added to their army strength, '
                              "representing a resisting population. Don't expect to win with 5 soldiers against none.")
        embed.add_field(name='Loot',
                        value='(1.1 * (Attacking Soldiers) + 25.15 * (Attacking Tanks)) * '
                              '(Victory Factor) * (War Type Factor) * (War Policy Factor) * (Random Factor)\n\n'
                              'Victory Factor - Battle Outcome. IT - 3, MS - 2, PV - 1, UF - 0\n'
                              'War Type Factor - 1 for Raid, 0.5 for Ordinary, 0.25 for Attrition\n'
                              'War Policy Factor - Default 1, +0.4 if attacker has Pirate war policy,'
                              ' -0.4 if defender has Moneybags policy\n'
                              'Random Factor - A random number ranging from 0.8 - 1.1\n\n'
                              "Note: You cannot steal more than 75% of the defender's cash, nor their last 1000000")
        embed.add_field(name='Infrastructure Damage',
                        value=)
        await ctx.respond(embed=embed)
    '''

    @commands.command(name='help', guild_ids=config.guild_ids)
    async def help_(self, ctx: discord.ApplicationContext,
                    command: discord.Option(str, 'Cog or Command name', required=False,
                                            autocomplete=help_command.autocomplete) = None):
        """Get help on DBBot's cogs and commands"""
        await help_command.help_command(self.bot, ctx, command)


# Setup Utility Cog as an extension
def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(UtilCog(bot))
