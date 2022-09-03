import discord

from utils import discordutils, config, dbbot


class DebugCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

    @discord.app_commands.command()
    @discord.app_commands.default_permissions()
    async def a(self, interaction: discord.Interaction):
        raise ValueError


async def setup(bot: dbbot.DBBot):
    await bot.add_cog(DebugCog(bot))
