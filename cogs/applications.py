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
        super().__init__(bot, __name__)
        self.users_table = self.bot.database.get_table('users')
        self.applications_table = self.bot.database.get_table('applications')

    @commands.command(guild_ids=config.guild_ids)
    @commands.default_permissions()
    @cmds.max_concurrency(1, cmds.BucketType.user)
    async def apply(self, ctx: discord.ApplicationContext):
        """Apply to our alliance!"""
        nation_id = await self.users_table.select_val('nation_id').where(discord_id=ctx.author.id)
        if nation_id is None:
            if '/' in ctx.author.display_name:
                try:
                    nation_id = int(ctx.author.display_name.split('/')[-1])
                except ValueError:
                    await ctx.respond('Please manually register to '
                                      'our database with `/register nation` first!')
                    return
                await self.users_table.insert(discord_id=ctx.author.id, nation_id=nation_id)
            else:
                await ctx.respond('Please manually register to our database with `/register nation` first!')
                return

        channel_ids_table = self.bot.database.get_kv('channel_ids')
        cat_id = await channel_ids_table.get('application_category')
        if cat_id is None:
            await ctx.respond('Application Category has not been set! Aborting...')
            return

        if await self.applications_table.exists(discord_id=ctx.author.id):
            await ctx.respond('You already have an ongoing application!')
            return

        overwrites = {
            ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            ctx.guild.me: discord.PermissionOverwrite(read_messages=True),
            ctx.author: discord.PermissionOverwrite(read_messages=True),
            ctx.guild.get_role(config.interviewer_role_id): discord.PermissionOverwrite(read_messages=True)
        }

        try:
            category: discord.CategoryChannel = self.bot.get_channel(cat_id)  # type: ignore
            # have to create channel then move to end
            # otherwise it does not work for some reason
            channel = await category.create_text_channel(
                f'application-{nation_id}',
                reason=f'Application from {ctx.author.mention}',
                topic=f"{ctx.author.display_name}'s Application to {config.alliance_name}",
                overwrites=overwrites)
            await channel.move(end=True)
        except discord.Forbidden:
            await ctx.respond('I do not have the permissions to create channels in the application category! '
                              'Aborting...')
            return

        await self.applications_table.insert(discord_id=ctx.author.id, channel_id=channel.id)
        await asyncio.gather(
            ctx.respond(f'Please proceed to your interview channel at {channel.mention}', ephemeral=True),
            channel.send(f'Welcome to the {config.alliance_name} interview. '
                         'When you are ready, please run the `/start_interview` command.'))

    @apply.error
    async def apply_error(self, ctx: discord.ApplicationContext,
                          error: discord.ApplicationCommandError) -> None:
        if isinstance(error.__cause__, cmds.MaxConcurrencyReached):
            await ctx.respond('You are already applying!', ephemeral=True)
            return

        await self.bot.default_on_error(ctx, error)

    @commands.command(guild_ids=config.guild_ids)
    @commands.default_permissions()
    @cmds.max_concurrency(1, cmds.BucketType.channel)
    @discord.option('question_number', description='What question number to start from. Leave blank.',
                    min_value=1, max_value=len(config.interview_questions))
    async def start_interview(self, ctx: discord.ApplicationContext, question_number: int = 1) -> None:
        """Gives you interview questions for you to respond to"""
        applicant_id = await self.applications_table.select_val('discord_id').where(channel_id=ctx.channel_id)
        if applicant_id is None:
            await ctx.respond('This channel is not an application channel!')
            return
        if int(applicant_id) != ctx.author.id:
            await ctx.respond('You are not the applicant of this application channel!')
            return

        response_check = discordutils.get_msg_chk(ctx)
        await ctx.respond('Please answer each of the following questions in one message.')
        for question in config.interview_questions[question_number - 1:]:
            await ctx.respond(question)
            try:
                await self.bot.wait_for('message', check=response_check, timeout=config.timeout)
            except asyncio.TimeoutError:
                await ctx.send('You took too long to respond! Aborting...')
                return

        await ctx.respond(config.interview_sendoff)

    @start_interview.error
    async def start_interview_error(self, ctx: discord.ApplicationContext,
                                    error: discord.ApplicationCommandError) -> None:
        if isinstance(error.__cause__, cmds.MaxConcurrencyReached):
            await ctx.respond('You are already doing an interview!', ephemeral=True)
            return

        await self.bot.default_on_error(ctx, error)

    application = commands.SlashCommandGroup('application', 'Interviewer commands related to applications',
                                             guild_ids=config.guild_ids,
                                             default_member_permissions=discord.Permissions())

    @application.command(guild_ids=config.guild_ids, default_permission=False)
    @cmds.max_concurrency(1, cmds.BucketType.channel)
    async def accept(self, ctx: discord.ApplicationContext):
        """Accept someone into the alliance"""
        record = await self.applications_table.select_row('discord_id', 'status').where(channel_id=ctx.channel_id)
        if record is None:
            await ctx.respond('This channel is not an application channel!')
            return
        if record['status'] is not None:
            await ctx.respond('This application has already been processed!')

        applicant = ctx.guild.get_member(record['discord_id'])
        try:
            await applicant.add_roles(*map(discord.Object, config.on_accepted_added_roles),
                                      reason=f'Accepted into {config.alliance_name}!', atomic=False)
        except discord.Forbidden:
            await ctx.respond('I do not have the permissions to add roles!')
            return
        await self.applications_table.update('status = TRUE').where(channel_id=ctx.channel_id)
        await ctx.respond(f'{applicant.mention} has been accepted.',
                          ephemeral=True)

    @application.command(guild_ids=config.guild_ids)
    @cmds.max_concurrency(1, cmds.BucketType.channel)
    async def reject(self, ctx: discord.ApplicationContext):
        """Reject someone from the alliance"""
        record = await self.applications_table.select_row('discord_id', 'status').where(channel_id=ctx.channel_id)
        if record is None:
            await ctx.respond('This channel is not an application channel!')
            return
        if record['status'] is not None:
            await ctx.respond('This application has already been processed!')
        await self.applications_table.update('status = FALSE').where(channel_id=ctx.channel_id)
        await ctx.respond(f'<@{record["discord_id"]}> has been rejected.',
                          ephemeral=True)

    @application.command(guild_ids=config.guild_ids)
    @cmds.max_concurrency(1, cmds.BucketType.channel)
    async def close(self, ctx: discord.ApplicationContext):
        """Close this application channel"""
        application_log = await self.bot.database.get_kv('channel_ids').get('application_log')
        if application_log is None:
            await ctx.respond('Application Log channel is unset! Aborting...')
            return
        record = await self.bot.database.fetch_row(
            'SELECT application_id, discord_id, nation_id, status FROM users INNER JOIN applications '
            'ON users.discord_id = applications.discord_id WHERE applications.channel_id = $1', ctx.channel_id)
        if record is None:
            await ctx.respond('This channel is not an application channel!')
            return
        if record['status'] is None:
            await ctx.respond('The application in this channel has not been completed!')
            return

        applicant = ctx.guild.get_member(record['discord_id'])
        nation_id = record["nation_id"]
        data = await acceptance_query.query(self.bot.session, nation_id=nation_id)
        data = data['data'][0]
        acc_str = 'Accepted' if record['status'] else 'Rejected'
        info_str = (f'Application Number: {record["application_id"]}, Leader Name: {data["leader_name"]}, '
                    f'Nation Name: {data["nation_name"]}, Nation ID: {nation_id}, '
                    f'Discord User: {applicant.name}, Discord User ID: {record["discord_id"]}')

        transcript_header = (f'Transcript For Application (ID: {record["application_id"]} of {applicant.name}\n'
                             f'Closed at {datetime.now(timezone.utc).isoformat(timespec="seconds")} by '
                             f'{ctx.author.name}.\n\n{info_str}\n')

        string_io = io.StringIO(transcript_header + '\n'.join(
            f'{message.created_at.isoformat()} {message.author.name} ({message.author.id}): {message.content}'
            async for message in ctx.channel.history(limit=None, oldest_first=True)))
        await application_log.send(embed=discord.Embed(title=f'{acc_str} Application', description=info_str),
                                   file=discord.File(string_io))  # type: ignore

        await ctx.channel.delete(
            reason=f'Closing application by {applicant.name} (Discord ID: {record["discord_id"]}).')


def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(ApplicationCog(bot))
