import asyncio

import discord
from discord import commands
from discord.ext import commands as cmds

from utils import discordutils, pnwutils, queries, config
import dbbot


class ApplicationCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

    @commands.command(guild_ids=config.guild_ids)
    @cmds.max_concurrency(1, cmds.BucketType.user)
    async def start_interview(self, ctx: discord.ApplicationContext,
                              q_num: commands.Option(int, 'Do not provide this parameter unless asked to',
                                                     name='question_number', default=1, min_value=1,
                                                     max_value=len(config.interview_questions))
                              ) -> None:
        """Gives you interview questions for you to respond to."""
        if not ctx.channel.name.endswith('-application'):
            await ctx.respond('This is not an interview channel!')
            return

        response_check = discordutils.get_msg_chk(ctx)
        await ctx.respond('Please answer each of the following questions in one message.')
        for question in config.interview_questions[q_num - 1:]:
            await ctx.respond(question)
            try:
                await self.bot.wait_for('message', check=response_check, timeout=config.timeout)
            except asyncio.TimeoutError:
                await ctx.send('You took too long to respond! Aborting...')
                return

        await ctx.respond('Thank you for answering our questions. An interviewer will be reviewing your answers'
                          'and will get back to you as soon as possible (1 - 4 hours). '
                          'They will respond to your queries and may ask follow up questions.')

    @commands.user_command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_any_role(config.gov_role_id, config.staff_role_id, guild_id=config.guild_id)
    async def accept(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Accept someone into the alliance!"""
        await member.add_roles(*map(discord.Object, config.on_accepted_added_roles),
                               reason=f'Accepted into {config.alliance_name}!')
        util_cog = self.bot.get_cog('UtilCog')
        if '/' in member.display_name:
            try:
                int(nation_id := member.display_name.split('/')[1])
            except ValueError:
                await ctx.respond('Error in getting nation id!')
                return
            await util_cog.nations[str(member.id)].options(nation_id)
            data = await pnwutils.api.post_query(self.bot.session, queries.acceptance_query,
                                                 {'nation_id': nation_id}, 'nations')
            data = data['data']
            await ctx.respond(
                f'Reason: Accepted (Leader Name: {data["leader_name"]}, Nation Name: {data["nation_name"]}, '
                f'Nation ID: {nation_id}, Discord User ID: {member.id})', ephemeral=True)
        else:
            await ctx.respond('Error in getting nation id!')

    @accept.error
    async def accept_on_error(self, ctx: discord.ApplicationContext, error: discord.ApplicationCommandError):
        if isinstance(error, discord.ApplicationCommandInvokeError):
            await ctx.respond('I do not have the permissions to add roles!')
            return
        await discordutils.default_error_handler(ctx, error)


def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(ApplicationCog(bot))
