from __future__ import annotations

import datetime

from utils import discordutils, dbbot


class UnnaturalSlotOpenDetectorCog(discordutils.LoopedCogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

        self.last_data: list[dict] | None = None
        self.last_time: datetime.datetime | None = None

    def compare(self, pre, nxt):
        return


def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(UnnaturalSlotOpenDetectorCog(bot))
