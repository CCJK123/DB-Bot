# use to convert the loans and balances index to discord id rather than nation id
import asyncio

from replit.database import AsyncDatabase
from replit import db


async def main():
    database = AsyncDatabase(db.db_url)
    async with database:
        nations = await database.get('cogs.util.nations')
        loans = await database.get('cogs.finance.loans')
        balances = await database.get('cogs.bank.balances')
        print(nations, loans, balances)
        if not set(nations.values()) <= (set(loans.keys()) | set(balances.keys())):
            raise ValueError('Some nation ids in loans or balances arent recorded in nations!')
        new_loans = {}
        new_balances = {}
        for d_id, n_id in nations.items():
            if loan_val := loans.get(n_id):
                new_loans[d_id] = loan_val
            if bal_val := balances.get(n_id):
                new_balances[d_id] = bal_val

        await database.set('cogs.finance.loans', new_loans)
        await database.set('cogs.bank.balances', new_balances)

if __name__ == '__main__':
    asyncio.run(main())
