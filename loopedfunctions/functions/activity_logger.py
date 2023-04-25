import pathlib
from datetime import datetime
from typing import Iterable

import aiohttp
import aiofiles

from . import constants


class ActivityLogger:
    def __init__(self, session: aiohttp.ClientSession, settings: dict) -> None:
        self.path = pathlib.Path(settings['log_path'])
        self.key = settings['api_key']
        self.session = session
        self.path.mkdir(exist_ok=True)

    async def run_once(self, now: datetime):
        async with self.session.get(f'{constants.api_base_url}nations/{self.key}/&v_mode=0&min_score=1000') as resp:
            data = await resp.json()
        if data['api_request']['success']:
            await self.store((self.stored_string(nation) for nation in data['data']), now)
            print('Data recorded!')
        else:
            print(f'Error while getting data: {data["general_message"]}')

    async def store(self, nations: Iterable[str], now: datetime) -> None:
        async with aiofiles.open(self.path / (now.isoformat(sep=' ').replace(':', '-') + '.csv'), 'w') as file:
            await file.write('\n'.join(nations))

    @staticmethod
    def stored_string(nation: dict):
        return f"{nation['nation_id']},{nation['score']},{nation['war_policy']},{nation['last_active']}"
