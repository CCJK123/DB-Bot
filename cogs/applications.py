import asyncio
from datetime import datetime, timezone
import io

import discord
from discord.ext import commands

from utils import discordutils, config, dbbot
from utils.queries import acceptance_query


class ApplicationCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.users_table = self.bot.database.get_table('users')
        self.applications_table = self.bot.database.get_table('applications')

    @discord.app_commands.command()
    @discord.app_commands.default_permissions()
    @discordutils.max_one
    async def apply(self, interaction: discord.Interaction):
        """Apply to our alliance!"""
        nation_id = await self.users_table.select_val('nation_id').where(discord_id=interaction.user.id)
        if nation_id is None:
            if '/' in interaction.user.display_name:
                try:
                    nation_id = int(interaction.user.display_name.split('/')[-1])
                except ValueError:
                    await interaction.response.send_message(
                        'Please manually register to our database with `/register nation` first!')
                    return
                await self.users_table.insert(discord_id=interaction.user.id, nation_id=nation_id)
            else:
                await interaction.response.send_message(
                    'Please manually register to our database with `/register nation` first!')
                return

        channel_ids_table = self.bot.database.get_kv('channel_ids')
        cat_id = await channel_ids_table.get('application_category')
        if cat_id is None:
            await interaction.response.send_message('Application Category has not been set! Aborting...')
            return

        if await self.applications_table.exists(discord_id=interaction.user.id):
            await interaction.response.send_message('You already have an ongoing application!')
            return

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True),
            interaction.user: discord.PermissionOverwrite(read_messages=True),
            interaction.guild.get_role(config.interviewer_role_id): discord.PermissionOverwrite(read_messages=True)
        }

        try:
            category: discord.CategoryChannel = self.bot.get_channel(cat_id)  # type: ignore
            # have to create channel then move to end
            # otherwise it does not work for some reason
            channel = await category.create_text_channel(
                f'application-{nation_id}',
                reason=f'Application from {interaction.user.mention}',
                topic=f"{interaction.user.display_name}'s Application to {config.alliance_name}",
                overwrites=overwrites)
            await channel.move(end=True)
        except discord.Forbidden:
            await interaction.response.send_message(
                'I do not have the permissions to create channels in the application category! '
                'Aborting...')
            return

        await self.applications_table.insert(discord_id=interaction.user.id, channel_id=channel.id)
        await asyncio.gather(
            interaction.response.send_message(f'Please proceed to your interview channel at {channel.mention}',
                                              ephemeral=True),
            channel.send(f'Welcome to the {config.alliance_name} interview. '
                         'When you are ready, please run the `/start_interview` command.'))

    @apply.error
    async def apply_error(self, interaction: discord.Interaction,
                          error: discord.app_commands.AppCommandError) -> None:
        if isinstance(error.__cause__, commands.MaxConcurrencyReached):
            await interaction.response.send_message('You are already applying!', ephemeral=True)
            return

        await self.bot.default_on_error(interaction, error)

    @discord.app_commands.command()
    @discord.app_commands.default_permissions()
    @commands.max_concurrency(1, commands.BucketType.channel)
    @discord.app_commands.describe(question_number='What question number to start from. Leave blank.')
    async def start_interview(
            self, interaction: discord.Interaction,
            question_number: discord.app_commands.Range[int, 1, len(config.interview_questions)] = 1) -> None:
        """Gives you interview questions for you to respond to"""
        applicant_id = await self.applications_table.select_val('discord_id').where(channel_id=interaction.channel_id)
        if applicant_id is None:
            await interaction.response.send_message('This channel is not an application channel!')
            return
        if int(applicant_id) != interaction.user.id:
            await interaction.response.send_message('You are not the applicant of this application channel!')
            return

        response_check = discordutils.get_msg_chk(interaction)
        await interaction.response.send_message('Please answer each of the following questions in one message.')
        for question in config.interview_questions[question_number - 1:]:
            await interaction.followup.send(question)
            try:
                await self.bot.wait_for('message', check=response_check, timeout=config.timeout)
            except asyncio.TimeoutError:
                await interaction.followup.send('You took too long to respond! Aborting...')
                return

        await interaction.followup.send(config.interview_sendoff)

    @start_interview.error
    async def start_interview_error(self, interaction: discord.Interaction,
                                    error: discord.app_commands.AppCommandError) -> None:
        if isinstance(error.__cause__, commands.MaxConcurrencyReached):
            await interaction.response.send_message('You are already doing an interview!', ephemeral=True)
            return

        await self.bot.default_on_error(interaction, error)

    application = discord.app_commands.Group(
        name='application', description='Interviewer commands related to applications',
        default_permissions=discord.Permissions())

    @application.command()
    @commands.max_concurrency(1, commands.BucketType.channel)
    async def accept(self, interaction: discord.Interaction):
        """Accept someone into the alliance"""
        record = await self.applications_table.select_row('discord_id', 'status').where(
            channel_id=interaction.channel_id)
        if record is None:
            await interaction.response.send_message('This channel is not an application channel!')
            return
        if record['status'] is not None:
            await interaction.response.send_message('This application has already been processed!')
            return

        applicant = interaction.guild.get_member(record['discord_id'])
        try:
            await applicant.add_roles(*map(discord.Object, config.on_accepted_added_roles),
                                      reason=f'Accepted into {config.alliance_name}!', atomic=False)
        except discord.Forbidden:
            await interaction.response.send_message('I do not have the permissions to add roles!')
            return
        await self.applications_table.update('status = TRUE').where(channel_id=interaction.channel_id)
        await interaction.response.send_message(f'{applicant.mention} has been accepted.',
                                                ephemeral=True)

    @application.command()
    @commands.max_concurrency(1, commands.BucketType.channel)
    async def reject(self, interaction: discord.Interaction):
        """Reject someone from the alliance"""
        record = await self.applications_table.select_row('discord_id', 'status').where(
            channel_id=interaction.channel_id)
        if record is None:
            await interaction.response.send_message('This channel is not an application channel!')
            return
        if record['status'] is not None:
            await interaction.response.send_message('This application has already been processed!')
            return
        await self.applications_table.update('status = FALSE').where(channel_id=interaction.channel_id)
        await interaction.response.send_message(f'<@{record["discord_id"]}> has been rejected.',
                                                ephemeral=True)

    @application.command()
    @commands.max_concurrency(1, commands.BucketType.channel)
    async def close(self, interaction: discord.Interaction):
        """Close this application channel"""
        application_log = await self.bot.database.get_kv('channel_ids').get('application_log')
        if application_log is None:
            await interaction.response.send_message('Application Log channel is unset! Aborting...')
            return
        record = await self.bot.database.fetch_row(
            'SELECT application_id, discord_id, nation_id, status FROM users INNER JOIN applications '
            'ON users.discord_id = applications.discord_id WHERE applications.channel_id = $1', interaction.channel_id)
        if record is None:
            await interaction.response.send_message('This channel is not an application channel!')
            return
        if record['status'] is None:
            await interaction.response.send_message('The application in this channel has not been completed!')
            return
        respond_task = asyncio.create_task(interaction.response.send_message('Closing application channel...'))
        applicant = interaction.guild.get_member(record['discord_id'])
        nation_id = record["nation_id"]
        data = await acceptance_query.query(self.bot.session, nation_id=nation_id)
        data = data['data'][0]
        acc_str = 'Accepted' if record['status'] else 'Rejected'
        info_str = (f'Application Number: {record["application_id"]}, Leader Name: {data["leader_name"]}, '
                    f'Nation Name: {data["nation_name"]}, Nation ID: {nation_id}, '
                    f'Discord User: {applicant.name}, Discord User ID: {record["discord_id"]}')

        transcript_header = (
            f'Transcript For Application (ID: {record["application_id"]} of {applicant.name}\n'
            f'Closed at {datetime.now(timezone.utc).isoformat(timespec="seconds")} by '
            f'{interaction.user.name}.\n\n{info_str}\n')

        string_io = io.StringIO(transcript_header + '\n'.join(
            f'{message.created_at.isoformat()} {message.author.name} ({message.author.id}): {message.content}'
            async for message in interaction.channel.history(limit=None, oldest_first=True)))
        await asyncio.gather(
            application_log.send(
                embed=discord.Embed(title=f'{acc_str} Application', description=info_str),
                file=discord.File(string_io)),  # type: ignore
            interaction.channel.delete(
                reason=f'Closing application by {applicant.name} (Discord ID: {record["discord_id"]}).'),
            respond_task
        )


async def setup(bot: dbbot.DBBot) -> None:
    await bot.add_cog(ApplicationCog(bot))
