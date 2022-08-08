from __future__ import annotations

import itertools
from typing import Callable, Iterable

import discord

# Setup what is exported by default
__all__ = ('blank_colour', 'create_embed', 'get_msg_chk', 'get_dm_msg_chk',
           'split_blocks', 'respond_to_interaction')


blank_colour = 3092790


def create_embed(names: Iterable[str] = (), values: Iterable[str] = (), /,
                 user: discord.User | discord.Member | None = None,
                 **kwargs: str | int) -> discord.Embed:
    """Create an embed from iterables of name, value pairs"""
    kwargs.setdefault('colour', blank_colour)
    embed = discord.Embed(**kwargs)
    for k, v in zip(names, values):
        embed.add_field(name=k, value=v)
    if user is not None:
        embed.set_author(name=user.name, icon_url=user.avatar.url)
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


def split_blocks(joiner: str, *iterables: Iterable[str], limit: int = 2000) -> Iterable[str]:
    """split a message from a string, join into blocks smaller than limit"""
    s = ''
    join_no_sep = True
    for i in itertools.chain.from_iterable(iterables):
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


async def respond_to_interaction(interaction: discord.Interaction) -> None:
    """Responds to the given interaction without any changes."""

    # intentionally send empty message, responding to the interaction but doing nothing
    try:
        await interaction.response.send_message('')
    except discord.HTTPException:
        pass
    else:
        raise AssertionError('HTTPException Not Raised!')

