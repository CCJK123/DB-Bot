import asyncio
from datetime import datetime, timezone
import io

import discord
from discord import commands
from discord.ext import commands as cmds

from utils import discordutils, config, dbbot
from utils.queries import acceptance_query


class ApplicationCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot)
        self.application_category = discordutils.ChannelProperty(self, 'application_category')
        self.application_log = discordutils.ChannelProperty(self, 'application_log')
        self.applications = discordutils.MappingProperty[str, str](self, 'applications')
        self.completed_applications = discordutils.MappingProperty[str, str](self, 'accepted_applications')
    
    @commands.command(guild_ids=config.guild_ids)
    @commands.permission(role_id=config.member_role_id, permission=False, guild_id=config.guild_id)
    @cmds.max_concurrency(1, cmds.BucketType.user)
    async def apply(self, ctx: discord.ApplicationContext):
        """Apply to our alliance!"""
        await self.applications.initialise()
        await self.completed_applications.initialise()
        util_cog = self.bot.get_cog('UtilCog')
        nation_id = await util_cog.nations[ctx.author.id].get(None)
        if nation_id is None:
            if '/' in ctx.author.display_name:
                try:
                    int(nation_id := ctx.author.display_name.split('/')[-1])
                except ValueError:
                    await ctx.respond('Please register with __ or manually register to '
                                      'our database with `/register nation` first!')
                    return
                await util_cog.nations[ctx.author.id].set(nation_id)
            else:
                await ctx.respond('Please register with __ or manually register to '
                                  'our database with `/register nation` first!')
                return

        category: discord.CategoryChannel = await self.application_category.get(None)
        if category is None:
            await ctx.respond('Application Category has not been set! Aborting...')
            return
        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True),
            ctx.author: discord.PermissionOverwrite(read_messages=True),
            ctx.guild.get_role(config.interviewer_role_id): discord.PermissionOverwrite(read_messages=True)
        }
        try:
            channel = await category.create_text_channel(
                f'application-{nation_id}',
                reason=f'Application from {ctx.author.mention}',
                topic=f"{ctx.author.display_name}'s Application to {config.alliance_name}",
                overwrites=overwrites)
            await channel.move(end=True)
        except discord.Forbidden:
            await ctx.respond('I do not have the permissions to create channels in the category!')
            return

        await self.applications[channel.id].set(ctx.author.id)
        await ctx.respond(f'Please proceed to your interview channel at {channel.mention}', ephemeral=True)
        await channel.send(f'Welcome to the {config.alliance_name} interview. '
                           'When you are ready, please run the `/start_interview` command.')

    @commands.command(guild_ids=config.guild_ids)
    @commands.permission(role_id=config.member_role_id, permission=False, guild_id=config.guild_id)
    @cmds.max_concurrency(1, cmds.BucketType.channel)
    async def start_interview(self, ctx: discord.ApplicationContext,
                              q_num: commands.Option(int, 'Do not provide this parameter unless asked to',
                                                     name='question_number', default=1, min_value=1,
                                                     max_value=len(config.interview_questions))
                              ) -> None:
        """Gives you interview questions for you to respond to."""
        applicant_id = await self.applications[ctx.channel.id].get(None)
        if applicant_id is None:
            await ctx.respond('This channel is not an application channel!')
            return
        if int(applicant_id) != ctx.author.id:
            await ctx.respond('You are not the applicant of this application channel!')
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

    application = commands.SlashCommandGroup('application', 'Interviewer commands related to applications',
                                             guild_ids=config.guild_ids, default_permission=False,
                                             permissions=[
                                                 config.gov_role_permission,
                                                 commands.CommandPermission(config.interviewer_role_id, type=1,
                                                                            permission=True, guild_id=config.guild_id)
                                             ])

    @application.command(guild_ids=config.guild_ids, default_permission=False)
    @cmds.max_concurrency(1, cmds.BucketType.channel)
    async def accept(self, ctx: discord.ApplicationContext):
        """Accept someone into the alliance!"""
        applicant_id = await self.applications[ctx.channel_id].get(None)
        if applicant_id is None:
            await ctx.respond('This channel is not an application channel!')
            return

        applicant = ctx.guild.get_member(applicant_id)
        try:
            await applicant.add_roles(*map(discord.Object, config.on_accepted_added_roles),
                                      reason=f'Accepted into {config.alliance_name}!')
        except discord.Forbidden:
            await ctx.respond('I do not have the permissions to add roles!')
            return
        await self.applications[ctx.channel_id].delete()
        await self.completed_applications[ctx.channel_id].set((applicant_id, True))
        await ctx.respond(f'{applicant.mention} has been accepted.',
                          ephemeral=True)

    @application.command(guild_ids=config.guild_ids, default_permission=False)
    @cmds.max_concurrency(1, cmds.BucketType.channel)
    async def reject(self, ctx: discord.ApplicationContext):
        applicant_id = await self.applications[ctx.channel_id].get(None)
        if applicant_id is None:
            await ctx.respond('This channel is not an application channel!')
            return
        await self.applications[ctx.channel_id].delete()
        await self.completed_applications[ctx.channel_id].set((applicant_id, False))
        await ctx.respond(f'<@{applicant_id}> has been rejected.',
                          ephemeral=True)

    @application.command(guild_ids=config.guild_ids, default_permission=False)
    @cmds.max_concurrency(1, cmds.BucketType.channel)
    async def close(self, ctx: discord.ApplicationContext):
        """Close this application channel."""
        application_info = await self.completed_applications[ctx.channel_id].get(None)
        if application_info is None:
            await ctx.respond('This channel is not a completed application channel!')
            return
        application_log = await self.application_log.get(None)
        if application_log is None:
            await ctx.respond('Application Log channel is unset! Aborting...')
            return
        applicant_id, accepted = application_info
        applicant = ctx.guild.get_member(applicant_id)
        util_cog = self.bot.get_cog('UtilCog')
        nation_id = await util_cog.nations[applicant_id].get()
        data = await acceptance_query.query(self.bot.session, nation_id=nation_id)
        data = data['data'].pop()
        acc_str = 'Accepted' if accepted else 'Rejected'
        info_str = f'Leader Name: {data["leader_name"]}, Nation Name: {data["nation_name"]}, ' \
                   f'Nation ID: {nation_id}, Discord User: {applicant.name}, Discord User ID: {applicant_id}'

        transcript_list = [f'Transcript For Application of Nation {nation_id} (<@{applicant_id}>\n'
                           f'Closed at {datetime.now(timezone.utc).isoformat()} by {ctx.author.name}.\n']
        async for message in ctx.channel.history(limit=None, oldest_first=True):
            transcript_list.append(f'{message.created_at.isoformat()} {message.author.name} '
                                   f'({message.author.id}): {message.content}')
        await application_log.send(embed=discord.Embed(title=f'{acc_str} Application', description=info_str),
                                   file=discord.File(io.StringIO('\n'.join(transcript_list)),  # type: ignore
                                                     f'{nation_id}_application_transcript.txt',
                                                     description=f'Transcript of the application of nation {nation_id}')
                                   )
        await ctx.channel.delete(reason=f'Closing application by applicant with id {applicant_id}.')


def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(ApplicationCog(bot))
