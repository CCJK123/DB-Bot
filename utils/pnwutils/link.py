from __future__ import annotations

from typing import Literal, Iterable

from . import constants
from .data_classes import Resources
from .. import config


def nation(nation_id: str | int) -> str:
    """Creates link to a nation given its ID."""
    return f'{constants.base_url}nation/id={nation_id}'


def alliance(alliance_id: str | int | None = None) -> str:
    """Creates link to an alliance given its ID."""
    if alliance_id is None:
        alliance_id = config.alliance_id
    return f'{constants.base_url}alliance/id={alliance_id}'


def bank(kind: Literal['w', 'd', 'wa'], res: Resources | None = None,
         recipient: str | None = None, note: str | None = None) -> str:
    """Creates a link to the bank page of our alliance."""
    if kind == 'd' and recipient is not None:
        raise ValueError('Do not provide recipient for deposits!')

    # Add parameters to withdrawal / deposit url
    link = f'{alliance()}&display=bank'
    if note is not None:
        link += f'&{kind[0]}_note={note.replace(" ", "%20")}'
    if kind == 'wa':
        link += '&w_type=alliance'
    if recipient is not None:
        # Replace spaces with url encoding for spaces
        link += f'&w_recipient={recipient.replace(" ", "%20")}'
    if res is not None:
        for res_name, res_amt in res:
            link += f'&{kind[0]}_{res_name}={res_amt}'
    return link


def bank_split_link(kind: Literal['w', 'd', 'wa'], res: Resources | None = None,
                    recipient: str | None = None, note: str | None = None) -> Iterable[str]:
    """Like `bank`, but outputs multiple links if the link would be too long and cause P&W to error"""
    link_base = bank(kind, recipient=recipient, note=note)
    link = link_base
    for res_name, res_amt in res:
        # 291 is the limit, 291 = len('https://politicsandwar.com/alliance/') + 255
        if len(link) + 3 + len(res_name) + len(str(res_amt)) > 291:
            yield link
            link = link_base
        link += f'&{kind[0]}_{res_name}={res_amt}'
    yield link


def war(war_id: str | int) -> str:
    """Creates a link to a war given its ID."""
    return f'{constants.base_url}nation/war/timeline/war={war_id}'
