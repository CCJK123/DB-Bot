from utils import discordutils, dbbot


class LoggingCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

        self.logging_channel = discordutils.ChannelProperty(self, 'logging_channel')

    async def log(self, **kwargs):
        channel = await self.logging_channel.get()
        await channel.send(**kwargs)


def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(LoggingCog(bot))
