from __future__ import annotations

import asyncio
import os
import random
import traceback
from typing import Callable, Sequence

import aiohttp
import discord
from discord.ext import tasks, commands as cmds

from utils import discordutils, databases


# pycharm complains about sync_commands not being written,
# cause in the library they have not written it, it just raises NotImplemented
# noinspection PyAbstractClass
class DBBot(discord.Bot):
    def __init__(self, db_url: str, on_ready_func: Callable[[], None] | None = None,
                 status: Sequence[discord.Activity] | None = None):
        intents = discord.Intents(guilds=True, messages=True, members=True)
        super().__init__(intents=intents)

        self.session = None
        self.database = databases.RudimentaryDatabase(db_url)
        self.views = discordutils.ViewStorage[discordutils.PersistentView](self, 'views')
        self.prepped = False
        self.on_ready_func = on_ready_func
        self.status = status if status is not None else (
            *map(discord.Game, ("with Python", "with the P&W API")),
            discord.Activity(type=discord.ActivityType.listening, name="Spotify"),
            discord.Activity(type=discord.ActivityType.watching, name="YouTube")
        )

    def load_cogs(self, directory: str) -> None:
        """
        directory: str
        Name of directory where the cogs can be found.

        Loads extensions found in [directory] into the bot.
        """
        cogs = (file.split('.')[0] for file in os.listdir(directory)
                if file.endswith('.py') and not file.startswith('_'))
        for ext in cogs:
            self.load_extension(f'{directory}.{ext}')

    async def prep(self):
        self.session = await aiohttp.ClientSession().__aenter__()
        self.database = await self.database.__aenter__()

        if await self.views.get(None) is None:
            await self.views.set({})

        self.change_status.start()

    async def cleanup(self):
        await self.session.__aexit__(None, None, None)
        await self.database.__aexit__(None, None, None)
        await asyncio.sleep(.25)

    @tasks.loop(seconds=20)
    async def change_status(self):
        await self.change_presence(activity=random.choice(self.status))

    async def add_view(self, view: discordutils.PersistentView, *, message_id: int | None = None) -> None:
        super().add_view(view, message_id=message_id)
        view.bot = self
        await self.views.add(view)

    async def on_ready(self):
        if not self.prepped:
            self.prepped = True
            await self.prep()

        for cog in self.cogs.values():
            if isinstance(cog, discordutils.CogBase):
                await cog.on_ready()

        # add views
        for view in await self.views.get_views():
            await self.add_view(view)
            print(f'Adding a {type(view)} from storage!')

        if self.on_ready_func is not None:
            self.on_ready_func()
        print('Ready!')

    async def on_application_command_error(self, ctx: discord.ApplicationContext, exception: discord.DiscordException):
        command = ctx.command
        if command and command.has_error_handler():
            print(f'Ignoring {exception!r}, already has handler')
            return

        ignored = (
            cmds.CommandNotFound,
            cmds.MissingRole,
            cmds.MissingRequiredArgument
        )
        if not isinstance(exception, ignored):
            await super().on_application_command_error(ctx, exception)

            await self.default_on_error(ctx, exception)

    @staticmethod
    async def default_on_error(ctx: discord.ApplicationContext, exception: Exception):
        exs = traceback.format_exception(exception)  # type: ignore
        await ctx.respond(f'Sorry, an exception occurred.')
        s = ''
        for ex in exs:
            if ex == 'The above exception was the direct cause of the following exception:':
                await ctx.respond(f'```{s}```')
                s = ex
            else:
                s += ex
        await ctx.respond(f'```{s}```')


# the new bot doesnt seem to have a help command, the help command has not been ported over to slash yet i believe
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
