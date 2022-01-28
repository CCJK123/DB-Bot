import aiohttp
import enum
from typing import Any

import discord
from discord import commands
from discord.ext import tasks

from utils import discordutils, pnwutils, config
from utils.queries import alliance_wars_query
import dbbot


class WarType(enum.Enum):
    DEF = -1
    LOSE = 0
    ATT = 1


class WarDetectorCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.running = discordutils.CogProperty[bool](self, 'running')
        self.check_losing = discordutils.CogProperty[bool](self, 'check_losing')
        self.att_channel = discordutils.ChannelProperty(self, 'att_channel')
        self.def_channel = discordutils.ChannelProperty(self, 'def_channel')
        self.lose_channel = discordutils.ChannelProperty(self, 'lose_channel')
        self.channels = {WarType.ATT: self.att_channel, WarType.DEF: self.def_channel, WarType.LOSE: self.lose_channel}
        self.done_wars: list[str] = []

    async def on_ready(self):
        if await self.running.get(None) is None:
            await self.running.request_options(False)

        if await self.running.get():
            self.detect_wars.start()

    @staticmethod
    async def war_embed(data: dict[str, Any], kind: WarType) -> tuple[discord.Embed, discord.Embed]:
        if kind == WarType.ATT:
            title = 'New Offensive War'
        elif kind == WarType.DEF:
            title = 'New Defensive War'
        else:
            title = 'Losing War!'

        embeds = discord.Embed(title=title, description=f'[War Page]({pnwutils.link.war(data["id"])})'), discord.Embed()
        for name, nation, prefix, n in ('Attacker', data['attacker'], 'att', 0), (
                'Defender', data['defender'], 'def', 1):
            embeds[n].add_field(name=name,
                                value=f'[{nation["nation_name"]}]({pnwutils.link.nation(data[f"{prefix}id"])})',
                                inline=False)
            aa_text = 'None' if nation['alliance'] is None else \
                f'[{nation["alliance"]["name"]}]({pnwutils.link.alliance(data[f"{prefix}_alliance_id"])})'
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
        async with aiohttp.ClientSession() as session:
            data = await pnwutils.api.post_query(session, alliance_wars_query, {'alliance_id': config.alliance_id})

        war: dict[str, Any]
        for war in data:
            if war['id'] in self.done_wars:
                continue

            kind, kind_str = (WarType.ATT, 'attacker') if war['att_alliance_id'] == config.alliance_id else (
                WarType.DEF, 'defender')
            if war[kind_str]['alliance_position'] == 'APPLICANT':
                self.done_wars.append(war['id'])
                continue
            if war['turnsleft'] == 60:
                # new war
                kind = WarType.ATT if war['att_alliance_id'] == config.alliance_id else WarType.DEF
                await (await self.channels[kind].get()).send(embeds=await self.war_embed(war, kind))
                self.done_wars.append(war['id'])
                continue
            if await self.check_losing.get() and war[f'{kind_str[:3]}_resistance'] <= 50:
                await (await self.channels[WarType.LOSE].get()).send(embeds=await self.war_embed(war, WarType.LOSE))
                self.done_wars.append(war['id'])

    war_detector = commands.SlashCommandGroup('war_detector', 'A module that keeps track of wars!',
                                              guild_ids=config.guild_ids)

    @war_detector.command(guild_id=config.guild_id, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def toggle(self, ctx: discord.ApplicationContext) -> None:
        """Toggles the war detector on and off"""
        if any(await c.get(None) is None for c in self.channels.values()):
            await ctx.respond('Not all of the defensive, offensive and losing wars channels have been set! '
                              'Set them with the `war_detector channel` command in the respective channels.')
            return

        if self.detect_wars.is_running():
            self.detect_wars.stop()
            await ctx.respond('War detector stopped!')
            return
        self.detect_wars.start()
        await ctx.respond('War detector started!')


# Setup War Detector Cog as an extension
def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(WarDetectorCog(bot))
