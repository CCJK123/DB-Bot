from __future__ import annotations

import datetime

from discord.ext import tasks

from utils import discordutils, dbbot
from utils.queries import find_slots_query


class UnnaturalSlotOpenDetectorCog(discordutils.LoopedCogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

        self.last_data: list[dict] | None = None
        self.last_time: datetime.datetime | None = None

    @tasks.loop(minutes=2)
    async def task(self):
        # TODO: figure out enemies
        data = await find_slots_query.query(self.bot.session, self.enemies)
        now = datetime.datetime.now()
        if self.last_data is not None:
            turn = now.replace(minute=0, second=0, microsecond=0) - datetime.timedelta(hours=now.hour % 2)
            offset = self.last_time < turn <= now

        self.last_data = data
        self.last_time = now

    def compare(self, pre, nxt):
        return


def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(UnnaturalSlotOpenDetectorCog(bot))
