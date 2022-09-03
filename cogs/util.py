import collections
import datetime
import io
import itertools
import operator
import re

import discord
import matplotlib.pyplot as plt
import numpy as np
from discord.ext import commands

from utils import discordutils, pnwutils, config, dbbot
from utils.queries import (nation_register_query, alliance_member_res_query,
                           alliance_activity_query, alliance_tiers_query, nation_info_query)


class UtilCog(discordutils.CogBase):
    nation_link_pattern = re.compile(rf'{pnwutils.constants.base_url}nation/id=(\d+)')

    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.users_table = self.bot.database.get_table('users')
        self.bot.tree.add_command(discord.app_commands.ContextMenu(
            name='nation',
            callback=self.nation
        ))
        self.bot.tree.add_command(discord.app_commands.ContextMenu(
            name='discords',
            callback=self.discords
        ))

    register = discord.app_commands.Group(name='register',
                                          description='Commands related to the user to nation registry the bot keeps!')

    @register.command(name='nation')
    @discord.app_commands.describe(
        nation_id='Your Nation ID',
        nation_link='Your Nation Link'
    )
    async def register_nation(self, interaction: discord.Interaction,
                              nation_id: int = None,
                              nation_link: str = None):
        """Use to manually add your nation to the database, with either an ID or a link"""
        if await self.users_table.exists(discord_id=interaction.user.id):
            await interaction.response.send_message('You are already registered!', ephemeral=True)
            return

        if nation_id is None and nation_link is None:
            if '/' in interaction.user.display_name:
                try:
                    nation_id = int(interaction.user.display_name.split('/')[-1])
                except ValueError:
                    await interaction.response.send_message('Please provide your nation id!')
                    return
                await self.users_table.insert(discord_id=interaction.user.id, nation_id=nation_id)
                await interaction.response.send_message('You have been registered to our database!', ephemeral=True)
                return
            await interaction.response.send_message('Please provide your nation id!', ephemeral=True)
            return
        elif nation_id is None:
            try:
                nation_id = int(nation_link.removeprefix(f'{pnwutils.constants.base_url}nation/id='))
            except ValueError:
                await interaction.response.send_message("The given ID isn't a number!", ephemeral=True)
                return

        data = await nation_register_query.query(self.bot.session, nation_id=nation_id)
        data = data['data']
        if not data:
            # nation does not exist, empty list returned
            await interaction.response.send_message('This nation does not exist!', ephemeral=True)
            return
        data = data[0]
        # nation exists, is in one elem list
        if data['alliance_id'] != config.alliance_id:
            off_id = await self.bot.get_offshore_id()
            if data['alliance_id'] != off_id:
                await interaction.response.send_message(f'This nation is not in {config.alliance_name}!')
                return
        username = f'{interaction.user.name}#{interaction.user.discriminator}'
        if data['discord'] != username:
            await interaction.response.send_message(
                'Your Discord Username is not set! Please edit your nation and set your discord tag to '
                f'{username}, then try this command again.', ephemeral=True)
            return
        await self.users_table.insert(discord_id=interaction.user.id, nation_id=nation_id)
        await interaction.response.send_message('You have been registered to our database!', ephemeral=True)
        return

    @register.command(name='list')
    async def register_list(self, interaction: discord.Interaction):
        """List all nations registered in our database"""
        await interaction.response.defer()
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
            await discordutils.Pager(nation_pages).respond(interaction, ephemeral=True)
            return
        await interaction.followup.send('There are no registrations!', ephemeral=True)

    _register = discord.app_commands.Group(name='_register', description='Government Registry commands',
                                           default_permissions=None)

    @_register.command(name='update')
    async def register_update(self, interaction: discord.Interaction):
        """Update registry using the / separated nation ids in nicknames"""
        count = 0
        await interaction.response.defer()
        async with self.bot.database.acquire() as conn:
            async with conn.transaction():
                nation_ids = [rec['nation_id'] async for rec in self.users_table.select('nation_id').cursor(conn)]
                for member in interaction.guild.members:
                    if '/' in member.display_name:
                        try:
                            nation_id = int(member.display_name.split('/')[-1])
                        except ValueError:
                            continue
                        if nation_id not in nation_ids:
                            count += 1
                            await self.users_table.insert(discord_id=member.id, nation_id=nation_id)
        await interaction.followup.send(f'{count} members have been added to the database.')

    @_register.command(name='other')
    async def register_other(self, interaction: discord.Interaction, member: discord.Member, nation_id: int):
        """Update someone else's nation in the registry for them"""
        if await self.users_table.exists_or(discord_id=member.id, nation_id=nation_id):
            await interaction.response.send_message(
                'A user with this discord ID or nation ID has already been registered!')
            return

        data = await nation_register_query.query(self.bot.session, nation_id=nation_id)
        data = data['data']
        if not data:
            # nation does not exist, empty list returned
            await interaction.response.send_message('This nation does not exist!', ephemeral=True)
            return
        data = data[0]
        # nation exists, is in one elem list
        if data['alliance_id'] != config.alliance_id:
            off_id = await self.bot.get_offshore_id()
            if data['alliance_id'] != off_id:
                await interaction.response.send_message(f'This nation is not in {config.alliance_name}!')
                return
        username = f'{member.name}#{member.discriminator}'
        if data['discord'] != username:
            await interaction.response.send_message(
                "This nation's Discord Username is not set! "
                f'Please ask {member.mention} to edit their nation and set their discord tag to {username}, '
                'then try this command again.', ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
            return
        await self.users_table.insert(discord_id=member.id, nation_id=nation_id)
        await interaction.response.send_message(f'{member.mention} has been registered to our database!',
                                                ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
        return

    @_register.command(name='purge')
    async def register_purge(self, interaction: discord.Interaction):
        """Purge accounts that are not in the server from the database"""
        ids = ', '.join(str(member.id) for member in interaction.guild.members)
        _, n = (await self.bot.database.execute(f'DELETE FROM users WHERE discord_id NOT IN ({ids})')).split(' ')
        await interaction.response.send_message(f'{n} accounts not in the server have been purged!')

    _check = discord.app_commands.Group(name='_check', description='Various checks on members of the alliance',
                                        default_permissions=None)

    @_check.command(name='resources')
    async def check_resources(self, interaction: discord.Interaction):
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
            await interaction.response.send_message(embed=embed)
            return
        await interaction.response.send_message('No one has ran out of food or uranium!')

    @_check.command(name='activity')
    @discord.app_commands.describe(
        days='How many days inactive'
    )
    async def check_activity(self, interaction: discord.Interaction,
                             days: int = 3):
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
                nation_id = int(nation['id'])
                inactives.add(nation_id)
                nation_names[nation_id] = nation['nation_name']

        async with self.bot.database.acquire() as conn:
            async with conn.transaction():
                map_discord = {rec['nation_id']: rec['discord_id'] async for rec in
                               self.users_table.select('discord_id', 'nation_id').where(
                                   f'nation_id IN ({",".join(map(str, inactives))})').cursor(conn)}

        for m in discordutils.split_blocks('\n', itertools.chain(
                (f'Inactive for {days} day{"s" if days != 1 else ""}:',),
                (f'<@{d_id}>' for d_id in map_discord.values()))):
            await discordutils.interaction_send(interaction, m)
        for m in discordutils.split_blocks('\n', (f'[{nation_names[n]}/{n}](<{pnwutils.link.nation(n)}>)'
                                                  for n in (inactives - map_discord.keys()))):
            await discordutils.interaction_send(interaction, m)

    @_check.command(name='military')
    async def check_military(self, interaction: discord.Interaction):
        """Not implemented as of now. Check back soon!"""
        await interaction.response.send_message('Not Implemented!', ephemeral=True)

    async def nation_info_embed(self, nation_id: int,
                                member: 'discord.Member | None' = None) -> 'discord.Embed | None':
        data = await nation_info_query.query(self.bot.session, nation_id=nation_id)
        if not data['data']:
            return None
        data = data['data'][0]
        embed = discord.Embed(title=data['nation_name'],
                              description='' if member is None else f"{member.mention}'s Nation")
        embed.add_field(name='Score', value=data['score'])
        embed.add_field(name='Domestic Policy', value=data['domestic_policy'])
        embed.add_field(name='War Policy', value=data['war_policy'])
        wars = [w for w in data['wars'] if w['turns_left'] > 0]
        if wars:
            offensive = sum(int(w['att_id']) == nation_id for w in wars)
            block = any(int(w['naval_blockade']) not in (nation_id, 0) for w in wars)
            s = ''
            if offensive:
                s = f'{offensive} Offensive War{"s" if offensive != 1 else ""}\n'
            if defensive := len(wars) - offensive:
                s += f'{defensive} Defensive War{"s" if offensive != 1 else ""}\n'
            if block:
                s += 'Currently under a naval blockade!'
            embed.add_field(name='Current Wars', value=s)
        return embed

    async def nation(self, interaction: discord.Interaction, member: discord.Member):
        """Get the nation of this member"""
        nation_id = await self.users_table.select_val('nation_id').where(discord_id=member.id)
        if nation_id is None:
            await interaction.response.send_message('This user does not have their nation registered!')
            return

        embed = await self.nation_info_embed(nation_id, member)
        if embed is None:
            await interaction.response.send_message("This member's registered nation does not exist! Aborting...")
            return

        await interaction.response.send_message(
            embed=embed, view=discordutils.LinkView('Nation Link', pnwutils.link.nation(nation_id)))

    @discord.app_commands.command(name='nation_info')
    async def nation_info(self, interaction: discord.Interaction, nation_id: int):
        """Get some basic information about a nation. 'nation' command equivalent for nation IDs"""
        embed = await self.nation_info_embed(nation_id)
        if embed is None:
            await interaction.response.send_message("This member's registered nation does not exist! Aborting...")
            return

        await interaction.response.send_message(
            embed=embed, view=discordutils.LinkView('Nation Link', pnwutils.link.nation(nation_id)))

    @discord.app_commands.command(name='discord')
    @discord.app_commands.describe(nation_id='Nation ID of the user you are trying to find!')
    async def _discord(self, interaction: discord.Interaction,
                       nation_id: discord.app_commands.Range[int, 1, None]):
        """Find a user from their nation ID"""
        discord_id = await self.users_table.select_val('discord_id').where(nation_id=nation_id)
        if discord_id is None:
            await interaction.response.send_message('No user linked to that nation was found!')
            return
        await interaction.response.send_message(f'<@{discord_id}> has nation ID {nation_id}.',
                                                allowed_mentions=discord.AllowedMentions.none())

    async def discords(self, interaction: discord.Interaction, message: discord.Message):
        """Look for the discord accounts of the nation links in the message!"""
        nation_ids = ','.join(self.nation_link_pattern.findall(message.content))
        if not nation_ids:
            await interaction.response.send_message('No nation links found in this message!')
            return
        found = await self.users_table.select('discord_id', 'nation_id').where(f'nation_id IN ({nation_ids})')

        if found:
            await interaction.response.send_message(embed=discord.Embed(
                title='Discord Accounts Found',
                description='\n'.join(
                    f'{pnwutils.link.nation(rec["nation_id"])} - <@{rec["discord_id"]}>' for rec in found)))
            return

        await interaction.response.send_message(
            'No discord accounts associated with those nations found in our registry!')

    plot = discord.app_commands.Group(name='plot', description='Plotting commands!')

    @plot.command()
    @discord.app_commands.describe(
        alliances='Comma separated string of alliance ids'
    )
    async def alliance_tiers(self, interaction: discord.Interaction,
                             alliances: str = config.alliance_id):
        """Create a plot of the tiers of some alliances"""
        try:
            alliance_ids = map(int, alliances.split(','))
        except ValueError:
            await interaction.response.send_message(
                'Improper input! Please provide a comma separated list of ids, e.g. `4221,1234`')
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
        await interaction.response.send_message(file=discord.File(buf, 'tiers.png'))

    @discord.app_commands.command()
    @discord.app_commands.describe(
        turns='Time in how many turns'
    )
    async def time_in(self, interaction: discord.Interaction, turns: int):
        """Express the time in n turns"""
        s = pnwutils.time_after_turns(turns)
        await interaction.response.send_message(f'It would be {s} (`{s}`) in {turns} turns.')

    @discord.app_commands.command(name='_reload')
    @discord.app_commands.default_permissions(manage_guild=True)
    async def reload(self, interaction: discord.Interaction, cog: str) -> None:
        """Reload the given cog"""
        try:
            await self.bot.reload_extension(f'cogs.{cog}')
        except commands.ExtensionNotLoaded:
            await interaction.response.send_message(f'The cog `{cog}` was not previously loaded!')
            return
        await interaction.response.send_message(f'The cog `{cog}` has been reloaded!')

    @commands.command()
    @commands.has_guild_permissions(administrator=True)
    async def sync(self, ctx: commands.Context):
        await self.bot.tree.sync(guild=ctx.guild)
        await ctx.send('Synced!')

    # im not sure if I should impl this
    '''
    formulas = commands.SlashCommandGroup('formulas', 'List of formulas for reference!', guild_ids=config.guild_ids)

    war_formulas = formulas.create_subgroup('war', 'Formulas for war!')
    war_formulas.guild_ids = config.guild_ids

    @war_formulas.command()
    async def ground(self, interaction: discord.Interaction):
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
        await interaction.response.send_message(embed=embed)
    '''

    '''
    @commands.command(name='help', guild_ids=config.guild_ids)
    async def help_(self, interaction: discord.Interaction,
                    command: discord.Option(str, 'Cog or Command name', required=False,
                                            autocomplete=help_command.autocomplete) = None):
        """Get help on DBBot's cogs and commands"""
        await help_command.help_command(self.bot, ctx, command)
    '''


# Setup Utility Cog as an extension
async def setup(bot: dbbot.DBBot) -> None:
    await bot.add_cog(UtilCog(bot))
