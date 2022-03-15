# use to convert the replit db to a dict
import asyncio

from replit.database import AsyncDatabase
from replit import db


async def main():
    database = AsyncDatabase(db.db_url)
    async with database:
        with open('dict.txt', 'w') as f:
            f.write(str(await database.to_dict()))
    print('done')

if __name__ == '__main__':
    asyncio.run(main())