from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from ... import dbbot

__all__ = ('CogBase',)


class CogBase(commands.Cog):
    def __init__(self, bot: "dbbot.DBBot", prefix: str):
        self.bot = bot
        self.prefix = prefix
