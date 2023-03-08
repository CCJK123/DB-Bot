from __future__ import annotations

import asyncio
import random
import traceback
import pkgutil
from collections.abc import Awaitable, Sequence

import aiohttp
import asyncpg
import discord
import pnwkit
from discord.ext import tasks, commands

from .utils import discordutils, databases, config


async def database_init_pre(database: databases.Database):
    # define type `resources` and define addition and subtraction for it
    await database.execute('''
        DO $$ BEGIN PERFORM 'resources'::regtype; EXCEPTION WHEN undefined_object THEN CREATE TYPE resources AS (
            money BIGINT, food BIGINT, coal BIGINT, oil BIGINT, uranium BIGINT, lead BIGINT, iron BIGINT,
            bauxite BIGINT, gasoline BIGINT, munitions BIGINT, steel BIGINT, aluminum BIGINT);
        END $$;

        CREATE OR REPLACE FUNCTION add_resources(resources, resources) RETURNS resources AS $$
            SELECT ROW(
                $1.money + $2.money, $1.food + $2.food, $1.coal + $2.coal, $1.oil + $2.oil,
                $1.uranium + $2.uranium, $1.lead + $2.lead, $1.iron + $2.iron, $1.bauxite + $2.bauxite,
                $1.gasoline + $2.gasoline, $1.munitions + $2.munitions, $1.steel + $2.steel, $1.aluminum + $2.aluminum)
        $$ LANGUAGE SQL;
        CREATE OR REPLACE FUNCTION sub_resources(resources, resources) RETURNS resources AS $$
            SELECT ROW(
                $1.money - $2.money, $1.food - $2.food, $1.coal - $2.coal, $1.oil - $2.oil,
                $1.uranium - $2.uranium, $1.lead - $2.lead, $1.iron - $2.iron, $1.bauxite - $2.bauxite,
                $1.gasoline - $2.gasoline, $1.munitions - $2.munitions, $1.steel - $2.steel, $1.aluminum - $2.aluminum)
        $$ LANGUAGE SQL;

        DO $$ BEGIN
            CREATE OPERATOR + (leftarg = resources, rightarg = resources, function = add_resources, commutator = +);
            CREATE OPERATOR - (leftarg = resources, rightarg = resources, function = sub_resources);
        EXCEPTION WHEN duplicate_function THEN null;
        END $$;
        ''')


async def database_init_post(database: databases.Database):
    # ensure misc table is populated with its single row
    await database.execute('INSERT INTO misc DEFAULT VALUES ON CONFLICT DO NOTHING')


class DBBot(commands.Bot):
    def __init__(self, session: aiohttp.ClientSession, db_url: str,
                 possible_statuses: Sequence[discord.Activity] | None = None):
        intents = discord.Intents(guilds=True, messages=True, message_content=True, members=True)
        super().__init__(intents=intents, command_prefix='`!', allowed_mentions=discord.AllowedMentions.none())
        self.session = session
        self.excluded = {'debug', 'applications_old'}
        self.kit = pnwkit.QueryKit(config.api_key)

        self.database: databases.Database = databases.PGDatabase(database_init_pre, database_init_post, dsn=db_url)

        self.database.new_table('users', discord_id='BIGINT PRIMARY KEY', nation_id='INT UNIQUE NOT NULL',
                                balance='resources DEFAULT ROW(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0) NOT NULL')
        self.database.new_table('loans', ',FOREIGN KEY(discord_id) REFERENCES users(discord_id)',
                                discord_id='BIGINT PRIMARY KEY', loaned='resources NOT NULL',
                                due_date='TIMESTAMP(0) WITH TIME ZONE NOT NULL')
        self.database.new_table(
            'applications',
            application_id='SMALLINT GENERATED ALWAYS AS IDENTITY (MINVALUE 0 MAXVALUE 99 CYCLE)',
            discord_id='BIGINT UNIQUE NOT NULL REFERENCES users(discord_id)', channel_id='BIGINT PRIMARY KEY',
            status='BOOL DEFAULT NULL')
        self.database.new_table('market', resource='TEXT PRIMARY KEY', ordering='SMALLINT UNIQUE NOT NULL',
                                buy_price='INT DEFAULT NULL', sell_price='INT DEFAULT NULL',
                                stock='BIGINT DEFAULT 0 NOT NULL')
        self.database.new_table('coalitions', name='TEXT PRIMARY KEY', alliances='INT[] NOT NULL')
        self.database.new_table('misc', one='BOOLEAN GENERATED ALWAYS AS (TRUE) STORED UNIQUE',
                                open_slot_coalition='TEXT REFERENCES coalitions(name) DEFAULT NULL')
        self.database.new_table('to_resend', time='TIMESTAMP(0) WITH TIME ZONE NOT NULL', send_id='BIGINT',
                                channel_id='BIGINT NOT NULL', message_id='BIGINT NOT NULL')

        self.database.new_kv('channel_ids', 'BIGINT')
        self.database.new_kv('kv_ints', 'INT')
        self.database.new_kv('kv_bools', 'BOOL')
        self.view_table = databases.ViewTable(self.database, 'views')
        self.database.add_table(self.view_table)

        self.possible_statuses = possible_statuses if possible_statuses is not None else (
            *map(discord.Game, ("with Python", "with the P&W API")),
            discord.Activity(type=discord.ActivityType.listening, name="Spotify"),
            discord.Activity(type=discord.ActivityType.watching, name="YouTube")
        )

        discordutils.PersistentView.bot = self

        self.tree.error(self.on_app_command_error)
        self.command_ids: dict[int, dict[str, int]] = {}

    async def setup_hook(self) -> None:
        print('Loading Cogs')
        await self.load_extensions('bot/cogs', self.excluded)
        for guild in map(discord.Object, config.guild_ids):
            self.tree.copy_global_to(guild=guild)
            try:
                self.command_ids[guild.id] = {c.name: c.id for c in await self.tree.sync(guild=guild)}
            except discord.Forbidden as e:
                print(f'Failed to sync to guild with id {guild.id}: {e.text}')

    @staticmethod
    def get_extensions(directory: str) -> set[str]:
        return {m.name for m in pkgutil.iter_modules([directory])}

    async def load_extensions(self, directory: str, excluded: set[str]) -> None:
        """
        Loads extensions found in [directory] into the bot.
        Excludes any found in [excluded]
        """
        cog_tasks = (asyncio.create_task(self.load_extension(f'{directory.replace("/", ".")}.{ext}'))
                     for ext in self.get_extensions(directory) - excluded)
        await asyncio.gather(*cog_tasks)

    async def unload_extensions(self, directory: str, excluded: set[str]) -> None:
        """
        Unloads extensions found in [directory] into the bot.
        Excludes any found in [excluded]
        """
        cog_tasks = (asyncio.create_task(self.unload_extension(f'{directory}.{ext}'))
                     for ext in self.get_extensions(directory) - excluded)
        await asyncio.gather(*cog_tasks)

    async def __aenter__(self):
        await super().__aenter__()
        self.kit.aiohttp_session = self.session

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.change_status.stop()
        await self.unload_extensions('cogs', self.excluded)
        await super().__aexit__(exc_type, exc_val, exc_tb)
        await asyncio.sleep(1)

    @tasks.loop(minutes=20)
    async def change_status(self):
        await self.change_presence(activity=random.choice(self.possible_statuses))

    async def add_view(self, view: discordutils.PersistentView, *, message_id: int | None = None) -> None:
        super().add_view(view, message_id=message_id)
        await self.view_table.add(view)

    async def remove_view(self, view: discordutils.PersistentView):
        await self.view_table.remove(view.custom_id)

    async def on_ready(self):
        self.change_status.start()

        # add views
        async for view in self.view_table.get_all():
            super().add_view(view)
            print(f'Adding a {type(view)} from storage!')

        print('Ready!')

    async def on_app_command_error(self, interaction: discord.Interaction,
                                   exception: discord.app_commands.AppCommandError):
        command = interaction.command
        if command is not None and command._has_any_error_handlers():
            return

        ignored = (

        )

        if not isinstance(exception, ignored):
            await self.default_on_error(interaction, exception)

    async def default_on_error(self, interaction: discord.Interaction, exception: discord.app_commands.AppCommandError):
        command = interaction.command
        if isinstance(exception.__cause__, discord.NotFound):
            # def from a command from some sort, since those are the ones where the interactions expire
            suffix = (f': </{command.qualified_name}:{self.command_ids[interaction.guild_id][command.qualified_name]}>'
                      if isinstance(command, discord.app_commands.Command) else '.')
            await interaction.channel.send(f'Sorry, please rerun your command{suffix}')
            return
        if isinstance(exception.__cause__, asyncpg.PostgresSyntaxError):
            print(exception.__cause__.as_dict())
        if command is None:
            # no associated command
            # likely a button or something
            try:
                await discordutils.interaction_send(
                    interaction,
                    f'Sorry, an exception occurred.')
            except discord.HTTPException as e:
                print('Responding failed! Exc Type: ', type(e))
                await interaction.channel.send(f'Sorry, an exception occurred.')
            finally:
                await self.log(f'An exception occurred when {interaction.user.mention} '
                               f'did something in {interaction.channel.mention}.')
        else:
            try:
                name = (f'</{command.qualified_name}:{self.command_ids[interaction.guild_id][command.qualified_name]}>'
                        if isinstance(command, discord.app_commands.Command) else f'`{command.qualified_name}`')
            except KeyError:
                name = f'`{command.qualified_name}`'

            try:
                await discordutils.interaction_send(
                    interaction,
                    f'Sorry, an exception occurred in the command {name}.')
            except discord.HTTPException as e:
                print('Responding failed! Exc Type: ', type(e))
                await interaction.channel.send(f'Sorry, an exception occurred in the command {name}.')
            finally:
                await self.log(f'An exception occurred when {interaction.user.mention} was running the command {name} '
                               f'in {interaction.channel.mention}.')

        await self.log(f'Interaction Data: {interaction.data}')
        s = ''
        for ex in traceback.format_exception(type(exception), exception, exception.__traceback__):
            if ex == '\nThe above exception was the direct cause of the following exception:\n\n':
                await self.log(f'```{s}```')
                s = ex
            else:
                s += ex
        await self.log(f'```{s}```')

        # print the exception to stderr too
        traceback.print_exception(type(exception), exception, exception.__traceback__)

    @staticmethod
    async def log(c: str | None = None, **kwargs):
        pass

    def get_custom_id(self) -> Awaitable[int]:
        return self.view_table.get_id()


# the new bot does not seem to have a help command, the help command has not been ported over to slash yet, I believe
# we will see if this class gets use in the future
"""
class DBHelpCommand(cmds.HelpCommand):
    d_desc = 'No description found'

    async def send_bot_help(self, mapping: Mapping[discord.Cog | None, list[commands.ApplicationCommand]]):
        embeds = []
        for k in mapping:
            filtered = await self.filter_commands(mapping[k])
            if filtered:
                embeds.append(self.create_cog_embed(k, filtered))

        await self.get_destination().send(embeds=embeds)

    def create_cog_embed(self, cog: discord.Cog, cog_commands: list[commands.ApplicationCommand]):
        embed = discord.Embed(title=cog.qualified_name,
                              description=cog.description)

        for cmd in cog_commands:
            embed.add_field(name=cmd.name,
                            value=cmd.description or cmd.short_doc or self.d_desc,
                            inline=False)

        return embed

    async def send_cog_help(self, cog: discord.Cog):
        embed = self.create_cog_embed(cog, await self.filter_commands(cog.get_commands()))
        await self.get_destination().send(embed=embed)

    async def send_group_help(self, group: cmds.Group):
        embed = discord.Embed(
            title=self.get_command_signature(group),
            description=group.description
        )
        for cmd in await self.filter_commands(group.commands):
            embed.add_field(name=cmd.name,
                            value=cmd.description or cmd.short_doc or self.d_desc,
                            inline=False)
        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command: commands.ApplicationCommand):
        await self.get_destination().send(embed=discord.Embed(
            title=self.get_command_signature(command),
            description=command.description or command.short_doc
        ))
"""
