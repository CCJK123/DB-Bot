import functools

import discord
from discord import commands

from utils import config

ApplicationCommandList = list[discord.ApplicationCommand]


async def help_command(bot: discord.Bot, ctx: discord.ApplicationContext, name: str | None):
    if name is None:
        embeds = filter(None, (create_cog_embed(ctx, cog) for cog in bot.cogs.values()))
        await ctx.respond(embeds=tuple(embeds))
        return
    cog = bot.get_cog(name)
    if cog is not None:
        embed = create_cog_embed(ctx, cog)
        if embed:
            await ctx.respond(embed=embed)
        else:
            await ctx.respond('No command, cog or group by that name found.')
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
        ))
        return
    group = bot.get_application_command(name, config.guild_ids, discord.SlashCommandGroup)
    if group is not None:
        embed = discord.Embed(title=group.qualified_name, description=group.description)
        for cmd in group.walk_commands():
            embed.add_field(name=get_command_name(cmd), value=get_command_description(cmd))
        await ctx.respond(embed=embed)
        return
    await ctx.respond('No command, cog or group by that name found.')


def create_cog_embed(ctx: discord.ApplicationContext, cog: discord.Cog) -> discord.Embed | None:
    filtered = filter(functools.partial(check_permissions, ctx), cog.walk_commands())

    embed = discord.Embed(title=cog.qualified_name, description=cog.description)
    for cmd in filtered:
        embed.add_field(name=get_command_name(cmd),
                        value=get_command_description(cmd),
                        inline=False)
    return embed if embed.fields else None


def check_permissions(ctx: discord.ApplicationContext, command: discord.ApplicationCommand):
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
        return f'{command.qualified_name} (user command)'
    elif isinstance(command, discord.MessageCommand):
        return f'{command.qualified_name} (message command)'
    return command.qualified_name


def get_command_description(command: discord.ApplicationCommand) -> str:
    default = 'No description found'
    if isinstance(command, (discord.UserCommand, discord.MessageCommand)):
        return command.callback.__doc__ or default
    return command.description or default
