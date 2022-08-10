from __future__ import annotations

import asyncio
import os
import random
import traceback
from collections.abc import Awaitable, Callable, Sequence

import aiohttp
import discord
import pnwkit
from discord.ext import tasks, commands as cmds

from utils import discordutils, databases, config
from utils.queries import offshore_info_query


async def database_initialisation(database):
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


class DBBot(discord.Bot):
    def __init__(self, db_url: str, on_ready_func: Callable[[], None] | None = None,
                 possible_statuses: Sequence[discord.Activity] | None = None):
        intents = discord.Intents(guilds=True, messages=True, members=True)
        super().__init__(intents=intents)
        self.excluded = {'open_slots_detector', 'new_war_detector', 'market', 'debug', 'applications'}
        self.session: aiohttp.ClientSession | None = None
        self.kit = pnwkit.QueryKit(config.api_key)

        self.database: databases.Database = databases.PGDatabase(db_url)
        # define type `resources` and define addition and subtraction for it
        self.database.add_on_init(database_initialisation)

        self.database.new_table('users', discord_id='BIGINT PRIMARY KEY', nation_id='INT UNIQUE NOT NULL',
                                balance='resources DEFAULT ROW(0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0) NOT NULL')
        self.database.new_table('loans', ',FOREIGN KEY(discord_id) REFERENCES users(discord_id)',
                                discord_id='BIGINT PRIMARY KEY', loaned='resources NOT NULL',
                                due_date='timestamp(0) with time zone NOT NULL')
        self.database.new_table(
            'applications', ',FOREIGN KEY(discord_id) REFERENCES users(discord_id)',
            application_id='SMALLINT GENERATED ALWAYS AS IDENTITY (MINVALUE 0 MAXVALUE 99 CYCLE)',
            discord_id='BIGINT UNIQUE NOT NULL', channel_id='INT PRIMARY KEY', status='BOOL DEFAULT NULL')
        self.database.new_table('market', resource='TEXT PRIMARY KEY', buy_price='INT DEFAULT NULL',
                                sell_price='INT DEFAULT NULL', stock='BIGINT DEFAULT 0 NOT NULL')

        self.database.new_kv('channel_ids', 'BIGINT')
        self.database.new_kv('kv_bools', 'BOOL')
        self.view_table = databases.ViewTable(self.database, 'views')
        self.database.add_table(self.view_table)

        self.on_ready_func = on_ready_func
        self.possible_statuses = possible_statuses if possible_statuses is not None else (
            *map(discord.Game, ("with Python", "with the P&W API")),
            discord.Activity(type=discord.ActivityType.listening, name="Spotify"),
            discord.Activity(type=discord.ActivityType.watching, name="YouTube")
        )

        discordutils.PersistentView.bot = self

        self.prepared = False

    def load_cogs(self, directory: str) -> None:
        """
        directory: str
        Name of directory where the cogs can be found.

        Loads extensions found in [directory] into the bot.
        """
        cogs = {file.split('.')[0] for file in os.listdir(directory)
                if file.endswith('.py') and not file.startswith('_')}
        for ext in cogs - self.excluded:
            self.load_extension(f'{directory}.{ext}')

    async def prepare(self):
        self.session = await aiohttp.ClientSession().__aenter__()
        self.database = await self.database.__aenter__()
        self.kit.aiohttp_session = self.session

        self.change_status.start()

    async def cleanup(self):
        await self.session.__aexit__(None, None, None)
        await self.database.__aexit__(None, None, None)

        self.change_status.stop()

        for cog in self.cogs.values():
            if isinstance(cog, discordutils.CogBase):
                await cog.on_cleanup()

        await asyncio.sleep(1)

    @tasks.loop(seconds=40)
    async def change_status(self):
        await self.change_presence(activity=random.choice(self.possible_statuses))

    async def add_view(self, view: discordutils.PersistentView, *, message_id: int | None = None) -> None:
        super().add_view(view, message_id=message_id)
        await self.view_table.add(view)

    async def remove_view(self, view: discordutils.PersistentView):
        await self.view_table.remove(view.custom_id)

    async def on_ready(self):
        if not self.prepared:
            await self.prepare()
            self.prepared = True

        await asyncio.gather(*(cog.on_ready() for cog in self.cogs.values() if isinstance(cog, discordutils.CogBase)))

        # add views
        async for view in self.view_table.get_all():
            super().add_view(view)
            print(f'Adding a {type(view)} from storage!')

        if self.on_ready_func is not None:
            self.on_ready_func()
        print('Ready!')

    async def on_application_command_error(self, ctx: discord.ApplicationContext, exception: discord.DiscordException):
        command = ctx.command
        if command and command.has_error_handler():
            return

        ignored = (
            cmds.CommandNotFound,
            cmds.MissingRole,
            cmds.MissingRequiredArgument
        )

        if isinstance(c := exception.__cause__, discord.NotFound):
            print(getattr(c, 'text'))
            try:
                await ctx.respond('Sorry, please rerun your command.')
            except discord.HTTPException as e:
                print('Responding failed! Exc Type: ', type(e))
                await ctx.send('Sorry, please rerun your command.')
        elif not isinstance(exception, ignored):
            await self.default_on_error(ctx, exception)

    @staticmethod
    async def default_on_error(ctx: discord.ApplicationContext, exception: discord.DiscordException):
        try:
            await ctx.respond(f'Sorry, an exception occurred in the command `{ctx.command}`.')
        except discord.HTTPException as e:
            print('Responding failed! Exc Type: ', type(e))
            await ctx.send('Sorry, an exception occurred.')

        s = ''
        for ex in traceback.format_exception(type(exception), exception, exception.__traceback__):
            if ex == '\nThe above exception was the direct cause of the following exception:\n\n':
                await ctx.send(f'```{s}```')
                s = ex
            else:
                s += ex
        await ctx.send(f'```{s}```')

        # print the exception to stderr too
        traceback.print_exception(type(exception), exception, exception.__traceback__)

    async def get_offshore_id(self):
        data = await offshore_info_query.query(self.session, api_key=config.offshore_api_key)
        return data['nation']['alliance_id']

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
