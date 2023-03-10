import asyncio
from datetime import datetime, timezone
import io

import discord
from discord.ext import commands

from ..utils import discordutils, config
from .. import dbbot
from ..utils.queries import acceptance_query


class ApplyView(discordutils.PersistentView):
    def __init__(self, channel_id: 'int | None' = None, message_id: 'int | None' = None, *, custom_id: int):
        super().__init__(custom_id=custom_id)
        self.users_table = self.bot.database.get_table('users')
        self.applications_table = self.bot.database.get_table('applications')
        self.channel_id: 'int | None' = channel_id
        self.message_id: 'int | None' = message_id

    def get_state(self) -> tuple:
        return {}, self.channel_id, self.message_id

    @discordutils.persistent_button(label='Test', style=discord.ButtonStyle.blurple, emoji='🕳️')
    async def apply_button(self, _button: discordutils.PersistentButton, interaction: discord.Interaction):
        """Apply to our alliance!"""
        nation_id = await self.users_table.select_val('nation_id').where(discord_id=interaction.user.id)
        if nation_id is None:
            if '/' in interaction.user.display_name:
                try:
                    nation_id = int(interaction.user.display_name.split('/')[-1])
                except ValueError:
                    await interaction.response.send_message(
                        'Please manually register to our database with `/register nation` first!', ephemeral=True)
                    return
                await self.users_table.insert(discord_id=interaction.user.id, nation_id=nation_id)
            else:
                await interaction.response.send_message(
                    'Please manually register to our database with `/register nation` first!', ephemeral=True)
                return

        channel_ids_table = self.bot.database.get_kv('channel_ids')
        cat_id = await channel_ids_table.get('application_category')
        if cat_id is None:
            await interaction.response.send_message('Application Category has not been set! Aborting...')
            return

        if await self.applications_table.exists(discord_id=interaction.user.id):
            await interaction.response.send_message('You already have an ongoing application!', ephemeral=True)
            return

        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
            interaction.guild.me: discord.PermissionOverwrite(read_messages=True),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, read_messages=True, read_message_history=True, send_messages=True,
                manage_channels=True),
            interaction.guild.get_role(config.interviewer_role_id): discord.PermissionOverwrite(read_messages=True)
        }
        if None in overwrites:
            del overwrites[None]

        try:
            category: discord.CategoryChannel = self.bot.get_channel(cat_id)  # type: ignore
            # have to create channel then move to end
            # otherwise it does not work for some reason
            channel = await category.create_text_channel(
                f'application-{nation_id}',
                reason=f'Application from {interaction.user.display_name}',
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
            channel.send(embed=discord.Embed(
                description=
                f'Welcome {interaction.user.mention}!\n'
                f'Glad to see that you are interested in applying to {config.alliance_name}.\n'
                'When you have about 5 to 10 minutes of free time, '
                'kindly use the `/start_interview` command to begin a short interview.'
            )))


class ApplicationCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.users_table = self.bot.database.get_table('users')
        self.applications_table = self.bot.database.get_table('applications')

    @commands.command()
    @commands.has_role(config.gov_role_id)
    async def create_apply_button(self, ctx: commands.Context):
        kv = self.bot.database.get_kv('kv_ints')
        if old := await kv.get('apply_view_id'):
            old_view = await self.bot.view_table.get(old)
            discordutils.disable_all(old_view)
            old_view.stop()
            await asyncio.gather(
                self.bot.get_channel(old_view.channel_id).get_partial_message(old_view.message_id).edit(view=old_view),
                self.bot.remove_view(old_view))
        apply_view = ApplyView(custom_id=await self.bot.get_custom_id())
        msg = await ctx.send('button!', view=apply_view)
        apply_view.channel_id = ctx.channel.id
        apply_view.message_id = msg.id
        await asyncio.gather(
            self.bot.add_view(apply_view, message_id=msg.id),
            kv.set('apply_view_id', apply_view.custom_id))

    @discord.app_commands.command()
    @discord.app_commands.default_permissions()
    @commands.max_concurrency(1, commands.BucketType.channel)
    @discord.app_commands.describe(question_number='What question number to start from. Leave blank.')
    async def _new_start_interview(
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

    _application = discord.app_commands.Group(
        name='_application', description='Interviewer commands related to applications',
        default_permissions=discord.Permissions())

    @_application.command()
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

    @_application.command()
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

    @_application.command()
    @commands.max_concurrency(1, commands.BucketType.channel)
    async def close(self, interaction: discord.Interaction):
        """Close this application channel"""
        application_log = await self.bot.database.get_kv('channel_ids').get('application_log_channel')
        if application_log is None:
            await interaction.response.send_message('Application Log channel is unset! Aborting...')
            return
        record = await self.bot.database.fetch_row(
            'SELECT application_id, u.discord_id, nation_id, status FROM users AS u INNER JOIN applications AS a '
            'ON u.discord_id = a.discord_id WHERE a.channel_id = $1', interaction.channel_id)
        if record is None:
            await interaction.response.send_message('This channel is not an application channel!')
            return
        if record['status'] is None:
            await interaction.response.send_message('The application in this channel has not been completed!')
            return
        await interaction.response.send_message('Closing application channel...')
        applicant = interaction.guild.get_member(record['discord_id'])
        nation_id = record["nation_id"]
        data = await acceptance_query.query(self.bot.session, nation_id=nation_id)
        data = data['data'][0]
        acc_str = 'Accepted' if record['status'] else 'Rejected'
        info_str = (f'Application Number: {record["application_id"]}, Leader Name: {data["leader_name"]}, '
                    f'Nation Name: {data["nation_name"]}, Nation ID: {nation_id}, '
                    f'Discord User: {applicant.name}, Discord User ID: ')

        transcript_header = (
            f'Transcript For Application (ID: {record["application_id"]} of {applicant.name}\n'
            f'Closed at {datetime.now(timezone.utc).isoformat(timespec="seconds")} by '
            f'{interaction.user.name}.\n\n{info_str}{record["discord_id"]}')

        string_io = io.StringIO(transcript_header)
        string_io.seek(0, io.SEEK_END)
        async for message in interaction.channel.history(limit=None, oldest_first=True):
            string_io.write(f'\n{message.created_at.isoformat()} {message.author.name} '
                            f'({message.author.id}): {message.content}')
        string_io.seek(0)
        await asyncio.gather(
            self.bot.get_channel(application_log).send(
                embed=discord.Embed(title=f'{acc_str} Application', description=f'{info_str}<@{record["discord_id"]}>'),
                file=discord.File(string_io, f'application-{record["application_id"]}.txt',  # type: ignore
                                  description=f'Application {record["application_id"]} Transcript')),
            interaction.channel.delete(
                reason=f'Closing application by {applicant.name} (Discord ID: {record["discord_id"]}).'),
            self.applications_table.delete().where(channel_id=interaction.channel_id)
        )

    @_application.command()
    @discord.app_commands.describe(ephemeral='Whether to only allow you to see the message')
    async def active(self, interaction: discord.Interaction, ephemeral: bool = True):
        """Gets a list of active applications and their statuses"""
        paginator_pages = []
        async with self.bot.database.acquire() as conn:
            async with conn.transaction():
                app_cursor = await self.applications_table.select().cursor(conn)
                while chunk := await app_cursor.fetch(10):
                    embeds = []
                    for rec in chunk:
                        embed = discord.Embed(title=f'Application #{rec["application_id"]}')
                        embed.add_field(name='Applicant', value=f'<@{rec["discord_id"]}>')
                        embed.add_field(name='Channel', value=f'<#{rec["channel_id"]}>')
                        if rec['status'] is None:
                            status = 'Pending'
                        elif rec['status']:
                            status = 'Accepted'
                        else:
                            status = 'Rejected'
                        embed.add_field(name='Status', value=status)
                        embeds.append(embed)
                    paginator_pages.append(embeds)
        if paginator_pages:
            paginator = discordutils.Pager(paginator_pages)
            await paginator.respond(interaction, ephemeral=ephemeral)
            return
        await interaction.response.send_message('There are no active applications!', ephemeral=ephemeral)


async def setup(bot: dbbot.DBBot) -> None:
    await bot.add_cog(ApplicationCog(bot))
