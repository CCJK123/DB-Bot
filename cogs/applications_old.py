import asyncio

import discord
from discord.ext import commands

from utils import config, dbbot, discordutils


class OldApplicationCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

    @discord.app_commands.command()
    @discord.app_commands.default_permissions()
    @commands.max_concurrency(1, commands.BucketType.channel)
    async def start_interview(self, interaction: discord.Interaction) -> None:
        """Gives you interview questions for you to respond to"""
        response_check = discordutils.get_msg_chk(interaction)
        await interaction.response.send_message('Please answer each of the following questions in one message.')
        for question in config.interview_questions:
            await interaction.channel.send(question)
            try:
                await self.bot.wait_for('message', check=response_check, timeout=config.timeout)
            except asyncio.TimeoutError:
                await interaction.channel.send('You took too long to respond! Aborting...')
                return

        await interaction.channel.send(config.interview_sendoff)


async def setup(bot: dbbot.DBBot) -> None:
    await bot.add_cog(OldApplicationCog(bot))
