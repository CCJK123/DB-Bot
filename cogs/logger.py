from utils import discordutils, dbbot


class LoggingCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

        bot.log = self.log

    async def log(self, content: 'str | None' = None, **kwargs):
        channel_id = await self.bot.database.get_kv('channel_ids').get('logging_channel')
        await self.bot.get_channel(channel_id).send(content, **kwargs)


def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(LoggingCog(bot))
