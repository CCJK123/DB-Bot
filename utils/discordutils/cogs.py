from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from .. import dbbot

__all__ = ('CogBase', 'LoopedCogBase')


class CogBase(commands.Cog):
    def __init__(self, bot: "dbbot.DBBot", prefix: str):
        self.bot = bot
        self.prefix = prefix
    
    async def on_ready(self):
        pass

    async def on_cleanup(self):
        pass


class LoopedCogBase(CogBase):
    def __init__(self, bot: "dbbot.DBBot", prefix: str):
        super().__init__(bot, prefix)
        self.task = None
        self.running = None

    async def on_ready(self):
        if await self.running.get(None) is None:
            await self.running.set(False)

        if await self.running.get() and not self.task.is_running():
            self.task.start()
