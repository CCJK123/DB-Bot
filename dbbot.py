import os
import random
import aiohttp
from replit.database import AsyncDatabase
from typing import Callable, Mapping

import discord
from discord import commands
from discord.ext import tasks

from utils import discordutils


class DBBot(discord.Bot):
    def __init__(self, db_url: str, on_ready_func: Callable[[], None]):
        intents = discord.Intents(guilds=True, messages=True, members=True)
        super().__init__(command_prefix=os.environ['command_prefix'],
                         help_command=DBHelpCommand(),
                         intents=intents)

        self.on_ready_func = on_ready_func
        self.session = None
        self.database = AsyncDatabase(db_url)
        self.views = discordutils.ViewStorage[discordutils.PersistentView](self, 'views')
        self.prepped = False

    async def prep(self):
        if await self.views.get(None) is None:
            await self.views.set({})
        
        self.session = await aiohttp.ClientSession().__aenter__()
        self.database = await self.database.__aenter__()

        self.change_status.start()
        war_detector_cog = self.get_cog('WarDetectorCog')

    async def cleanup(self):
        await self.session.__aexit__(None, None, None)
        await self.database.__aexit__(None, None, None)

    # Change bot status (background task for 24/7 functionality)
    status = (
        *map(discord.Game, ("with Python", "with repl.it", "with the P&W API")),
        discord.Activity(type=discord.ActivityType.listening, name="Spotify"),
        discord.Activity(type=discord.ActivityType.watching, name="YouTube")
    )

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

        # add views
        for view in await self.views.get_views():
            await self.add_view(view)

        self.on_ready_func()

    async def on_command_error(self, ctx: discord.ApplicationContext, exception):
        command = ctx.command
        if command and command.has_error_handler():
            await ctx.defer()
            return

        await ctx.respond(str(exception))

        ignored = (
            commands.CommandNotFound,
            commands.MissingRole,
            commands.MissingRequiredArgument
        )
        if not isinstance(exception, ignored):
            await super().on_command_error(ctx, exception)


class DBHelpCommand(discord.ext.commands.HelpCommand):
    d_desc = 'No description found'

    async def send_bot_help(self, mapping: Mapping[commands.Cog | None, list[commands.command]]):
        embeds = []
        for k in mapping:
            filtered = await self.filter_commands(mapping[k])
            if filtered:
                embeds.append(self.create_cog_embed(k, filtered))

        await self.get_destination().send(embeds=embeds)

    def create_cog_embed(self, cog: commands.Cog, cmds: list[commands.command]):
        embed = discord.Embed(title=cog.qualified_name,
                              description=cog.description)

        for cmd in cmds:
            embed.add_field(name=cmd.name,
                            value=cmd.description or cmd.short_doc or self.d_desc,
                            inline=False)

        return embed

    async def send_cog_help(self, cog: commands.Cog):
        embed = self.create_cog_embed(cog, await self.filter_commands(cog.get_commands()))
        await self.get_destination().send(embed=embed)

    async def send_group_help(self, group: commands.Group):
        embed = discord.Embed(
            title=self.get_command_signature(group),
            description=group.description
        )
        for cmd in await self.filter_commands(group.commands):
            embed.add_field(name=cmd.name,
                            value=cmd.description or cmd.short_doc or self.d_desc,
                            inline=False)
        await self.get_destination().send(embed=embed)

    async def send_command_help(self, command: commands.command):
        await self.get_destination().send(embed=discord.Embed(
            title=self.get_command_signature(command),
            description=command.description or command.short_doc
        ))
