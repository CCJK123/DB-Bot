# use to convert the replit db to a file
import asyncio

from replit.database import AsyncDatabase
from replit import db
from database import RudimentaryDatabase


async def main():
    database = AsyncDatabase(db.db_url)
    new_db = RudimentaryDatabase('data')
    async with database:
        new_db.data = await database.to_dict()
    await new_db.save()

if __name__ == '__main__':
    asyncio.run(main())
