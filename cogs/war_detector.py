import enum
from typing import Any

import discord
from discord import commands
from discord.ext import tasks

import dbbot
from utils import discordutils, pnwutils, config
from utils.queries import alliance_wars_query


class WarType(enum.Enum):
    def __init__(self, v):
        if v:
            self.string = 'attacker'
            self.string_short = 'att'
        else:
            self.string = 'defender'
            self.string_short = 'def'

    ATT = True
    DEF = False


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
    async def new_war_embed(data: dict[str, Any], kind: WarType) -> discord.Embed:
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
                            value=pnwutils.mil_text(nation, data[f'{t.string_short}points']))
        return embed

    @tasks.loop(minutes=2)
    async def detect_wars(self) -> None:
        data = await pnwutils.api.post_query(self.bot.session, alliance_wars_query, {'alliance_id': config.alliance_id})
        await self.monitor_att.initialise()
        await self.monitor_def.initialise()
        monitoring = []
        war: dict[str, Any]
        for war in data:
            if await self.monitor_att.contains(war['id']):
                kind = WarType.ATT
            elif await self.monitor_def.contains(war['id']):
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
        monitoring = tuple(filter(lambda t: t[0][f'{t[1].string_short}_resistance'] <= 50, monitoring))
        if not self.fuzzy_compare(monitoring, self.last_monitoring):
            self.last_monitoring = monitoring
            if monitoring:
                embed = discord.Embed(title=f'{config.alliance_name} Lowest Resistance Wars')
                for w, k in monitoring:
                    embed.add_field(name=f"{w[k.string]['nation_name']}'s War",
                                    value=self.war_description(w), inline=False)
                await self.updates_channel.send(embed=embed)

    @staticmethod
    def fuzzy_compare(a, b) -> bool:
        if a is None or b is None or len(a) != len(b):
            return False

        score = 0
        for e_0, e_1 in zip(a, b):
            for k in e_0:
                print(k)
                score += e_0[k] != e_1[k]
        return score <= 2

    @staticmethod
    def war_description(w) -> str:
        s = f'[War Page]({pnwutils.link.war(w["id"])})\n{w["war_type"].capitalize()} War\n\n'
        for k in WarType.ATT, WarType.DEF:
            n = w[k.string]
            aa_text = 'None' if n['alliance'] is None else \
                f'[{n["alliance"]["name"]}]({pnwutils.link.alliance(w[f"{k.string_short}_alliance_id"])})'
            resist = w[f"{k.string_short}_resistance"]
            bar = (resist // 10) * '🟩' + (10 - resist // 10) * '⬛'
            s += (f'{k.string.capitalize()}: [{n["nation_name"]}]'
                  f'({pnwutils.link.nation(w[f"{k.string_short}id"])})\n'
                  f'{aa_text}\n\n'
                  f'{bar} {resist} Resistance\n\n'
                  f'{pnwutils.mil_text(n, w[f"{k.string_short}points"])}\n\n')
        return s

    detector = commands.SlashCommandGroup('detector', "The bot's war detector!", guild_ids=config.guild_ids,
                                          default_permission=False, permissions=[config.gov_role_permission])

    @detector.command(guild_ids=config.guild_ids, default_permission=False)
    async def toggle(self, ctx: discord.ApplicationContext):
        """Toggles the war detector on and off"""
        for c in self.channels.values():
            if await c.get(None) is None:
                await ctx.respond('Not all of the defensive, offensive and updates wars channels have been set! '
                                  'Set them with the `options war_detector channel` command '
                                  'in the respective channels.')
                return

        running_state = await self.running.get()
        if self.detect_wars.is_running():
            self.detect_wars.stop()
            if running_state:
                await ctx.respond('War Detector stopping!')
                await self.running.set(False)
            else:
                await ctx.respond('War Detector is in the process of stopping!')
            return
        self.detect_wars.start()
        if running_state:
            # not sure if valueerror is appropriate here
            raise ValueError('state is running but detector is not running!')
        await self.running.set(True)
        await ctx.respond('War detector started!')

    @detector.command(guild_ids=config.guild_ids, default_permission=False)
    async def monitor_ongoing(self, ctx: discord.ApplicationContext):
        """Makes the detector check for ongoing wars that it missed while offline to monitor."""
        data = await pnwutils.api.post_query(self.bot.session, alliance_wars_query, {'alliance_id': config.alliance_id})
        c = 0
        for war in data:
            if await self.monitor_att.contains(war['id']) or await self.monitor_def.contains(war['id']):
                continue
            kind = WarType.ATT if war['att_alliance_id'] == config.alliance_id else WarType.DEF
            if war[kind.string]['alliance_position'] == 'APPLICANT':  # type: ignore
                continue
            if war['att_resistance'] and war['def_resistance'] and war['turnsleft'] > 0:
                if kind == WarType.ATT:
                    await self.monitor_att.add(war['id'])
                else:
                    await self.monitor_def.add(war['id'])
                c += 1

        await ctx.respond(f'Complete! {c} wars added.')


# Setup War Detector Cog as an extension
def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(WarDetectorCog(bot))
