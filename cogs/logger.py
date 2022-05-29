from utils import discordutils, dbbot


class LoggingCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

        bot.log_func = self.log

    async def log(self, content: 'str | None', **kwargs):
        channel = await self.bot.database.get_kv('channel_ids').get('logging_channel')
        await channel.send(content, **kwargs)


def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(LoggingCog(bot))
