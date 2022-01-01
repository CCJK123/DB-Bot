import aiohttp
import enum
import operator
from typing import Any

from discord.ext import commands, tasks
import discord

import pnwutils
import discordutils


class WarType(enum.Enum):
    DEF = -1
    LOSE = 0
    ATT = 1


class WarDetectorCog(discordutils.CogBase):
    def __init__(self, bot: discordutils.DBBot):
        super().__init__(bot, __name__)
        self.check_losing = discordutils.SavedProperty[bool](self, 'check_losing')
        self.att_channel = discordutils.ChannelProperty(self, 'att_channel')
        self.def_channel = discordutils.ChannelProperty(self, 'def_channel')
        self.lose_channel = discordutils.ChannelProperty(self, 'lose_channel')
        self.channels = {WarType.ATT: self.att_channel, WarType.DEF: self.def_channel, WarType.LOSE: self.lose_channel}
        self.done_wars: list[str] = []

    @staticmethod
    async def war_embed(data: dict[str, Any], kind: WarType) -> tuple[discord.Embed, discord.Embed]:
        if kind == WarType.ATT:
            title = 'New Offensive War'
        elif kind == WarType.DEF:
            title = 'New Defensive War'
        else:
            title = 'Losing War!'

        embeds = discord.Embed(title=title, description=f'[War Page]({pnwutils.Link.war(data["id"])})'), discord.Embed()
        for name, nation, prefix, n in ('Attacker', data['attacker'], 'att', 0), (
                'Defender', data['defender'], 'def', 1):
            embeds[n].add_field(name=name,
                                value=f'[{nation["nation_name"]}]({pnwutils.Link.nation(data[f"{prefix}id"])})',
                                inline=False)
            aa_text = 'None' if nation['alliance'] is None else \
                f'[{nation["alliance"]["name"]}]({pnwutils.Link.alliance(data[f"{prefix}_alliance_id"])})'
            embeds[n].add_field(name='Alliance', value=aa_text, inline=False)
            embeds[n].add_field(name='Score', value=nation['score'])
            r = pnwutils.war_range(nation['score'])
            embeds[n].add_field(name='Range', value=f'{r[0]:.2f}-{r[1]:.2f}')
            embeds[n].add_field(name='Cities', value=nation['num_cities'], inline=False)
            embeds[n].add_field(name='War Policy', value=nation['warpolicy'], inline=False)
            embeds[n].add_field(name='Soldiers', value=nation['soldiers'])
            embeds[n].add_field(name='Tanks', value=nation['tanks'])
            embeds[n].add_field(name='Aircraft', value=nation['aircraft'])
            embeds[n].add_field(name='Ships', value=nation['ships'])
            embeds[n].add_field(name='Missiles', value=nation['missiles'])
            embeds[n].add_field(name='Nukes', value=nation['nukes'])
            if kind == WarType.LOSE:
                embeds[n].add_field(name='Resistance', value=data[f'{prefix}_resistance'], inline=False)
                embeds[n].add_field(name='Action Points', value=data[f'{prefix}points'])

        return embeds

    @tasks.loop(minutes=2)
    async def detect_wars(self) -> None:
        new_wars_query_str = '''
        query alliance_wars($alliance_id: [ID]){
          wars(alliance_id: $alliance_id, days_ago: 6){
            id
            turnsleft
            attid
            defid
            att_alliance_id
            def_alliance_id
            att_resistance
            def_resistance
            attpoints
            defpoints
            attacker {
              nation_name
              score
              num_cities
              warpolicy
              soldiers
              tanks
              aircraft
              ships
              missiles
              nukes
              alliance_position
              alliance {
                name
              }
            }
            defender {
              nation_name
              score
              num_cities
              warpolicy
              soldiers
              tanks
              aircraft
              ships
              missiles
              nukes
              alliance_position
              alliance {
                name
              }
            }
          }
        }
        '''
        async with aiohttp.ClientSession() as session:
            data = await pnwutils.API.post_query(session, new_wars_query_str, {'alliance_id': pnwutils.Config.aa_id},
                                                 'wars')

        war: dict[str, Any]
        for war in data:
            if war['id'] in self.done_wars:
                continue
            
            kind, kind_str = (WarType.ATT, 'attacker') if war['att_alliance_id'] == pnwutils.Config.aa_id else (
                WarType.DEF, 'defender')
            if war[kind_str]['alliance_position'] == 'APPLICANT':
                self.done_wars.append(war['id'])
                continue
            if war['turnsleft'] == 60:
                # new war
                kind = WarType.ATT if war['att_alliance_id'] == pnwutils.Config.aa_id else WarType.DEF
                await (await self.channels[kind].get()).send(embeds=await self.war_embed(war, kind))
                self.done_wars.append(war['id'])
                continue
            if await self.check_losing.get() and war[f'{kind_str[:3]}_resistance'] <= 50:
                await (await self.channels[WarType.LOSE].get()).send(embeds=await self.war_embed(war, WarType.LOSE))
                self.done_wars.append(war['id'])

    @discordutils.gov_check
    @commands.group(aliases=('detector',), invoke_without_command=True)
    async def war_detector(self, ctx: commands.Context) -> None:
        await ctx.send('Use `war_detector start` to start the detector and `war_detector stop` to stop it')

    @war_detector.command(aliases=('run',))
    async def running(self, ctx: commands.Context) -> None:
        if any(c.get(None) is None for c in self.channels.values()):
            await ctx.send('Not all of the defensive, offensive and losing wars channels have been set! '
                           'Set them with `war_detector set att`, `war_detector set def`, and `war_detector set lose`'
                           'in the respective channels.')
            return None

        if self.detect_wars.is_running():
            self.detect_wars.stop()
            await ctx.send('War detector stopped!')
            return None
        self.detect_wars.start()
        await ctx.send('War detector is now running!')

    @discordutils.gov_check
    @war_detector.command()
    async def losing(self, ctx: commands.Context) -> None:
        await ctx.send(f'Losing wars will now {"not " * await self.check_losing.get()}be checked!')
        await self.check_losing.transform(operator.not_)

    @discordutils.gov_check
    @war_detector.group(aliases=('set',), invoke_without_command=True)
    async def set_channel(self, ctx: commands.Context) -> None:
        await ctx.send('Provide one of `att`, `def`, or `lose` to set the channel to!')

    @discordutils.gov_check
    @set_channel.command(aliases=('att',))
    async def a(self, ctx: commands.Context) -> None:
        await self.att_channel.set(ctx.channel)
        await ctx.send('Offensive wars channel set!')

    @discordutils.gov_check
    @set_channel.command(aliases=('def',))
    async def d(self, ctx: commands.Context) -> None:
        await self.def_channel.set(ctx.channel)
        await ctx.send('Defensive wars channel set!')

    @discordutils.gov_check
    @set_channel.command(aliases=('l',))
    async def lose(self, ctx: commands.Context) -> None:
        await self.lose_channel.set(ctx.channel)
        await ctx.send('Losing wars channel set!')


# Setup War Detector Cog as an extension
def setup(bot: discordutils.DBBot) -> None:
    bot.add_cog(WarDetectorCog(bot))
