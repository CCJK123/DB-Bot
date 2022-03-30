import collections
import datetime
import io
import itertools
import operator

import discord
from discord import commands
from discord.ext import pages

import numpy as np
import matplotlib.pyplot as plt

from cogs.bank import BankCog
from utils import discordutils, pnwutils, config, help_command, dbbot
from utils.queries import (nation_register_query, alliance_member_res_query,
                           alliance_activity_query, individual_war_query, alliance_tiers_query,
                           nation_active_wars_query)


class UtilCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.nations: discordutils.MappingProperty[int, int] = discordutils.MappingProperty[int, int](self, 'nations')
        # discord id : nation id

    register = commands.SlashCommandGroup('register', 'Commands related to the user to nation registry the bot keeps!',
                                          guild_ids=config.guild_ids)

    @register.command(guild_ids=config.guild_ids)
    async def nation(self, ctx: discord.ApplicationContext,
                     nation_id: commands.Option(int, 'Your Nation ID', default=None),
                     nation_link: commands.Option(str, 'Your Nation ID', default=None)):
        """Use to manually add your nation to the database, with either an ID or a link"""
        await self.nations.initialise()
        if await self.nations.contains_key(ctx.author.id):
            await ctx.respond('You are already registered!', ephemeral=True)
            return

        if nation_id is None and nation_link is None:
            if '/' in ctx.author.display_name:
                try:
                    int(nation_id := ctx.author.display_name.split('/')[-1])
                except ValueError:
                    await ctx.respond('Please provide your nation id!')
                    return
                await self.nations[ctx.author.id].set(nation_id)
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

        if await self.nations.contains_value(nation_id):
            await ctx.respond('This nation has been registered before! Aborting...', ephemeral=True)
            return

        data = await nation_register_query.query(self.bot.session, nation_id=nation_id)
        data = data['data']
        if not data:
            # nation does not exist, empty list returned
            await ctx.respond('This nation does not exist!', ephemeral=True)
            return
        # nation exists, is in one elem list
        bank_cog = self.bot.get_cog('BankCog')
        assert isinstance(bank_cog, BankCog)
        off_id = await bank_cog.offshore_id.get(None)
        if data[0]['alliance_id'] not in (config.alliance_id, off_id):
            await ctx.respond(f'This nation is not in {config.alliance_name}!')
            return
        username = f'{ctx.author.name}#{ctx.author.discriminator}'
        if data['discord'] != username:
            await ctx.respond('Your Discord Username is not set! Please edit your nation and set your discord tag to '
                              f'{username}, then try this command again.', ephemeral=True)
        await self.nations[ctx.author.id].set(nation_id)
        await ctx.respond('You have been registered to our database!', ephemeral=True)
        return

    @register.command(name='list', guild_ids=config.guild_ids)
    async def register_list(self, ctx: discord.ApplicationContext):
        """List all nations registered in our database."""
        nations = await self.nations.get()
        if nations:
            nation_pages = []
            for n in discord.utils.as_chunks(nations.items(), 25):
                embed = discord.Embed()
                for disc_id, nation_id in n:
                    embed.add_field(name=pnwutils.link.nation(nation_id), value=f'<@{disc_id}>')
                nation_pages.append(embed)
            await pages.Paginator(nation_pages, timeout=config.timeout).respond(ctx.interaction, ephemeral=True)
            return
        await ctx.respond('There are no registrations!', ephemeral=True)

    @commands.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_any_role(config.gov_role_id, config.staff_role_id, guild_id=config.guild_id)
    async def register_update(self, ctx: discord.ApplicationContext):
        """Update registry using the / separated nation ids in nicknames"""
        count = 0
        nations = await self.nations.get()
        for member in ctx.guild.members:
            if str(member.id) not in nations.keys() and '/' in member.display_name:
                try:
                    int(nation_id := member.display_name.split('/')[-1])
                except ValueError:
                    continue
                nations[str(member.id)] = nation_id
                count += 1
        await self.nations.set(nations)
        # there are no await statements between get and set, so this is fine
        await ctx.respond(f'{count} members have been added to the database.')

    check = commands.SlashCommandGroup(
        'check', 'Various checks on members of the alliance', guild_ids=config.guild_ids,
        default_permission=False, permissions=[
            config.gov_role_permission,
            commands.permissions.CommandPermission(config.staff_role_id, 2, permission=True)
        ])

    @check.command(name='ran_out', guild_ids=config.guild_ids)
    async def check_ran_out(self, ctx: discord.ApplicationContext):
        """List all nations that have run out of food or uranium in the alliance."""
        data = await alliance_member_res_query.query(self.bot.session, alliance_id=config.alliance_id)
        data = data['data']
        result = {'Food': [], 'Food And Uranium': [], 'Uranium': []}
        ids = set()
        for nation in data:
            if nation['alliance_position'] == 'APPLICANT':
                continue
            has_food = not nation['food']
            # check for nuclear power and uranium amounts
            has_ura = not nation['uranium'] and any(map(operator.itemgetter('nuclearpower'), nation['cities']))

            if has_food and has_ura:
                result['Food And Uranium'].append((nation['id'], nation['nation_name']))
            elif has_food:
                result['Food'].append((nation['id'], nation['nation_name']))
            elif has_ura:
                result['Uranium'].append((nation['id'], nation['nation_name']))
            ids.add(nation['id'])

        map_discord = {}
        nations = await self.nations.get()
        for i, n in nations.items():
            if n in ids:
                map_discord[n] = i

        embed = discord.Embed(title='Ran Out Of...')
        for k, ns in result.items():
            string = '\n'.join((f'<@{d_id}>' if (d_id := map_discord.get(na[0])) else
                                f'[{na[1]}]({pnwutils.link.nation(ns[0])})') for na in ns)
            if string:
                embed.add_field(name=k, value=string)
        if embed:
            await ctx.respond(embed=embed)
        else:
            await ctx.respond('No one has ran out of food or uranium!')

    @check.command(name='activity', guild_ids=config.guild_ids)
    async def check_activity(self, ctx: discord.ApplicationContext,
                             days: commands.Option(int, 'How many days inactive', default=3)):
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

        inactives_discord = {}
        nations = await self.nations.get()
        for i, n in nations.items():
            if n in inactives:
                inactives_discord[n] = i

        for m in discordutils.split_blocks('\n', itertools.chain(
                ('Inactives:',), (f'<@{d_id}>' for d_id in inactives_discord.values()))):
            await ctx.respond(m)
        for m in discordutils.split_blocks('\n', (f'[{nation_names[n]}]({pnwutils.link.nation(n)})'
                                                  for n in inactives - inactives_discord.keys())):
            await ctx.respond(m)

    @check.command(name='military', guild_ids=config.guild_ids)
    async def check_military(self, ctx: discord.ApplicationContext):
        """Not Implemented as of now. Check back soon!"""
        await ctx.respond('Not Implemented!')

    @commands.command(guild_ids=config.guild_ids)
    async def war(self, ctx: discord.ApplicationContext, war: commands.Option(str, 'War ID or link')):
        """Gives information on a war given an ID or link!"""
        war = war.removeprefix(f'{pnwutils.constants.base_url}nation/war/timeline/war=')

        try:
            int(war)
        except ValueError:
            await ctx.respond("That isn't a number!")
            return

        data = await individual_war_query.query(self.bot.session, war_id=war)
        if data['data']:
            data = data['data'].pop()  # type: ignore
            await ctx.respond(embed=discord.Embed(description=pnwutils.war_description(data)))
        else:
            await ctx.respond('No such war exists!')

    @commands.command(guild_ids=config.guild_ids)
    async def wars(self, ctx: discord.ApplicationContext,
                   member: discord.Option(discord.Member, 'Member to check the wars of', required=False, default=None),
                   nation_id: discord.Option(str, 'Nation ID of checked nation', required=False, default=None)):
        """Check the active wars of the given member/nation (default yourself)"""
        if member is None and nation_id is None:
            member = ctx.author
        if member is not None:
            nation_id = await self.nations[member.id].get(None)
            if nation_id is None:
                await ctx.respond(f'{member.mention} does not have a nation registered!',
                                  allowed_mentions=discord.AllowedMentions.none(), ephemeral=True)
                return

        data = await nation_active_wars_query.query(self.bot.session, nation_id=nation_id)
        nation_link = pnwutils.link.nation(nation_id)
        if data['data']:
            await ctx.respond(
                f"{nation_link if member is None else member.mention}'s Active Wars",
                embeds=[discord.Embed(description=pnwutils.war_description(war)) for war in data['data']],
                allowed_mentions=discord.AllowedMentions.none()
            )
        else:
            await ctx.respond(f'{nation_link if member is None else member.mention} does not have any active wars!',
                              allowed_mentions=discord.AllowedMentions.none())

    @commands.user_command(guild_ids=config.guild_ids)
    async def nation(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Get the nation of this member"""
        nation_id = await self.nations[member.id].get(None)
        if nation_id is None:
            await ctx.respond('This user does not have their nation registered!')
            return
        await ctx.respond(f"{member.mention}'s nation:",
                          view=discordutils.LinkView('Nation link', pnwutils.link.nation(nation_id)),
                          allowed_mentions=discord.AllowedMentions.none())

    plot = commands.SlashCommandGroup('plot', 'Plotting commands!', guild_ids=config.guild_ids)

    @plot.command()
    async def alliance_tiers(self, ctx: discord.ApplicationContext,
                             alliances: commands.Option(str, 'Comma separated string of alliance ids',
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

    @commands.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def reload(self, ctx: discord.ApplicationContext, extension: str) -> None:
        """Reload the given cog"""
        await ctx.respond('At the moment, pycord has a bug wherein trying to unload a cog raises an error. '
                          'As a result, this command currently does not work.')

        try:
            self.bot.reload_extension(f'cogs.{extension}')
        except discord.ExtensionNotLoaded:
            await ctx.respond(f'The extension {extension} was not previously loaded!')
            return
        await ctx.respond(f'Extension {extension} reloaded!')

    @commands.command(name='help', guild_ids=config.guild_ids)
    async def help_(self, ctx: discord.ApplicationContext,
                    command: commands.Option(str, 'Cog or Command name', required=False,
                                             autocomplete=help_command.autocomplete) = None):
        """Get help on DBBot's cogs and commands."""
        await help_command.help_command(self.bot, ctx, command)


# Setup Utility Cog as an extension
def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(UtilCog(bot))
