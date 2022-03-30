from typing import Any

import discord
from discord import commands
from discord.ext import tasks

from utils import discordutils, pnwutils, config, dbbot
from utils.queries import alliance_wars_query


class WarDetectorCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.last_monitoring: list[tuple[dict[str, Any], pnwutils.WarType]] | None = None
        self.running = discordutils.CogProperty[bool](self, 'running')

        self.updates_channel = discordutils.ChannelProperty(self, 'update_channel')

        self.att_channel = discordutils.ChannelProperty(self, 'att_channel')
        self.def_channel = discordutils.ChannelProperty(self, 'def_channel')
        self.channels = {pnwutils.WarType.ATT: self.att_channel, pnwutils.WarType.DEF: self.def_channel}

        self.monitor_att = discordutils.SetProperty(self, 'monitor_att')
        self.monitor_def = discordutils.SetProperty(self, 'monitor_def')
        self.monitor = {pnwutils.WarType.ATT: self.monitor_att, pnwutils.WarType.DEF: self.monitor_def}

    async def on_ready(self):
        if await self.running.get(None) is None:
            await self.running.set(False)

        if await self.running.get() and not self.detect_wars.is_running():
            self.detect_wars.start()

    @staticmethod
    async def new_war_embed(data: dict[str, Any], kind: pnwutils.WarType) -> discord.Embed:
        if kind == pnwutils.WarType.ATT:
            title = f'New Offensive {data["war_type"].title()} War'
        elif kind == pnwutils.WarType.DEF:
            title = f'New Defensive {data["war_type"].title()} War'
        else:
            title = f'Losing {data["war_type"].title()} War!'

        embed = discord.Embed(title=title, description=f'[War Page]({pnwutils.link.war(data["id"])})')
        for t in pnwutils.WarType.ATT, pnwutils.WarType.DEF:
            nation = data[t.string]
            embed.add_field(name=t.string.capitalize(),
                            value=f'[{nation["nation_name"]}]({pnwutils.link.nation(data[f"{t.string_short}id"])})',
                            inline=False)
            a = nation['alliance']
            aa_text = 'None' if a is None else f'[{a["name"]}]({pnwutils.link.alliance(a["id"])})'
            embed.add_field(name='Alliance', value=aa_text, inline=False)
            embed.add_field(name='Score', value=nation['score'])
            r = pnwutils.war_range(nation['score'])
            embed.add_field(name='Range', value=f'{r[0]:.2f}-{r[1]:.2f}')
            embed.add_field(name='Cities', value=nation['num_cities'], inline=False)
            embed.add_field(name='War Policy', value=nation['warpolicy'], inline=False)
            embed.add_field(name='Military', value=pnwutils.mil_text(nation))
        return embed

    @tasks.loop(minutes=2)
    async def detect_wars(self) -> None:
        data = await alliance_wars_query.query(self.bot.session, alliance_id=config.alliance_id)
        data = data['data']
        await self.monitor_att.initialise()
        await self.monitor_def.initialise()
        monitoring = []
        war: dict[str, Any]
        for war in data:
            if await self.monitor_att.contains(war['id']):
                kind = pnwutils.WarType.ATT
            elif await self.monitor_def.contains(war['id']):
                kind = pnwutils.WarType.DEF
            else:
                if war['attacker']['alliance'] and war['attacker']['alliance']['id'] == config.alliance_id:
                    kind = pnwutils.WarType.ATT
                else:
                    kind = pnwutils.WarType.DEF

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
                                    value=pnwutils.war_description(w), inline=False)
                await self.updates_channel.send(embed=embed)

    @classmethod
    def fuzzy_compare(cls, a, b) -> int:
        if a is None or b is None:
            return 0
        if isinstance(a, dict):
            score = 0
            for k in a:
                score += cls.fuzzy_compare(a[k], b[k])
            return score
        if isinstance(a, (list, tuple)):
            score = 0
            for e_a, e_b in zip(a, b):
                score += cls.fuzzy_compare(e_a, e_b)
            return score
        return a == b

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
        data = await alliance_wars_query.query(self.bot.session, alliance_id=config.alliance_id)
        data = data['data']
        c = 0
        for war in data:
            if await self.monitor_att.contains(war['id']) or await self.monitor_def.contains(war['id']):
                continue
            kind = pnwutils.WarType.ATT if war['att_alliance_id'] == config.alliance_id else pnwutils.WarType.DEF
            if war[kind.string]['alliance_position'] == 'APPLICANT':  # type: ignore
                continue
            if war['att_resistance'] and war['def_resistance'] and war['turnsleft'] > 0:
                if kind == pnwutils.WarType.ATT:
                    await self.monitor_att.add(war['id'])
                else:
                    await self.monitor_def.add(war['id'])
                c += 1

        await ctx.respond(f'Complete! {c} wars added.')


# Setup War Detector Cog as an extension
def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(WarDetectorCog(bot))
