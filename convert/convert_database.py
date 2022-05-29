# use to convert the dict to the file database
import asyncio

import aiofiles

from utils import databases


async def main():
    async with aiofiles.open('dict.txt') as f:
        data = await f.read()
    databases.Database()
    new_db.data = dict(data)
    await new_db.save()
    print('done')

if __name__ == '__main__':
    asyncio.run(main())
