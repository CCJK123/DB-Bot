import asyncio
from datetime import datetime, timedelta
import pathlib

import aiohttp
import aiofiles

BASEURL = "https://politicsandwar.com/api/"
API_KEY = ""  # put api key here!


class Record:
    def __init__(self, path: pathlib.Path, minutes: int) -> None:
        self.path = path
        path.mkdir(exist_ok=True)
        self.minutes = minutes
        self.step = timedelta(minutes=minutes)
        self.next = datetime.now().replace(second=0, microsecond=0) + self.step

    async def run(self) -> None:
        while True:
            await asyncio.sleep((self.next - datetime.now()).total_seconds())
            await self.record_activity(self.next)
            self.next += self.step

    async def record_activity(self, now: datetime):
        async with aiohttp.ClientSession() as session:
            async with session.get(BASEURL + f'nations/?key={API_KEY}&vm=false') as resp:
                data = await resp.json()
            if data['success']:
                online = [f"{nation['nationid']}|{nation['score']}|{nation['war_policy']}" for nation in data['nations']
                          if nation['minutessinceactive'] <= self.minutes]
                await self.store(online, now)
                print('Data recorded!')
            else:
                print(f'Error while getting data: {data["general_message"]}')

    async def store(self, nations: list[str], now: datetime) -> None:
        async with aiofiles.open(self.path / now.isoformat(sep=' ').replace(':', '-'), 'w') as file:
            await file.write(','.join(nations))


asyncio.run(Record(pathlib.Path('logs'), 1).run())
