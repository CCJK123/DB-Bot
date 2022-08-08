# use to convert the dict to the psql database
import asyncio

import aiofiles

from utils import databases, config, pnwutils


async def main():
    async with aiofiles.open('dict.txt') as f:
        data = await f.read()
    db = databases.PGDatabase(config.database_url)
    d = eval(data)
    nations = d['cogs.util.nations']
    balances = d['cogs.bank.balances']
    tasks = []
    async with db:
        for d_id, n_id in nations.items():
            if bal := balances.get(d_id):
                res = pnwutils.Resources(**bal)
                tasks.append(asyncio.create_task(db.execute(
                    f'INSERT INTO users(discord_id, nation_id, balance) VALUES ($1, $2, {res.to_row()}) '
                    f'ON CONFLICT (discord_id) DO UPDATE SET nation_id = $2, balance = {res.to_row()}',
                    int(d_id), int(n_id))))
        await asyncio.gather(*tasks)
        print('done')

if __name__ == '__main__':
    asyncio.run(main())
