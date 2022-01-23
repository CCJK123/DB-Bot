import asyncio
from datetime import datetime, timedelta, timezone as tz
import pathlib
from typing import Iterable

import aiohttp
import aiofiles

BASEURL = "https://politicsandwar.com/api/v2/"
API_KEY = ""  # put api key here!


class Recorder:
    def __init__(self, path: pathlib.Path, minutes: int) -> None:
        self.path = path
        path.mkdir(exist_ok=True)
        self.step = timedelta(minutes=minutes)
        self.next = datetime.now(tz=tz.utc).replace(second=0, microsecond=0) + self.step

    async def run(self) -> None:
        await self.record_activity(self.next)
        while True:
            await asyncio.sleep((self.next - datetime.now(tz=tz.utc)).total_seconds())
            await self.record_activity(self.next)
            self.next += self.step

    async def record_activity(self, now: datetime):
        async with aiohttp.ClientSession() as session:
            async with session.get(f'{BASEURL}nations/{API_KEY}/&v_mode=0&min_score=1000') as resp:
                data = await resp.json()
            if data['api_request']['success']:
                for nation in data['data']:
                    if nation['nation_id'] == 85999:
                        print(datetime.fromisoformat(nation['last_active']) + self.step, now)
                nations = (f"{nation['nation_id']},{nation['score']},{nation['war_policy']},{nation['last_active']}"
                           for nation in data['data'])
                await self.store(nations, now)
                print('Data recorded!')
            else:
                print(f'Error while getting data: {data["general_message"]}')

    async def store(self, nations: Iterable[str], now: datetime) -> None:
        async with aiofiles.open(self.path / (now.isoformat(sep=' ').replace(':', '-') + '.csv'), 'w') as file:
            await file.write('\n'.join(nations))


if __name__ == '__main__':
    asyncio.run(Recorder(pathlib.Path('logs'), 1).run())
