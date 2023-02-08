import collections
import operator

import aiohttp
import discord

from ..utils import discordutils, pnwutils, config
from .. import dbbot
from ..utils.queries import (individual_war_query, nation_active_wars_query,
                             find_slots_query, nation_score_query, spy_sat_query, find_in_range_query)


class OddsInfoView(discordutils.TimeoutView):
    def __init__(self, orig: discord.Embed, data: dict, interaction: discord.Interaction):
        super().__init__()
        self.orig = orig
        self.data = data
        self.interaction = interaction

    @discord.ui.button(label='Battle Odds')
    async def odds(self, interaction: discord.Interaction, button: discord.ui.Button):
        button.style = discord.ButtonStyle.success
        button.disabled = True
        self.stop()
        self.orig.set_footer(text='Note: assumes all soldiers have munitions')
        a = self.data['attacker']
        d = self.data['defender']
        odds = [f'Utter Defeat: {t[0]:.2%}\nPyrrhic Victory: {t[1]:.2%}\n'
                f'Moderate Success: {t[2]:.2%}\nImmense Triumph {t[3]:.2%}'
                for t in pnwutils.formulas.odds(a, d)]
        a_link = f'[{a["nation_name"]}]({pnwutils.link.nation(a["id"])})'
        d_link = f'[{d["nation_name"]}]({pnwutils.link.nation(d["id"])})'
        self.orig.description += (
            '__**Battle Odds**__\n'
            f'{a_link} against {d_link}\n**Ground Battle**\n{odds[0]}\n'
            f'**Airstrike**\n{odds[1]}\n**Naval Battle**\n{odds[2]}\n\n'
            f'{d_link} against {a_link}\n**Ground Battle**\n{odds[3]}\n'
            f'**Airstrike**\n{odds[4]}\n**Naval Battle**\n{odds[5]}')

        await interaction.response.edit_message(view=self, embed=self.orig)


class WarCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

        self.coalitions_table = self.bot.database.get_table('coalitions')

    war = discord.app_commands.Group(name='war', description='War related commands!')

    @war.command()
    @discord.app_commands.describe(
        war='War ID or link'
    )
    async def info(self, interaction: discord.Interaction, war: str):
        """Gives information on a war given an ID or link"""
        war = war.removeprefix(f'{pnwutils.constants.base_url}nation/war/timeline/war=')

        try:
            war_id = int(war)
        except ValueError:
            await interaction.response.send_message("The ID given isn't a number!")
            return

        if data := (await individual_war_query.query(self.bot.session, war_id=war_id)).get('data'):
            war_data = data[0]
            end_attack = pnwutils.find_end_attack(war_data)
            embed = discord.Embed(description=pnwutils.war_description(war_data, end_attack))
            if end_attack is None and war_data['turns_left'] > 0:
                await interaction.response.send_message(embed=embed, view=OddsInfoView(embed, war_data, interaction))
                return
            await interaction.response.send_message(embed=embed)
            return

        await interaction.response.send_message('No such war exists!')

    @staticmethod
    async def nation_get_war_embeds(session: aiohttp.ClientSession, nation_id: int):
        data = (await nation_active_wars_query.query(session, nation_id=nation_id))['data']
        return [discord.Embed(description=pnwutils.war_description(war)) for war in data] if data else []

    @war.command()
    @discord.app_commands.describe(
        member='Member to check the wars of',
        nation_id='Nation ID of checked nation (overrides member)'
    )
    async def nation_info(
            self, interaction: discord.Interaction,
            member: discord.Member = None,
            nation_id: str = None):
        """Check the active wars of the given member/nation (default yourself)"""
        if member is None and nation_id is None:
            member = interaction.user
        if member is not None:
            nation_id = await self.bot.database.get_table('users').select_val('nation_id').where(discord_id=member.id)
            if nation_id is None:
                await interaction.response.send_message(f'{member.mention} does not have a nation registered!',
                                                        ephemeral=True)
                return

        embeds = await self.nation_get_war_embeds(self.bot.session, nation_id)
        nation_link = pnwutils.link.nation(nation_id)
        if embeds:
            await interaction.response.send_message(
                f"{nation_link if member is None else member.mention}'s Active Wars",
                embeds=embeds,
                allowed_mentions=discord.AllowedMentions.none()
            )
            return
        await interaction.response.send_message(
            f'{nation_link if member is None else member.mention} does not have any active wars!',)

    async def _find_slots(self, interaction: discord.Interaction, ids: str, turns: int, mi: float, ma: float):

        try:
            alliances = tuple(map(int, ids.split(',')))
        except ValueError:
            # error in converting to int list
            # search for coalition
            alliances = await self.coalitions_table.select_val('alliances').where(name=ids)
            if alliances is None:
                await interaction.followup.send(
                    'Incorrect format for ids! Please provide a comma separated ID list, like `4221,1224`')
                return

        data = await find_slots_query.query(
            self.bot.session, alliance_ids=alliances, min_score=mi, max_score=ma)

        found = collections.defaultdict(set)
        for n in data:
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
            await interaction.followup.send('No defensive slots were found!')
        elif turns:
            embed = discord.Embed(title='Nations with free slots in...')
            for t, nations in sorted(found.items(), key=operator.itemgetter(0)):
                blocks = tuple(discordutils.split_blocks(
                    '\n',
                    (f'[{nation_id}]({pnwutils.link.nation(nation_id)})' for nation_id in nations),
                    limit=1024))
                time = discord.utils.format_dt(pnwutils.time_after_turns(t))
                if len(blocks) == 1:
                    embed.add_field(
                        name=f'{t} turn{"s" * (t != 1)} ({time})',
                        value=blocks[0])
                else:
                    for i, block in enumerate(blocks, 1):
                        embed.add_field(
                            name=f'{t} turn{"s" * (t != 1)} ({time}) ({i})',
                            value=block)
            await interaction.followup.send(embed=embed)
        else:
            await interaction.followup.send(embed=discord.Embed(
                title='Nations with free slots',
                description='\n'.join(f'[{nation_id}]({pnwutils.link.nation(nation_id)})' for nation_id in found[0])))

    find = discord.app_commands.Group(name='find', description='Commands for finding certain nations!')

    @find.command()
    @discord.app_commands.describe(
        ids='Comma separated list of alliance IDs. Pass 0 (the default) for no alliance.',
        turns='The maximum number of turns for the slot to open up.',
        user='Run this command as if this user ran it.'
    )
    async def slots(self, interaction: discord.Interaction,
                         ids: str = '0', turns: int = 0, user: discord.Member = None):
        """Looks for nations in the given alliances that have empty defensive slots"""
        user = user if user else interaction.user
        if user == self.bot.user:
            mi, ma = 0, 100000
            await interaction.response.defer()
        else:
            nation_id = await self.bot.database.get_table('users').select_val('nation_id').where(discord_id=user.id)
            if nation_id is None:
                await interaction.response.send_message('This user does not have a nation registered!')
                return
            await interaction.response.defer()
            score_data = await nation_score_query.query(self.bot.session, nation_id=nation_id)
            mi, ma = pnwutils.formulas.war_range(score_data['data'][0]['score'])
        await self._find_slots(interaction, ids, turns, mi, ma)

    @find.command()
    @discord.app_commands.describe(
        ids='Comma separated list of alliance IDs. Pass 0 (the default) for no alliance.',
        turns='The maximum number of turns for the slot to open up.',
        minimum='Minimum score. If left empty, means unbounded.',
        maximum='Minimum score. If left empty, means unbounded.'
    )
    async def slots_range(self, interaction: discord.Interaction, ids: str = '0', turns: int = 0,
                               minimum: discord.app_commands.Range[float, 0, None] = None,
                               maximum: discord.app_commands.Range[float, 0, None] = None):
        """Like /find_slots, but with a score range"""
        await interaction.response.defer()
        await self._find_slots(interaction, ids, turns, minimum, maximum)

    @find.command()
    async def find_spy_sat(self, interaction: discord.Interaction, target_score: int = 0):
        """Looks for nations in the alliance with Spy Satellite who can spy on targets with the given score"""
        if target_score:
            mi, ma = pnwutils.formulas.inverse_spy_range(target_score)
            data = await spy_sat_query.query(self.bot.session, alliance_id=config.alliance_id,
                                             min_score=mi, max_score=ma)
            ids = []
            for n in data['data']:
                if n['spy_satellite']:
                    ids.append(n['id'])
            await interaction.response.send_message(embed=discord.Embed(
                title='Nations with spy satellite who can attack:',
                description='\n'.join(f'[{pnwutils.link.nation(n_id)}]({n_id})' for n_id in ids)))
        else:
            ids = []
            data = await spy_sat_query.query(self.bot.session, alliance_id=config.alliance_id)
            for n in data['data']:
                if n['spy_satellite']:
                    ids.append(n['id'])
            await interaction.response.send_message(embed=discord.Embed(
                title='Nations with spy satellite:',
                description='\n'.join(f'[{pnwutils.link.nation(n_id)}]({n_id})' for n_id in ids)))

    @find.command()
    async def in_war_range(
            self, interaction: discord.Interaction,
            score: discord.app_commands.Range[float, 0, None] = None,
            nation_id: discord.app_commands.Range[int, 1, None] = None,
            min_cities: discord.app_commands.Range[int, 0, None] = 0):
        """Find nations in the alliance who are in range of a nation. The score parameter overrides nation_id"""
        if score is None and nation_id is None:
            await interaction.response.send_message('At least one of score and nation_id must be provided!')
            return
        if score is None:
            score = (await nation_score_query.query(self.bot.session, nation_id=nation_id))['data'][0]['score']
        mi, ma = pnwutils.formulas.inverse_war_range(score)
        data = await find_in_range_query.query(self.bot.session, alliance_id=config.alliance_id,
                                               min_score=mi, max_score=ma)

        n_ids = ",".join(e['id'] for e in data['data'] if e['num_cities'] >= min_cities)
        if n_ids:
            found = await self.bot.database.get_table('users').select(
                'discord_id', 'nation_id').where(f'nation_id IN ({n_ids})')

            await interaction.response.send_message(embed=discord.Embed(
                title='Nations found in war range',
                description='\n'.join(
                    f'<@{rec["discord_id"]}> - [{rec["nation_id"]}]({pnwutils.link.nation(rec["nation_id"])})'
                    for rec in found)
            ))
            return
        await interaction.response.send_message('No nations in war range found!')

    coalition = discord.app_commands.Group(name='_coalition', description='Coalition Commands')

    @coalition.command()
    @discord.app_commands.describe(
        name='The name to give the coalition',
        alliance_ids='Comma separated list of alliance IDs. Pass 0 (the default) for no alliance.')
    async def create(self, interaction: discord.Interaction, name: str, alliance_ids: str):
        """Create a coalition. If already exists, overrides it"""
        alliances = tuple(map(int, alliance_ids.split(',')))
        await self.coalitions_table.insert(name=name, alliances=alliances).on_conflict(
            '(name)').action_update('alliances = EXCLUDED.alliances')
        await interaction.response.send_message(f'Coalition `{name}` has been created/updated!')

    @coalition.command()
    async def list(self, interaction: discord.Interaction):
        """List all saved coalitions"""
        coalition_pages = []
        async with self.bot.database.acquire() as conn:
            async with conn.transaction():
                coalitions_cursor = await self.coalitions_table.select('name', 'alliances').cursor(conn)
                while chunk := await coalitions_cursor.fetch(25):
                    embed = discord.Embed()
                    for rec in chunk:
                        embed.add_field(name=rec['name'], value=rec['alliances'])
                    coalition_pages.append(embed)
        if coalition_pages:
            await discordutils.Pager(coalition_pages).respond(interaction)
            return
        await interaction.followup.send('There are no coalitions!')

    @coalition.command()
    async def delete(self, interaction: discord.Interaction, name: str):
        """Delete a coalition. This is irreversible!"""
        await interaction.response.send_message(
            f'Coalition `{name}` successfully deleted!'
            if await self.coalitions_table.delete().where(name=name) == 'DELETE 1'
            else f'There is no coalition named `{name}`!'
        )


async def setup(bot: dbbot.DBBot) -> None:
    await bot.add_cog(WarCog(bot))
