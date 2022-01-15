import asyncio

import discord
from discord.ext import commands

from utils import discordutils
import dbbot


class ApplicationCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

    @commands.command()
    @commands.max_concurrency(1, commands.BucketType.user)
    async def start_interview(self, ctx: commands.Context) -> None:
        if not ctx.channel.name.endswith('-application'):
            await ctx.send('This is not an interview channel!')
            return None

        def response_check(m: discord.Message) -> bool:
            return m.author == ctx.author and m.channel == ctx.channel

        questions = (
            '1. Why do you want to join the Dark Brotherhood? Have you been in another alliance?',
            "2. What's your nation link and leader name?",
            "3. What's your timezone and first language?",
            '4. We as an alliance have high standards for activity. How often will you be able to log in?',
            '5. We believe that security of information is essential to sustainable operation. '
            'Do you promise not to leak information that will harm the well-being of the Dark Brotherhood '
            'or any of its associates?',
            '6. The Dark Brotherhood offers loans and grants for cities, projects and more, '
            'what do you think about paying them back?',
            '7. How do you feel about being called to defend and fight for your alliance at some point?',
            '8. How do you feel about potentially having to sacrifice your infrastructure fighting a losing war for '
            'the sake of doing the right thing?',
            '9. If two superiors of equal rank gave you conflicting orders, what would you do?',
            '10. What skills, knowledge and values can you bring to the alliance?',
            '11. Would you be interested in working in any of the following areas? '
            '(1) Internal Affairs (2) Foreign Affairs (3) Military Affairs (4) Finance. '
            'Remember that it is important to help your fellow members.\n\n'
            'Internal Affairs\n'
            '- Enlist and interview people\n'
            '- Enrich new initiates with the basics of the game\n'
            '- Engage the alliance with fun and games\n'
            '\n'
            'Foreign Affairs\n'
            '- Set up embassies\n'
            '- Be diplomats\n'
            '- Much more\n'
            '\n'
            'Military\n'
            "- Make sure everyone's military is up to code (MMR or Minimum Military Requirement)\n"
            '- Help plan wars, counters and raids.\n'
            '\n'
            'Finance\n'
            '- Manage resources, money, grant loans',
            '12. Do you have any questions or anything else you want to tell us?'
        )

        await ctx.send('Please answer each of the following questions in one message.')
        for question in questions:
            await ctx.send(question)
            try:
                await self.bot.wait_for('message', check=response_check, timeout=discordutils.Config.timeout)
            except asyncio.TimeoutError:
                await ctx.send('You took too long to respond! Aborting...')
                return

        await ctx.send('Thank you for answering our questions. An interviewer will be reviewing your answers'
                       'and will get back to you as soon as possible (1 - 4 hours). '
                       'They will respond to your queries and may ask follow up questions.')


def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(ApplicationCog(bot))