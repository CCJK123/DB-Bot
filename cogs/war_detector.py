import aiohttp
import enum
import operator
from typing import Any

import discord
from discord import commands
from discord.ext import tasks

from utils import discordutils, pnwutils, config
from utils.queries import alliance_wars_query
import dbbot


class WarType(enum.Enum):
    def __init__(self):
        self.string = ''
        self.string_short = ''

    DEF = -1
    LOSE = 0
    ATT = 1


WarType.LOSE.string = 'losing'
WarType.LOSE.string_short = 'lose'
WarType.ATT.string = 'attacker'
WarType.ATT.string_short = 'att'
WarType.DEF.string = 'defender'
WarType.DEF.string_short = 'def'


class WarDetectorCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.last_monitoring: list[tuple[dict[str, Any], WarType]] | None = None
        self.running = discordutils.CogProperty[bool](self, 'running')

        self.updates_channel = discordutils.ChannelProperty(self, 'update_channel')

        self.att_channel = discordutils.ChannelProperty(self, 'att_channel')
        self.def_channel = discordutils.ChannelProperty(self, 'def_channel')
        self.channels = {WarType.ATT: self.att_channel, WarType.DEF: self.def_channel}

        self.monitor_att = discordutils.SetProperty(self, 'monitor_att')
        self.monitor_def = discordutils.SetProperty(self, 'monitor_def')
        self.monitor = {WarType.ATT: self.monitor_att, WarType.DEF: self.monitor_def}

    async def on_ready(self):
        if await self.running.get(None) is None:
            await self.running.set(False)

        if await self.running.get():
            self.detect_wars.start()

    @staticmethod
    def mil_text(nation):
        return (f'{nation["soldiers"]} 🪖\n'
                f'{nation["tanks"]} :truck:\n'
                f'{nation["aircraft"]} ✈\n'
                f'{nation["ships"]} 🚢\n'
                f'{nation["missiles"]} 🚀\n'
                f'{nation["nukes"]} ☢️')

    async def new_war_embed(self, data: dict[str, Any], kind: WarType) -> discord.Embed:
        if kind == WarType.ATT:
            title = 'New Offensive War'
        elif kind == WarType.DEF:
            title = 'New Defensive War'
        else:
            title = 'Losing War!'

        embed = discord.Embed(title=title, description=f'[War Page]({pnwutils.link.war(data["id"])})')
        for t in WarType.ATT, WarType.DEF:
            nation = data[t.string]
            embed.add_field(name=t.string.capitalize(),
                            value=f'[{nation["nation_name"]}]({pnwutils.link.nation(data[f"{t.string_short}id"])})',
                            inline=False)
            aa_text = 'None' if nation['alliance'] is None else \
                f'[{nation["alliance"]["name"]}]({pnwutils.link.alliance(data[f"{t.string_short}_alliance_id"])})'
            embed.add_field(name='Alliance', value=aa_text, inline=False)
            embed.add_field(name='Score', value=nation['score'])
            r = pnwutils.war_range(nation['score'])
            embed.add_field(name='Range', value=f'{r[0]:.2f}-{r[1]:.2f}')
            embed.add_field(name='Cities', value=nation['num_cities'], inline=False)
            embed.add_field(name='War Policy', value=nation['warpolicy'], inline=False)
            embed.add_field(name='Military',
                            value=self.mil_text(nation))
        return embed

    @tasks.loop(minutes=2)
    async def detect_wars(self) -> None:
        async with aiohttp.ClientSession() as session:
            data = await pnwutils.api.post_query(session, alliance_wars_query, {'alliance_id': config.alliance_id})

        monitoring = []
        war: dict[str, Any]
        for war in data:
            if war['id'] in self.monitor_att:
                kind = WarType.ATT
            elif war['id'] in self.monitor_def:
                kind = WarType.DEF
            else:
                kind = WarType.ATT if war['att_alliance_id'] == config.alliance_id else WarType.DEF

                if war[kind.string]['alliance_position'] != 'APPLICANT' and war['turnsleft'] == 60:
                    # new war
                    await self.channels[kind].send(embed=await self.new_war_embed(war, kind))

                    await self.monitor[kind].add(war['id'])
                continue

            if war['att_resistance'] and war['def_resistance'] and war['turnsleft'] > 0:
                monitoring.append((war, kind))

        monitoring.sort(key=lambda t: t[0][f'{t[1].string_short}_resistance'])
        monitoring = monitoring[:min(5, len(monitoring))]
        if monitoring != self.last_monitoring:
            self.last_monitoring = monitoring
            embed = discord.Embed(title=f'{config.alliance_name} Active Wars')
            for w, k in monitoring:
                embed.add_field(name=f"{w[k.string]['nation_name']}'s War", value=self.war_description(w))
            await self.updates_channel.send(embed=embed)

    def war_description(self, w):
        s = ''
        for k in WarType.ATT, WarType.DEF:
            resist = w[f"{k.string_short}_resistance"]
            bar = (resist // 10) * '🟩' + (10 - resist // 10) * '⬛'
            s += (f'{k.string.capitalize()}: [{w[k.string]["nation_name"]}]'
                  f'({pnwutils.link.nation(w[f"{k.string_short}id"])})\n'
                  f'{w[k.string]["alliance"]["name"]}\n'
                  f'{bar} {resist} Resistance\n'
                  f'{self.mil_text(w[k.string])}\n\n')
        return s

    @commands.command(guild_id=config.guild_id, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def detector_toggle(self, ctx: discord.ApplicationContext) -> None:
        """Toggles the war detector on and off"""
        for c in self.channels.values():
            if await c.get(None) is None:
                await ctx.respond('Not all of the defensive, offensive and updates wars channels have been set! '
                                  'Set them with the `options war_detector channel` command '
                                  'in the respective channels.')
                return

        await self.monitor_att.initialise()
        await self.monitor_def.initialise()
        await self.running.transform(operator.not_)
        if self.detect_wars.is_running():
            self.detect_wars.stop()
            await ctx.respond('War detector stopped!')
            return
        self.detect_wars.start()
        await ctx.respond('War detector started!')


# Setup War Detector Cog as an extension
def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(WarDetectorCog(bot))
