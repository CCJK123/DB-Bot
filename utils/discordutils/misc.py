import sys
import traceback
from typing import Callable, Iterable, Mapping

import discord


# Setup what is exported by default
__all__ = ('construct_embed', 'split_blocks', 'get_msg_chk', 'get_dm_msg_chk',
           'default_error_handler')


def construct_embed(fields: Mapping[str, str], /, **kwargs: str) -> discord.Embed:
    """Create embed from dictionary of key-value pairs"""
    embed = discord.Embed(**kwargs)
    for k, v in fields.items():
        embed.add_field(name=k, value=v)
    return embed


def get_msg_chk(ctx: discord.ApplicationContext) -> Callable[[discord.Message], bool]:
    """gets a function used as a check in bot.wait_for such that the author and channel is the same as the context"""
    def msg_chk(m: discord.Message) -> bool:
        return m.author.id == ctx.author.id and m.channel.id == ctx.channel.id

    return msg_chk


def get_dm_msg_chk(auth_id: int) -> Callable[[discord.Message], bool]:
    """gets a function used as a check in bot.wait_for such that it was sent in DMs from the author id given"""
    def msg_chk(m: discord.Message) -> bool:
        return m.author.id == auth_id and m.guild is None

    return msg_chk


def split_blocks(joiner: str, items: Iterable[str], limit: int) -> Iterable[str]:
    """split a message from a string.join into blocks smaller than limit"""
    s = ''
    join_no_sep = True
    for i in items:
        if len(s) + len(joiner) + len(i) > limit:
            yield s
            s = ''
            join_no_sep = True
        if join_no_sep:
            s += i
            join_no_sep = False
        else:
            s += joiner + i

    if s:
        yield s
    return


async def default_error_handler(context: discord.ApplicationContext,
                                exception: discord.ApplicationCommandError) -> None:
    print(f'Ignoring exception in command {context.command}:', file=sys.stderr)
    traceback.print_exception(type(exception), exception, exception.__traceback__, file=sys.stderr)
