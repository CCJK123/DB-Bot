from typing import Literal

from . import constants
from .data_classes import Resources
from .. import config


def nation(nation_id: str) -> str:
    return f'{constants.base_url}nation/id={nation_id}'


def alliance(alliance_id: str | None = None) -> str:
    if alliance_id is None:
        alliance_id = config.alliance_id
    return f'{constants.base_url}alliance/id={alliance_id}'


def bank(kind: Literal['w', 'd', 'wa'], res: Resources | None = None,
         recipient: str | None = None, note: str | None = None) -> str:
    if kind == 'd' and recipient is not None:
        raise ValueError('Do not provide recipient for deposits!')

    # Check if withdrawing to alliance
    with_aa = False
    if kind == 'wa':
        with_aa = True
        kind = 'w'

    # Add parameters to withdrawal / deposit url
    link = f'{alliance()}&display=bank'
    if res is not None:
        for res_name, res_amt in res:
            link += f'&{kind}_{res_name}={res_amt}'
    if note is not None:
        link += f'&{kind}_note={note.replace(" ", "%20")}'
    if with_aa:
        link += '&w_type=alliance'
    if recipient is not None:
        # Replace spaces with url encoding for spaces
        link += f'&w_recipient={recipient.replace(" ", "%20")}'
    return link


def war(war_id: str) -> str:
    return f'{constants.base_url}nation/war/timeline/war={war_id}'
