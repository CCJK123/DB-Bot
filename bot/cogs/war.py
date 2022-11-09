import collections
import operator

import discord

from ..utils import discordutils, pnwutils, config
from .. import dbbot
from ..utils.queries import (individual_war_query, nation_active_wars_query,
                             find_slots_query, nation_score_query, spy_sat_query)


class OddsInfoView(discord.ui.View):
    def __init__(self, orig: discord.Embed, data: dict):
        super().__init__(timeout=config.timeout)
        self.orig = orig
        self.data = data

    async def on_timeout(self) -> None:
        discordutils.disable_all(self)
        self.stop()

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
                await interaction.response.send_message(embed=embed, view=OddsInfoView(embed, war_data))
                return
            await interaction.response.send_message(embed=embed)
            return

        await interaction.response.send_message('No such war exists!')

    @war.command()
    @discord.app_commands.describe(
        member='Member to check the wars of',
        nation_id='Nation ID of checked nation (overrides member)'
    )
    async def member_info(
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

        data = await nation_active_wars_query.query(self.bot.session, nation_id=nation_id)
        nation_link = pnwutils.link.nation(nation_id)
        if data['data']:
            await interaction.response.send_message(
                f"{nation_link if member is None else member.mention}'s Active Wars",
                embeds=[discord.Embed(description=pnwutils.war_description(war)) for war in data['data']],
                allowed_mentions=discord.AllowedMentions.none()
            )
            return
        await interaction.response.send_message(
            f'{nation_link if member is None else member.mention} does not have any active wars!',)

    @discord.app_commands.command()
    @discord.app_commands.describe(
        ids='Comma separated list of alliance IDs. Pass 0 (the default) for no alliance.',
        turns='The maximum number of turns for the slot to open up.',
        user='Run this command as if this user ran it.'
    )
    async def find_slots(self, interaction: discord.Interaction,
                         ids: str = '0', turns: int = 0, user: discord.Member = None):
        """Looks for nations in the given alliances that have empty defensive slots"""
        user = user if user else interaction.user
        nation_id = await self.bot.database.get_table('users').select_val('nation_id').where(discord_id=user.id)
        if nation_id is None:
            await interaction.response.send_message('This user does not have a nation registered!')
            return
        score_data = await nation_score_query.query(self.bot.session, nation_id=nation_id)
        mi, ma = pnwutils.formulas.war_range(score_data['data'][0]['score'])
        try:
            data = await find_slots_query.query(self.bot.session, alliance_id=ids.split(','),
                                                min_score=mi, max_score=ma)
            # data = await find_slots_query.query(self.bot.session, alliance_id=ids.split(','))
        except ValueError:
            # error in converting to int list
            await interaction.response.send_message(
                'Incorrect format for ids! Please provide a comma separated ID list, like `4221,1224`')
            return

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
            await interaction.response.send_message('No defensive slots were found!')
        elif turns:
            embed = discord.Embed(title='Nations with free slots in...')

            for t, nations in sorted(found.items(), key=operator.itemgetter(0)):
                embed.add_field(name=f'{t} turn{"s" if t - 1 else ""} ({pnwutils.time_after_turns(t)})',
                                value='\n'.join(map(pnwutils.link.nation, nations)))
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message(embed=discord.Embed(title='Nations with free slots',
                                                                        description='\n'.join(
                                                                            map(pnwutils.link.nation, found[0]))))

    @discord.app_commands.command()
    async def find_spy_sat(self, interaction: discord.Interaction, target_score: int):
        """Looks for nations in the alliance with Spy Satellite who can spy on targets with the given score"""
        mi, ma = pnwutils.formulas.inverse_spy_range(target_score)
        data = await spy_sat_query.query(self.bot.session, alliance_id=config.alliance_id,
                                         min_score=mi, max_score=ma)
        ids = []
        for n in data['data']:
            if n['spy_satellite']:
                ids.append(n['id'])
        await interaction.response.send_message(embed=discord.Embed(
            title='Nations with spy satellite who can attack:',
            description='\n'.join(map(pnwutils.link.nation, ids))))


async def setup(bot: dbbot.DBBot) -> None:
    await bot.add_cog(WarCog(bot))
