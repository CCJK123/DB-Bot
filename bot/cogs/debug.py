import asyncio

import discord

from ..utils import discordutils
from .. import dbbot


class DebugCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

    @discord.app_commands.command()
    @discord.app_commands.default_permissions()
    async def a(self, interaction: discord.Interaction):
        raise ValueError

    @discord.app_commands.command()
    @discord.app_commands.default_permissions()
    async def b(self, interaction: discord.Interaction):
        await asyncio.sleep(4)
        await interaction.response.send_message('Interaction not found!')


async def setup(bot: dbbot.DBBot):
    await bot.add_cog(DebugCog(bot))
