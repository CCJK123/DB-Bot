from __future__ import annotations

import functools
import itertools
import typing
from collections.abc import Awaitable, Callable, Iterable, Sequence

import discord

# Setup what is exported by default
__all__ = ('blank_colour', 'create_embed', 'get_msg_chk', 'get_dm_msg_chk',
           'split_blocks', 'respond_to_interaction', 'make_choices', 'interaction_send', 'max_one')

from discord.ext import commands

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
        embed.set_author(name=user.display_name, icon_url=user.display_avatar.url)
    return embed


def get_msg_chk(interaction: discord.Interaction) -> Callable[[discord.Message], bool]:
    """gets a function used as a check in bot.wait_for such that the author and channel is the same as the context"""

    def msg_chk(m: discord.Message) -> bool:
        return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id

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


T = typing.TypeVar('T')


def make_choices(choices: Iterable[T]) -> list[discord.app_commands.Choice[T]]:
    return [discord.app_commands.Choice(name=c, value=c) for c in choices]


async def interaction_send(
        interaction: discord.Interaction, content: typing.Any | None = None, *,
        embed: discord.Embed = discord.utils.MISSING,
        embeds: Sequence[discord.Embed] = discord.utils.MISSING,
        file: discord.File = discord.utils.MISSING,
        files: Sequence[discord.File] = discord.utils.MISSING,
        view: discord.ui.View = discord.utils.MISSING,
        tts: bool = False,
        ephemeral: bool = False,
        allowed_mentions: discord.AllowedMentions = discord.utils.MISSING,
        suppress_embeds: bool = False
) -> None:
    if interaction.response.is_done():
        await interaction.followup.send(
            content, embed=embed, embeds=embeds, file=file, files=files, view=view, tts=tts,
            ephemeral=ephemeral, allowed_mentions=allowed_mentions, suppress_embeds=suppress_embeds
        )
        return
    await interaction.response.send_message(
        content, embed=embed, embeds=embeds, file=file, files=files, view=view, tts=tts,
        ephemeral=ephemeral, allowed_mentions=allowed_mentions, suppress_embeds=suppress_embeds
    )


# P = typing.ParamSpec('P')
Command = Callable[..., Awaitable[object]]
sen = object()


def max_one(func: Command) -> Command:
    @functools.wraps(func)
    async def inner(a, b=sen, *args, **kwargs) -> object:
        i = a.user.id if isinstance(a, discord.Interaction) else b.user.id  # type: ignore
        if i in inner.using:
            raise commands.MaxConcurrencyReached(1, commands.BucketType.user)
        inner.using.add(i)
        try:
            r = await (func(a, *args, **kwargs) if b is sen else func(a, b, *args, **kwargs))
        finally:
            inner.using.remove(i)
        return r

    inner.using = set()
    return inner  # type: ignore
