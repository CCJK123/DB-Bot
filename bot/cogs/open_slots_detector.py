from __future__ import annotations

import asyncio
import datetime

import asyncpg
import discord
import pnwkit

from ..utils import discordutils
from .. import dbbot
from ..utils.queries import find_slots_query


class SlotOpenDetectorCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

        self.last_data: list[dict] | None = None
        self.last_time: datetime.datetime | None = None
        self.alliance_ids = []
        self.subscribed = False
        self.nation_subscription: pnwkit.Subscription | None = None
        self.info = None
        self.misc_table = bot.database.get_table('misc')

    async def cog_load(self) -> None:
        alliances = await self.bot.database.fetch_val(
            'SELECT alliances FROM misc INNER JOIN coalitions ON misc.open_slot_coalition = coalitions.name')
        # if misc.open_slot_coalition == NULL then no rows returned, we get None
        if alliances is not None and not self.subscribed:
            asyncio.create_task(self.subscribe(alliances))

    async def subscribe(self, coalition: tuple[int]):
        await self.bot.wait_until_ready()
        self.subscribed = True
        self.nation_subscription = await pnwkit.Subscription.subscribe(
            self.bot.kit,
            'nation', 'update',
            {'alliance_id': coalition},
            self.on_nation_update
        )
        channel = self.bot.get_channel(await self.bot.database.get_kv('channel_ids').get('slot_open_channel'))

        # initial populate
        # find_slots query with unbounded score works
        self.info = await find_slots_query.query(self.bot.session, alliance_ids=coalition,
                                                 min_score=None, max_score=None)
        await channel.send(f'subscribed!')

    async def unsubscribe(self):
        await self.nation_subscription.unsubscribe()

    async def cog_unload(self) -> None:
        if self.subscribed:
            await self.unsubscribe()

    async def on_nation_update(self, nation: pnwkit.Nation):
        channel = self.bot.get_channel(await self.bot.database.get_kv('channel_ids').get('slot_open_channel'))
        print(nation.to_dict())

    slot_open_detector = discord.app_commands.Group(name='_slot_open_detector',
                                                    description='Open Slot Detector Commands')

    @slot_open_detector.command()
    async def start(self, interaction: discord.Interaction, coalition: str):
        """Start the detector on a provided coalition"""
        try:
            updated = await self.bot.database.fetch_val(
                'UPDATE misc SET open_slot_coalition = COALESCE(open_slot_coalition, $1) '
                'RETURNING open_slot_coalition = $1'
            )
        except asyncpg.ForeignKeyViolationError:
            await interaction.response.send_message('That is not a valid coalition name!')
            return
        if updated:
            # was not running before
            # this call should be successful, if no coalition with name there would be foreign key violation up top
            await self.subscribe(await self.bot.database.get_table('coalitions').select_val(
                'alliances').where(name=coalition))
            await interaction.response.send_message('Slot Open Detector starting!')
            return
        await interaction.response.send_message('Slot Open Detector already running!')

    @slot_open_detector.command()
    async def stop(self, interaction: discord.Interaction):
        """Stop the detector"""
        if self.subscribed:
            await asyncio.gather(
                self.unsubscribe(),
                self.misc_table.update('open_slot_coalition = NULL')
            )
            await interaction.response.send_message('The open slot detector has been stopped!')


async def setup(bot: dbbot.DBBot) -> None:
    await bot.add_cog(SlotOpenDetectorCog(bot))
