from ...utils import dbbot
from .finance_cog import FinanceCog
from .bank_cog import BankCog


async def setup(bot: dbbot.DBBot) -> None:
    await bot.add_cog(FinanceCog(bot))
    await bot.add_cog(BankCog(bot))
