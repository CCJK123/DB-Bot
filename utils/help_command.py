import discord
from discord import commands

from utils import config

ApplicationCommandList = list[discord.ApplicationCommand]


async def help_command(bot: discord.Bot, ctx: discord.ApplicationContext, name: str | None):
    if name is None:
        embeds = []
        for cog_name, cog in bot.cogs.items():
            filtered = await filter_commands(ctx, cog.get_commands())
            if filtered:
                embeds.append(create_cog_embed(cog, filtered))
        await ctx.respond(embeds=embeds)
        return
    cog = bot.get_cog(name)
    if cog is not None:
        filtered = await filter_commands(ctx, cog.get_commands())
        if filtered:
            await ctx.respond(embed=create_cog_embed(cog, filtered))
        else:
            await ctx.respond('There is no cog by that name!')
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
        for cmd in group.subcommands:
            embed.add_field(name=get_command_name(cmd), value=get_command_description(cmd))
        await ctx.respond(embed=embed)
        return
    await ctx.respond('No command, cog or group by that name found.')


async def filter_commands(ctx: discord.ApplicationContext,
                          command_list: ApplicationCommandList) -> ApplicationCommandList:
    new_list = []
    for cmd in command_list:
        if hasattr(cmd, 'permissions'):
            perm: commands.CommandPermission
            for perm in cmd.permissions:
                if perm.type == 1:
                    check = any(role.id == perm.id for role in ctx.author.roles)
                else:
                    check = ctx.author.id == perm.id
                if not (not check) ^ perm.permission:
                    break
            else:
                new_list.append(cmd)
        else:
            new_list.append(cmd)
    return new_list


def create_cog_embed(cog: discord.Cog, cog_commands: ApplicationCommandList) -> discord.Embed:
    embed = discord.Embed(title=cog.qualified_name,
                          description=cog.description)
    for cmd in cog_commands:
        embed.add_field(name=get_command_name(cmd),
                        value=get_command_description(cmd),
                        inline=False)

        return embed


def get_command_name(command: discord.ApplicationCommand) -> str:
    if isinstance(command, discord.UserCommand):
        return f'user command - {command.name}'
    elif isinstance(command, discord.MessageCommand):
        return f'message command - {command.name}'
    return command.name


def get_command_description(command: discord.ApplicationCommand) -> str:
    default = 'No description found'
    if isinstance(command, (discord.UserCommand, discord.MessageCommand)):
        return command.callback.__doc__ or default
    elif isinstance(command, discord.SlashCommandGroup):
        strings = []
        for cmd in command.subcommands:
            strings.append(f'- {get_command_name(cmd)}')
            strings.append(f'\t{get_command_description(cmd)}')
        return ('\n\t' + '\t' * get_nested_level(command)).join(strings) or default
    assert isinstance(command, discord.SlashCommand)
    return command.description or default


def get_nested_level(command: discord.ApplicationCommand) -> int:
    nested = 0
    while command.parent is not None and hasattr(command.parent, "name"):
        command = command.parent
        nested += 1
    return nested
