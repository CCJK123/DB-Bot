import functools
from typing import Iterable

import discord
from discord import commands

from utils import config

ApplicationCommandList = list[discord.ApplicationCommand]


async def help_command(bot: discord.Bot, ctx: discord.ApplicationContext, name: str | None):
    if name is None:
        embeds = filter(None, (create_cog_embed(ctx, cog) for cog in bot.cogs.values()))
        await ctx.respond(embeds=tuple(embeds), ephemeral=True)
        return
    cog = bot.get_cog(name)
    if cog is not None:
        embed = create_cog_embed(ctx, cog)
        if embed:
            await ctx.respond(embed=embed, ephemeral=True)
        else:
            await ctx.respond('No command, cog or group by that name found.', ephemeral=True)
        return
    # command
    for cmd_type in discord.SlashCommand, discord.UserCommand, discord.MessageCommand:
        cmd = bot.get_application_command(name, config.guild_ids, cmd_type)
        if cmd is not None:
            break

    if cmd is not None:
        await ctx.respond(embed=discord.Embed(
            title=get_command_name(cmd),
            description=get_command_description(cmd)
        ), ephemeral=True)
        return
    group = bot.get_application_command(name, config.guild_ids, discord.SlashCommandGroup)
    if group is not None:
        embed = discord.Embed(title=group.qualified_name, description=group.description)
        for cmd in group.walk_commands():
            embed.add_field(name=get_command_name(cmd), value=get_command_description(cmd))
        await ctx.respond(embed=embed, ephemeral=True)
        return
    await ctx.respond('No command, cog or group by that name found.', ephemeral=True)


def create_cog_embed(ctx: discord.ApplicationContext, cog: discord.Cog) -> discord.Embed | None:
    # cog.walk_commands doesn't actually walk down the slashcommandgroups
    filtered = filter(functools.partial(check_permissions, ctx), walk_commands(cog.get_commands()))
    embed = discord.Embed(title=cog.qualified_name, description=cog.description)
    for cmd in filtered:
        embed.add_field(name=get_command_name(cmd),
                        value=get_command_description(cmd),
                        inline=False)
    return embed if embed.fields else None


def walk_commands(cmds: Iterable[discord.ApplicationCommand]
                 ) -> Iterable[discord.ApplicationCommand]:
    for command in cmds:
        yield command
        if isinstance(command, discord.SlashCommandGroup):
            yield from walk_commands(command.subcommands)


def check_permissions(ctx: discord.ApplicationContext, command: discord.ApplicationCommand):
    if command.parent is not None:
        return check_permissions(ctx, command.parent)
    if hasattr(command, 'permissions'):
        perm: commands.CommandPermission
        for perm in command.permissions:
            if perm.type == 1:
                check = any(role.id == perm.id for role in ctx.author.roles)
            else:
                check = ctx.author.id == perm.id
            if not (not check) ^ perm.permission:
                return False
    return True


def get_command_name(command: discord.ApplicationCommand) -> str:
    if isinstance(command, discord.UserCommand):
        return f'{command.qualified_name} (User Command)'
    elif isinstance(command, discord.MessageCommand):
        return f'{command.qualified_name} (Message Command)'
    elif isinstance(command, discord.SlashCommandGroup):
        return f'{command.qualified_name} (Group)'
    return command.qualified_name


def get_command_description(command: discord.ApplicationCommand) -> str:
    default = 'No description found'
    if isinstance(command, (discord.UserCommand, discord.MessageCommand)):
        return command.callback.__doc__ or default
    return command.description or default
