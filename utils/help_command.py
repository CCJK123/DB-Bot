from __future__ import annotations

import functools
from typing import Iterable

import discord

__all__ = ('help_command', 'autocomplete')

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
    for command in bot.walk_application_commands():
        if command.qualified_name.lower() == name.lower():
            break
    else:
        await ctx.respond('No command, cog or group by that name found.', ephemeral=True)
        return
    if isinstance(command, discord.SlashCommandGroup):
        embed = discord.Embed(title=command.qualified_name, description=command.description)
        print(command.subcommands)
        for cmd in walk_commands(command.subcommands):
            print(cmd)
            embed.add_field(name=get_command_name(cmd), value=get_command_description(cmd))
        await ctx.respond(embed=embed, ephemeral=True)
        return
    await ctx.respond(embed=discord.Embed(
        title=get_command_name(command),
        description=get_command_description(command)
    ), ephemeral=True)


def create_cog_embed(ctx: discord.ApplicationContext, cog: discord.Cog) -> discord.Embed | None:
    # cog.walk_commands doesn't actually walk down the slash command groups
    embed = discord.Embed(title=cog.qualified_name, description=cog.description)
    for cmd in filter(functools.partial(check_permissions, ctx.author), walk_commands(cog.get_commands())):
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


def check_permissions(user: discord.Member, command: discord.ApplicationCommand):
    if command.parent is not None:
        return check_permissions(user, command.parent)
    if hasattr(command, 'permissions'):
        for perm in command.permissions:
            if perm.type == 1:
                check = any(role.id == perm.id for role in user.roles)
            else:
                check = user.id == perm.id
            if (not check) == perm.permission:
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


@functools.lru_cache(5)
def _autocomplete_options(ctx: discord.AutocompleteContext) -> Iterable[str]:
    # stupid pycord walk things don't fricking work
    for cog in ctx.bot.cogs.values():
        yield from (command.qualified_name for command in walk_commands(cog.get_commands()))


async def autocomplete(ctx: discord.AutocompleteContext):
    return (c for c in _autocomplete_options(ctx) if c.startswith(ctx.value))
