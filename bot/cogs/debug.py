import asyncio

import discord

from ..utils import discordutils
from .. import dbbot


class DebugCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

    @discord.app_commands.command()
    @discord.app_commands.default_permissions()
    async def test(self, interaction: discord.Interaction):
        await interaction.response.send_message('Command /test, cheese /war, /bank')

    @discord.app_commands.command()
    @discord.app_commands.default_permissions()
    async def test_interaction_fail(self, interaction: discord.Interaction):
        await asyncio.sleep(4)
        await interaction.response.send_message('oh no!')


async def setup(bot: dbbot.DBBot):
    await bot.add_cog(DebugCog(bot))
