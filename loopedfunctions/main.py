import asyncio
import json
from datetime import datetime, timedelta, timezone

import aiofiles
import aiohttp

from functions import ActivityLogger, Recruiter, types


async def main(filepath: str):
    async with aiohttp.ClientSession() as session:
        async with aiofiles.open(filepath, 'r') as f:
            settings: types.SettingsDict = json.loads(await f.read())

        recruiter = Recruiter(session, settings)
        activity_logger = ActivityLogger(session, settings)
        await recruiter.login()
        step = timedelta(minutes=settings['frequency'])
        next_time = datetime.now(tz=timezone.utc).replace(second=0, microsecond=0) + step

        # infinite loop
        while True:
            await asyncio.sleep((next_time - datetime.now(tz=timezone.utc)).total_seconds())
            await activity_logger.run_once(next_time)
            await recruiter.run_once(next_time)
            next_time += step


if __name__ == '__main__':
    asyncio.run(main('settings.json'))
