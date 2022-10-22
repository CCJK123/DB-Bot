import asyncio
import logging

import aiohttp
import discord.utils

from utils import config, dbbot

cog_logger = logging.getLogger('cogs')
cog_logger.addHandler(logging.FileHandler('logs.txt'))


async def main():
    async with aiohttp.ClientSession() as session:
        discord.utils.setup_logging(root=False)
        bot = dbbot.DBBot(session, config.database_url)

        async with bot.database:
            async with bot:
                print('Starting Bot')
                await bot.start(config.token)


if __name__ == '__main__':
    asyncio.run(main())
