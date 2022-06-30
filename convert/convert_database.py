# use to convert the dict to the file database
import asyncio

import aiofiles

from utils import databases, config, pnwutils


async def main():
    async with aiofiles.open('dict.txt') as f:
        data = await f.read()
    db = databases.PGDatabase(config.database_url)
    d = dict(data)
    nations = d['cogs.util.nations']
    balances = d['cogs.bank.balances']
    tasks = []
    for d_id, n_id in nations.items():
        res = pnwutils.Resources(**balances[d_id])
        tasks.append(asyncio.create_task(db.execute(
            f'INSERT INTO users(discord_id, nation_id, balances) VALUES ($1, $2, {res.to_row()})', d_id, n_id)))
    await asyncio.gather(*tasks)
    print('done')

if __name__ == '__main__':
    asyncio.run(main())
