from __future__ import annotations

import asyncio
import traceback
from typing import Any

import discord
import pnwkit

from utils import discordutils, pnwutils, config, dbbot
from utils.queries import new_war_query, update_war_query


class NewWarDetectorCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.last_monitoring: list[tuple[dict[str, Any], pnwutils.WarType]] | None = None
        self.channels = {pnwutils.WarType.ATT: 'offensive_channel', pnwutils.WarType.DEF: 'defensive_channel',
                         None: 'updates_channel'}

        self.new_war_subscription: pnwkit.Subscription | None = None
        self.update_war_subscription: pnwkit.Subscription | None = None
        self.subscribed = False
        self.breakpoints: dict[str, int] = {}

    async def cog_load(self) -> None:
        asyncio.create_task(self.subscribe())

    async def subscribe(self):
        await self.bot.wait_until_ready()
        if not self.subscribed:
            # note: filtering by alliance_id does not work
            # as filters only work on models which has them as one of the fields
            # wars do not define an alliance_id field, only att_alliance_id and def_alliance_id
            self.new_war_subscription = await pnwkit.Subscription.subscribe(
                self.bot.kit,
                'war', 'create',
                {},
                self.on_new_war
            )
            self.update_war_subscription = await pnwkit.Subscription.subscribe(
                self.bot.kit,
                'war', 'update',
                {},
                self.on_war_update
            )
            self.subscribed = True
            channel = self.bot.get_channel(await self.bot.database.get_kv('channel_ids').get(self.channels[None]))
            await channel.send(f'subscribed!')

    async def cog_unload(self) -> None:
        if self.subscribed:
            await asyncio.gather(
                self.new_war_subscription.unsubscribe(),
                self.update_war_subscription.unsubscribe()
            )

    async def on_new_war(self, war: pnwkit.War):
        if war.att_alliance_id == config.alliance_id:
            kind = pnwutils.WarType.ATT
        elif war.def_alliance_id == config.alliance_id:
            kind = pnwutils.WarType.DEF
        else:
            return

        channel = self.bot.get_channel(await self.bot.database.get_kv('channel_ids').get(self.channels[kind]))
        data = await new_war_query.query(self.bot.session, war_id=war.id)
        data = data['data'][0]

        await channel.send(embed=await self.new_war_embed(data, kind))

    @staticmethod
    async def new_war_embed(data: dict[str, Any], kind: pnwutils.WarType | None) -> discord.Embed:
        if kind == pnwutils.WarType.ATT:
            title = f'New Offensive {data["war_type"].title()} War'
        elif kind == pnwutils.WarType.DEF:
            title = f'New Defensive {data["war_type"].title()} War'
        else:
            title = f'New {data["war_type"].title()} War!'

        embed = discord.Embed(title=title, description=f'[War Page]({pnwutils.link.war(data["id"])})')
        for t in pnwutils.WarType.ATT, pnwutils.WarType.DEF:
            nation = data[t.string]
            embed.add_field(
                name=t.string.capitalize(),
                value=f'[{nation["nation_name"]}]({pnwutils.link.nation(data[f"{t.string_short}_id"])})',
                inline=False)
            a = nation['alliance']
            aa_text = 'None' if a is None else f'[{a["name"]}]({pnwutils.link.alliance(a["id"])})'
            if nation['alliance_position'] == 'APPLICANT':
                aa_text += ' (Applicant)'
            embed.add_field(name='Alliance', value=aa_text, inline=False)
            embed.add_field(name='Score', value=str(nation["score"]))
            r = pnwutils.formulas.war_range(nation["score"])
            embed.add_field(name='Range', value=f'{r[0]:.2f}-{r[1]:.2f}')
            embed.add_field(name='Cities', value=str(nation["num_cities"]), inline=False)
            embed.add_field(name='War Policy', value=nation["war_policy"], inline=False)
            embed.add_field(name='Military', value=pnwutils.mil_text(nation))
        return embed

    async def on_war_update(self, war: pnwkit.War):
        if war.att_alliance_id == config.alliance_id:
            kind = pnwutils.WarType.ATT
        elif war.def_alliance_id == config.alliance_id:
            kind = pnwutils.WarType.DEF
        else:
            return
        if (res := getattr(war, f'{kind.string_short}_resistance')) <= 60:
            if b := self.breakpoints.get(war.id):
                if res > b:
                    return
                self.breakpoints[war.id] = b - 20
            else:
                self.breakpoints[war.id] = 40

            channel = self.bot.get_channel(await self.bot.database.get_kv('channel_ids').get(self.channels[None]))
            try:
                data = await update_war_query.query(self.bot.session, war_id=war.id)
                data = data['data']
                if data and data[0][kind.string]['alliance_position'] != 'APPLICANT':
                    embed = discord.Embed(
                        title='Low Resistance War!',
                        description=pnwutils.war_description(data[0]))
                    await channel.send(embed=embed)
                else:
                    del self.breakpoints[war.id]
                # if data is empty war has already ended, because query does not have 'active: false'
                # otherwise low resistance is an applicant
            except BaseException as e:
                await self.on_error(e, channel)

    @staticmethod
    async def on_error(exception: BaseException, channel: discord.TextChannel):
        await channel.send(f'Sorry, an exception occurred in the new war detector.')

        s = ''
        for ex in traceback.format_exception(type(exception), exception, exception.__traceback__):
            if ex == '\nThe above exception was the direct cause of the following exception:\n\n':
                await channel.send(f'```{s}```')
                s = ex
            else:
                s += ex
        await channel.send(f'```{s}```')


'''
    async def task(self) -> None:
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

                if war[kind.string]['alliance_position'] != 'APPLICANT' and war['turns_left'] == 60:
                    # new war
                    await self.channels[kind].send(embed=await self.new_war_embed(war, kind))

                    await self.monitor[kind].add(war['id'])
                continue

            if war['att_resistance'] and war['def_resistance'] and war['turns_left'] > 0:
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
                                          default_permission=False)

    @detector.command(guild_ids=config.guild_ids, default_permission=False)
    async def toggle(self, interaction: discord.Interaction):
        """Toggles the war detector on and off"""
        channel_ids_table = self.bot.database.get_kv('channel_ids')
        if not await channel_ids_table.all_set(*self.channels.values()):
            await interaction.response.send_message(
                'Not all of the defensive, offensive and updates war channels have been set! '
                'Set them with the `options war_detector channel` command in the respective channels.')
            return

        if self.running.get():
            await asyncio.gather(self.monitor_subscription.unsubscribe(),
                                 interaction.response.send_message('War Detector Stopping!'))
            await asyncio.gather(self.running.set(False), interaction.response.send_message('War Detector Stopped!'))
            return
        await asyncio.gather(self.subscribe(), interaction.response.send_message('War Detector Starting!'))
        await asyncio.gather(self.running.set(True), interaction.response.send_message('War Detector Started!'))

    @detector.command(guild_ids=config.guild_ids, default_permission=False)
    async def monitor_ongoing(self, interaction: discord.Interaction):
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
            if war['att_resistance'] and war['def_resistance'] and war['turns_left'] > 0:
                if kind == pnwutils.WarType.ATT:
                    await self.monitor_att.add(war['id'])
                else:
                    await self.monitor_def.add(war['id'])
                c += 1

        await interaction.response.send_message(f'Complete! {c} wars added.')
    '''


# Setup War Detector Cog as an extension
async def setup(bot: dbbot.DBBot) -> None:
    await bot.add_cog(NewWarDetectorCog(bot))
