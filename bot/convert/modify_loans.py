import asyncio
import datetime

import aiofiles

from bot.utils import databases, config, pnwutils


async def main():
    async with aiofiles.open('dict.txt') as f:
        data = await f.read()
    db = databases.PGDatabase(config.database_url)
    d = eval(data)
    loans = d['cogs.finance.loans']
    tasks = []

    async with db:
        await db.execute('DELETE FROM loans')
        for d_id, loan in loans.items():
            d_id = int(d_id)
            if d_id in (826281787948138496, 759557583933145129):
                continue
            tasks.append(asyncio.create_task(db.execute(
                f'INSERT INTO loans(discord_id, due_date, loaned) VALUES ($1, $2, '
                f'{pnwutils.Resources(**loan["resources"]).to_row()})',
                d_id, datetime.datetime.fromisoformat(loan['due_date']))))
        await asyncio.gather(*tasks)
        print('done')


if __name__ == '__main__':
    asyncio.run(main())
