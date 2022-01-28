import operator
import datetime

import discord
from discord import commands
from discord.ext import pages

from utils import discordutils, pnwutils, config
from utils.queries import nation_alliance_query, alliance_member_res_query, alliance_activity_query
import dbbot


class UtilCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.nations: discordutils.MappingProperty[int, str] = discordutils.MappingProperty[int, str](self, 'nations')

    register = commands.SlashCommandGroup('register', 'Commands related to the user to nation registry the bot keeps!',
                                          guild_ids=config.guild_ids, default_permission=False)

    @register.command(guild_ids=config.guild_ids)
    async def nation(self, ctx: discord.ApplicationContext,
                     nation_id: commands.Option(str, 'Your nation id or link', default='')):
        """Use to manually add your nation to the database"""
        await self.nations.initialise()
        if self.nations.contains_key(ctx.author.id):
            await ctx.respond('You are already registered!')
            return

        if not nation_id:
            if '/' in ctx.author.display_name:
                try:
                    int(nation_id := ctx.author.display_name.split('/')[1])
                except ValueError:
                    await ctx.respond('Please provide your nation id!')
                    return
                await self.nations[ctx.author.id].set(nation_id)
                await ctx.respond('You have been registered to our database!')
                return
            await ctx.respond('Please provide your nation id!')
            return

        nation_prefix = pnwutils.constants.base_url + 'nation/id='
        nation_id.removeprefix(nation_prefix)

        try:
            int(nation_id)
        except ValueError:
            await ctx.respond("That isn't a number!")
            return

        if self.nations.contains_value(nation_id):
            await ctx.respond('This nation has been registered before! Aborting...')
            return

        data = await pnwutils.api.post_query(self.bot.session, nation_alliance_query,
                                             {'nation_id': nation_id})
        data = data['data']
        if not data:
            # nation does not exist, empty list returned
            await ctx.respond('This nation does not exist!')
            return
        # nation exists, is in one elem list
        if data[0]['alliance_id'] not in (config.alliance_id, config.offshore_id):
            await ctx.respond(f'This nation is not in {config.alliance_name}!')
            return

        nation_confirm_choice = discordutils.Choices('Yes', 'No', user_id=ctx.author.id)
        await ctx.respond(f'Is this your nation? ' + pnwutils.link.nation(nation_id),
                          view=nation_confirm_choice, ephemeral=True)
        if await nation_confirm_choice.result() == 'Yes':
            await self.nations[ctx.author.id].set(nation_id)
            await ctx.respond('You have been registered to our database!')
        else:
            await ctx.respond('Aborting!')

    @register.command(name='list', guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
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
            await pages.Paginator(nation_pages, timeout=config.timeout).respond(ctx.interaction)
            return
        await ctx.respond('There are no registrations!')

    @register.command(name='update', guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_any_role(config.gov_role_id, config.staff_role_id, guild_id=config.guild_id)
    async def register_update(self, ctx: discord.ApplicationContext):
        """Update registry using the / separated nation ids in nicknames"""
        count = 0
        nations = await self.nations.get()
        for member in ctx.guild.members:
            if str(member.id) not in nations.keys() and '/' in member.display_name:
                try:
                    int(nation_id := member.display_name.split('/')[1])
                except ValueError:
                    continue
                nations[str(member.id)] = nation_id
                count += 1
        await self.nations.set(nations)
        # there are no await statements between get and set, so this is fine
        await ctx.respond(f'{count} members have been added to the database.')

    check = commands.SlashCommandGroup('check', 'Various checks on members of the alliance', guild_ids=config.guild_ids,
                                       default_permission=False, permissions=[config.gov_role_permission])

    @check.command(name='ran_out', guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_any_role(config.gov_role_id, config.staff_role_id, guild_id=config.guild_id)
    async def check_ran_out(self, ctx: discord.ApplicationContext):
        """List all nations that have run out of food or uranium in the alliance."""
        data = (await pnwutils.api.post_query(self.bot.session, alliance_member_res_query,
                                              {'alliance_id': config.alliance_id}, True))['data']
        result = {'Food': [], 'Food And Uranium': [], 'Uranium': []}
        ids = set()
        for nation in data:
            if nation['alliance_position'] == 'APPLICANT' or nation['vmode'] > 0:
                continue
            has_food = not nation['food']
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

    @check.command(name='activity', guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_any_role(config.gov_role_id, config.staff_role_id, guild_id=config.guild_id)
    async def activity_check(self, ctx: discord.ApplicationContext,
                             days: commands.Option(int, 'How many days inactive', default=3)):
        """Lists nations that have not been active in the last n days (defaults to 3 days)"""
        data = (await pnwutils.api.post_query(self.bot.session, alliance_activity_query,
                                              {'alliance_id': config.alliance_id}, True))['data']

        inactives = set()
        now = datetime.datetime.now()
        for nation in data:
            if nation['alliance_position'] == 'APPLICANT' or nation['vmode'] > 0:
                continue
            time_since_active = now - datetime.datetime.fromisoformat(nation['last_active'])
            if time_since_active >= datetime.timedelta(days=days):
                inactives.add(nation['id'])

        inactives_discord = {}
        nations = await self.nations.get()
        for i, n in nations.items():
            if n in inactives:
                inactives_discord[n] = i

        await ctx.respond('Inactives:')
        for m in discordutils.split_blocks('\n', (f'<@{d_id}>' for d_id in inactives_discord.values()), 2000):
            await ctx.respond(m)
        for m in discordutils.split_blocks('\n',
                                           (pnwutils.link.nation(n) for n in inactives - inactives_discord.keys()),
                                           2000):
            await ctx.respond(m)

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


# Setup Utility Cog as an extension
def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(UtilCog(bot))
