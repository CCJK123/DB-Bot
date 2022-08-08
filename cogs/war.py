import collections
import operator

from discord import commands
import discord

from cogs.util import UtilCog
from utils import discordutils, pnwutils, config, dbbot
from utils.queries import individual_war_query, nation_active_wars_query, find_slots_query, nation_score_query, \
    spy_sat_query


class WarCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

    @commands.command(guild_ids=config.guild_ids)
    async def war(self, ctx: discord.ApplicationContext, war: discord.Option(str, 'War ID or link')):
        """Gives information on a war given an ID or link"""
        war = war.removeprefix(f'{pnwutils.constants.base_url}nation/war/timeline/war=')

        try:
            int(war)
        except ValueError:
            await ctx.respond("That isn't a number!")
            return

        data = await individual_war_query.query(self.bot.session, war_id=war)
        if data['data']:
            data = data['data'][0]  # type: ignore
            await ctx.respond(embed=discord.Embed(description=pnwutils.war_description(data)))
        else:
            await ctx.respond('No such war exists!')

    @commands.command(guild_ids=config.guild_ids)
    async def wars(self, ctx: discord.ApplicationContext,
                   member: discord.Option(discord.Member, 'Member to check the wars of', required=False, default=None),
                   nation_id: discord.Option(str, 'Nation ID of checked nation (overrides member)',
                                             required=False, default=None)):
        """Check the active wars of the given member/nation (default yourself)"""
        if member is None and nation_id is None:
            member = ctx.author
        if member is not None:
            nation_id = await self.bot.database.get_table('users').select_val('nation_id').where(discord_id=member.id)
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

    @commands.command(guild_ids=config.guild_ids)
    async def find_slots(self, ctx: discord.ApplicationContext,
                         ids: discord.Option(
                             str, 'Comma separated list of alliance IDs. Pass 0 (the default) for no alliance.',
                             default='0'),
                         turns: discord.Option(int, 'The maximum number of turns for the slot to open up.', default=0),
                         user: discord.Option(discord.Member, 'Run this command as if this user ran it.', default=None)
                         ):
        """Looks for nations in the given alliances that have empty defensive slots"""
        user = user if user else ctx.author
        nation_id = await self.bot.database.get_table('users').select_val('nation_id').where(discord_id=user.id)
        if nation_id is None:
            await ctx.respond('This user does not have a nation registered!')
            return
        score_data = await nation_score_query.query(self.bot.session, nation_id=nation_id)
        mi, ma = pnwutils.formulas.war_range(score_data['data'][0]['score'])
        try:
            data = await find_slots_query.query(self.bot.session, alliance_id=ids.split(','),
                                                min_score=mi, max_score=ma)
            # data = await find_slots_query.query(self.bot.session, alliance_id=ids.split(','))
        except ValueError:
            # error in converting to int list
            await ctx.respond('Incorrect format for ids! Please provide a comma separated ID list, like `4221,1224`')
            return

        found = collections.defaultdict(set)
        for n in data['data']:
            if n['vacation_mode_turns'] > turns or n['alliance_position'] == 'APPLICANT' or n['beige_turns'] > turns:
                continue
            def_war_turns = [w['turns_left'] for w in n['wars'] if w['def_id'] == n['id'] and w['turns_left'] > 0]
            if len(def_war_turns) <= 2:
                found[max(n['beige_turns'], n['vacation_mode_turns'])].add(n['id'])
                continue
            min_turns = min(def_war_turns)
            if min_turns <= turns:
                found[max(n['beige_turns'], n['vacation_mode_turns'], min_turns)].add(n['id'])

        if not found:
            await ctx.respond('No defensive slots were found!')
        elif turns:
            embed = discord.Embed(title='Nations with free slots in...')

            for t, nations in sorted(found.items(), key=operator.itemgetter(0)):
                embed.add_field(name=f'{t} turn{"s" if t - 1 else ""} ({pnwutils.time_after_turns(t)})',
                                value='\n'.join(map(pnwutils.link.nation, nations)))
            await ctx.respond(embed=embed)
        else:
            await ctx.respond(embed=discord.Embed(title='Nations with free slots',
                                                  description='\n'.join(map(pnwutils.link.nation, found[0]))))

    @commands.command(guild_ids=config.guild_ids)
    async def find_spy_sat(self, ctx: discord.ApplicationContext, target_score: int):
        """Looks for nations in the alliance with Spy Satellite who can spy on targets with the given score"""
        mi, ma = pnwutils.formulas.inverse_spy_range(target_score)
        data = await spy_sat_query.query(self.bot.session, alliance_id=config.alliance_id,
                                         min_score=mi, max_score=ma)
        ids = []
        for n in data['data']:
            if n['spy_satellite']:
                ids.append(n['id'])
        await ctx.respond(embed=discord.Embed(title='Nations with spy satellite who can attack:',
                                              description='\n'.join(map(pnwutils.link.nation, ids))))


def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(WarCog(bot))
