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


def war(war_id: str) -> str:
    return f'{constants.base_url}nation/war/timeline/war={war_id}'
