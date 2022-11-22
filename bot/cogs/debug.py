import asyncio

import discord

from ..utils import discordutils
from .. import dbbot


class DebugCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

    @discord.app_commands.command()
    @discord.app_commands.default_permissions()
    async def _test(self, interaction: discord.Interaction):
        await interaction.response.send_message('Command /test, cheese /war, /bank')

    @discord.app_commands.command()
    @discord.app_commands.default_permissions()
    async def _test_interaction_fail(self, interaction: discord.Interaction):
        await asyncio.sleep(4)
        await interaction.response.send_message('oh no!')

    @discord.app_commands.command()
    @discord.app_commands.default_permissions()
    async def _error(self, interaction: discord.Interaction):
        raise ZeroDivisionError


async def setup(bot: dbbot.DBBot):
    await bot.add_cog(DebugCog(bot))
