from __future__ import annotations

import aiohttp
import enum
from typing import Any, Optional, TYPE_CHECKING

from discord.ext import commands, tasks
import discord

import pnwutils
import discordutils
if TYPE_CHECKING:
    from ..main import DBBot



class WarType(enum.Enum):
    DEF = -1
    LOSE = 0
    ATT = 1


class WarCog(commands.Cog):
    def __init__(self, bot: DBBot):
        self.bot = bot
        self.prepped = False
        self.channels: dict[WarType, Optional[discord.TextChannel]] = {}
        self.check_losing: bool = True
        self.done_wars: list[str] = []
    

    async def prep(self):
        if not self.prepped:
            self.prepped = True
            self.check_losing = await self.bot.db_get('war', 'check_losing')
            for t in WarType:
                self.channels[t] = await self.bot.db_get('war', t.name)


    @staticmethod
    async def war_embed(data: dict[str, Any], kind: WarType) -> discord.Embed:
        if kind == WarType.ATT:
            title = 'New Offensive War'
        elif kind == WarType.DEF:
            title = 'New Defensive War'
        else:
            title = 'Losing War!'

        embeds = discord.Embed(title=title, description=f'[War Page]({pnwutils.Link.war(data["id"])})'), discord.Embed()
        for name, nation, prefix, n in (('Attacker', data['attacker'], 'att', 0), ('Defender', data['defender'], 'def', 1)):
            embeds[n].add_field(name=name, value=f'[{nation["nation_name"]}]({pnwutils.Link.nation(data[f"{prefix}id"])})',
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

        for war in data:
            if war['id'] in self.done_wars:
                continue
            
            kind, kind_str = (WarType.ATT, 'attacker') if war['att_alliance_id'] == pnwutils.Config.aa_id else (WarType.DEF, 'defender')
            if war[kind_str]['alliance_position'] == 'APPLICANT':
                self.done_wars.append(war['id'])
                continue
            if war['turnsleft'] == 60:
                # new war
                kind = WarType.ATT if war['att_alliance_id'] == pnwutils.Config.aa_id else WarType.DEF
                await self.channels[kind].send(embeds=await self.war_embed(war, kind))
                self.done_wars.append(war['id'])
                continue
            if self.check_losing and war[f'{kind_str[:3]}_resistance'] <= 50:
                await self.channels[WarType.LOSE].send(embeds=await self.war_embed(war, WarType.LOSE))
                self.done_wars.append(war['id'])


    @commands.guild_only()
    @commands.check(discordutils.gov_check)
    @commands.group(aliases=('detector',), invoke_without_command=True)
    async def war_detector(self, ctx: commands.Context) -> None:
        await ctx.send('Use `war_detector start` to start the detector and `war_detector stop` to stop it')

    @war_detector.command(aliases=('run',))
    async def running(self, ctx: commands.Context) -> None:
        await self.prep()
        if self.channels.keys() != set(WarType):
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

    @war_detector.command()
    async def losing(self, ctx: commands.Context) -> None:
        await ctx.send(f'Losing wars will now {"not " * self.check_losing}be checked!')
        self.check_losing = not self.check_losing
        await self.bot.db_set('war', 'check_losing', self.check_losing)

    @war_detector.group(aliases=('set',), invoke_without_command=True)
    async def set_channel(self, ctx: commands.Context) -> None:
        await ctx.send('Provide one of `att`, `def`, or `lose` to set the channel to!')


    @set_channel.command(aliases=('att',))
    async def a(self, ctx: commands.Context) -> None:
        self.channels[WarType.ATT] = ctx.channel
        await self.bot.db_set('war', WarType.ATT.name, ctx.channel.id)
        await ctx.send('Offensive wars channel set!')

    @set_channel.command(aliases=('def',))
    async def d(self, ctx: commands.Context) -> None:
        self.channels[WarType.DEF] = ctx.channel
        await self.bot.db_set('war', WarType.DEF.name, ctx.channel.id)
        await ctx.send('Defensive wars channel set!')

    @set_channel.command(aliases=('l',))
    async def lose(self, ctx: commands.Context) -> None:
        self.channels[WarType.LOSE] = ctx.channel
        await self.bot.db_set('war', WarType.LOSE.name, ctx.channel.id)
        await ctx.send('Losing wars channel set!')



# Setup War Cog as an extension
def setup(bot: DBBot) -> None:
    bot.add_cog(WarCog(bot))