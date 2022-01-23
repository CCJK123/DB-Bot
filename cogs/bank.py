import asyncio
import datetime
import operator
from typing import Any, Optional

import discord
from discord import commands
from discord.ext import commands as cmds

from utils import financeutils, discordutils, pnwutils, config
from utils.queries import bank_transactions_query, bank_info_query, nation_name_query
import dbbot


class BankCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.balances = discordutils.MappingProperty[str, pnwutils.ResourceDict](self, 'balances')
        self.prices = discordutils.MappingProperty[str, int](self, 'prices')
        self.stocks = discordutils.MappingProperty[str, int](self, 'stocks')
        self.market_open = discordutils.CogProperty[bool](self, 'market.open')

    @property
    def nations(self) -> discordutils.MappingProperty[int, str]:
        return self.bot.get_cog('UtilCog').nations  # type: ignore

    @property
    def loans(self) -> discordutils.MappingProperty[str, dict[str, Any]]:
        return self.bot.get_cog('FinanceCog').loans  # type: ignore

    async def get_transactions(self, entity_id: Optional[str] = None, kind: Optional[pnwutils.TransactionType] = None
                               ) -> list[pnwutils.Transaction]:
        if entity_id is None and kind is not None:
            raise ValueError('Please provide entity id!')

        data = await pnwutils.api.post_query(self.bot.session, bank_transactions_query,
                                             {'alliance_id': config.alliance_id}, 'alliances')

        bank_recs = data['data'][0]['bankrecs']
        if entity_id is None:
            return [pnwutils.Transaction.from_api_dict(rec) for rec in bank_recs]

        transactions = []
        for bank_rec in bank_recs:
            transaction = pnwutils.Transaction.from_api_dict(bank_rec)
            if transaction.entity_id == entity_id and (kind is None or transaction.kind == kind):
                transactions.append(transaction)

        return transactions

    bank = commands.SlashCommandGroup('bank', 'bank related commands!', config.guild_ids)

    @bank.command()
    async def balance(self, ctx: discord.ApplicationContext,
                      private: commands.Option(bool, 'Whether to hide your balance from others', default=True)):
        """Check your balance"""

        await self.balances.initialise()
        nation_id = await self.nations[ctx.author.id].get(None)
        if nation_id is None:
            await ctx.respond('Your nation id has not been set!')
            return

        resources = await self.balances[nation_id].get(None)
        if resources is None:
            resources = pnwutils.Resources()
            await self.balances[nation_id].set({})
        else:
            resources = pnwutils.Resources(**resources)

        loan = await self.loans[nation_id].get(None)

        await ctx.respond(f"{ctx.author.mention}'s Balance",
                          embed=resources.create_balance_embed(ctx.author.name),
                          allowed_mentions=discord.AllowedMentions.none(),
                          ephemeral=private)
        if loan is not None:
            await ctx.respond(
                f'You have a loan due in <t:{int(datetime.datetime.fromisoformat(loan["due_date"]).timestamp())}:R>',
                embed=pnwutils.Resources(**loan['resources']).create_embed(title='Loaned Resources'),
                ephemeral=private)

    @commands.user_command(name='check balance', guild_ids=config.guild_ids, default_permission=False)
    @commands.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def bal_check(self, ctx: discord.ApplicationContext, member: discord.Member):
        """check balance of this member"""
        nation_id = await self.nations[member.id].get(None)
        if nation_id is None:
            await ctx.respond(f'{member.mention} nation id has not been set!',
                              allowed_mentions=discord.AllowedMentions.none(),
                              ephemeral=True)
            return

        resources = await self.balances[nation_id].get(None)
        if resources is None:
            resources = pnwutils.Resources()
            await self.balances[nation_id].set({})
        else:
            resources = pnwutils.Resources(**resources)

        await ctx.respond(
            f"{member.mention}'s Balance",
            embed=resources.create_balance_embed(member.name),
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True
        )

    @bank.command(guild_ids=config.guild_ids)
    @cmds.max_concurrency(1, cmds.BucketType.user)
    async def deposit(self, ctx: discord.ApplicationContext):
        """Deposit resources"""
        nation_id = await self.nations[ctx.author.id].get(None)
        if nation_id is None:
            await ctx.send('Your nation id has not been set!')
            return

        if ctx.guild is not None:
            await ctx.send('Please check your DMs!')
        author = ctx.author
        msg_chk = discordutils.get_dm_msg_chk(author.id)

        start_time = datetime.datetime.now()
        await author.send('You now have 5 minutes to deposit your resources into the bank. '
                          'Once you are done, send a message here.',
                          view=discordutils.LinkView('Deposit Link', pnwutils.link.bank('d', note='Deposit to balance'))
                          )
        try:
            await self.bot.wait_for(
                'message',
                check=msg_chk,
                timeout=300)
        except asyncio.TimeoutError:
            await author.send('You have not responded for 5 minutes! '
                              'Automatically checking for deposits...')

        resources = await self.balances[nation_id].get(None)
        if resources is None:
            resources = pnwutils.Resources()
            await self.balances[nation_id].set({})
        else:
            resources = pnwutils.Resources(**resources)

        dep_transactions = list(filter(lambda t: t.time >= start_time,
                                       await self.get_transactions(nation_id, pnwutils.TransactionType.dep)))
        if dep_transactions:
            for transaction in dep_transactions:
                resources += transaction.resources
            await self.balances[nation_id].set(resources.to_dict())
            await author.send('Your balance is now:', embed=resources.create_balance_embed(author.name))
            return
        await author.send('You did not deposit any resources! Aborting!')

    @bank.command(guild_ids=config.guild_ids)
    @cmds.max_concurrency(1, cmds.BucketType.user)
    async def withdraw(self, ctx: discord.ApplicationContext):
        """Withdraw resources"""
        nation_id = await self.nations[ctx.author.id].get(None)
        if nation_id is None:
            await ctx.respond('Your nation id has not been set!')
            return

        channel = self.bot.get_cog('FinanceCog').send_channel  # type: ignore
        if (channel := await channel.get(None)) is None:
            await ctx.respond('Output channel has not been set! Aborting...')
            return None

        if ctx.guild is None:
            await ctx.respond('Hey!')
        else:
            await ctx.respond('Please check your DMs!')
        author = ctx.author

        resources = await self.balances[nation_id].get(None)

        if resources is None:
            await self.balances[nation_id].set({})
            await author.send('You do not have anything to withdraw! Aborting...')
            return

        resources = pnwutils.Resources(**resources)

        if not resources:
            await author.send('You do not have anything to withdraw! Aborting...')
            return

        res_select_view = financeutils.ResourceSelectView(author.id, resources.keys_nonzero())
        await author.send('What resources do you wish to withdraw?', view=res_select_view)

        msg_chk = discordutils.get_dm_msg_chk(author.id)
        req_resources = pnwutils.Resources()
        try:
            res_names = res_select_view.result()
        except asyncio.TimeoutError:
            await author.send('You took too long to reply! Aborting.')
            return

        for res in await res_names:
            if not resources[res]:
                await author.send(f'You do not have any {res}! Skipping...')
                continue
            await author.send(f'How much {res} do you wish to withdraw?')
            while True:
                try:
                    amt = (await self.bot.wait_for('message', check=msg_chk, timeout=config.timeout)
                           ).content
                except asyncio.TimeoutError:
                    await author.send('You took too long to reply! Aborting.')
                    return

                try:
                    amt = int(amt)
                except ValueError:
                    await author.send("That isn't a number! Please try again.")
                    continue
                if amt <= 0:
                    await author.send('You must withdraw at more than 0 of this resource!')
                    continue
                if amt > resources[res]:
                    await author.send(f'You cannot withdraw that much {res}! You only have {resources[res]} {res}!')
                    continue

                break
            req_resources[res] = amt

        await author.send('Is there a reason for this withdrawal?')
        try:
            reason = (await self.bot.wait_for('message', check=msg_chk, timeout=config.timeout)
                      ).content
        except asyncio.TimeoutError:
            await author.send('You took too long to reply! Aborting.')
            return

        data = await pnwutils.api.post_query(self.bot.session, nation_name_query, {'nation_id': nation_id}, 'nations')
        name = data['data'][0]['nation_name']
        link = pnwutils.link.bank('w', req_resources, name, 'Withdrawal from balance')

        view = financeutils.WithdrawalView('withdrawal_on_sent', link, author.id, req_resources)

        msg = await channel.send(f'Withdrawal Request from {author.mention}',
                                 embed=financeutils.withdrawal_embed(name, nation_id, reason, req_resources),
                                 allowed_mentions=discord.AllowedMentions.none(),
                                 view=view)
        await self.bot.add_view(view, message_id=msg.id)

        res = resources - req_resources
        await self.balances[nation_id].set(res.to_dict())
        await author.send('Your withdrawal request has been sent. '
                          'It will be sent to your nation shortly.')

    @deposit.error
    @withdraw.error
    async def on_error(self, ctx: discord.ApplicationContext,
                       error: discord.ApplicationCommandError) -> None:
        if isinstance(error, cmds.MaxConcurrencyReached):
            await ctx.respond('You are already trying to withdraw/deposit!')
            return

        await discordutils.default_error_handler(ctx, error)

    market = commands.SlashCommandGroup('market',
                                        'A market to buy and sell resources from the bank',
                                        guild_ids=config.guild_ids,
                                        parent=bank,
                                        hidden=True)

    @market.command(name='prices', guild_ids=config.guild_ids, hidden=True)
    async def _prices(self, ctx: discord.ApplicationContext):
        """List out the prices of resources"""
        await ctx.respond(embed=discordutils.construct_embed(await self.prices.get(), title='Bank Trading Prices'))

    @market.command(name='stocks', guild_ids=config.guild_ids)
    async def _stocks(self, ctx: discord.ApplicationContext):
        """List out the stocks of resources"""
        await self.stocks.initialise()
        await ctx.respond(embed=discordutils.construct_embed(await self.stocks.get(), title='Bank Trading Prices'))

    @market.command(guild_ids=config.guild_ids)
    async def buy(self, ctx: discord.ApplicationContext,
                  res_name: commands.Option(str, 'Choose resource to buy', choices=pnwutils.constants.all_res),
                  amt: commands.Option(int, 'How much to buy', min_value=0)):
        """Purchase some amount of a resource for money"""
        if not await self.market_open.get():
            await ctx.respond('The market is currently closed!')
            return

        if await self.stocks[res_name.capitalize()].get() < amt:
            await ctx.respond('The stocks are too low to buy that much!')
            return

        p = await self.prices[res_name.capitalize()].get()
        bal = self.balances[await self.nations[ctx.author.id].get()]
        res = pnwutils.Resources(**await bal.get())
        res.money -= amt * p
        if res.money < 0:
            await ctx.respond('You do not have enough money deposited to do that!')
            return
        res[res_name.lower()] += amt
        await bal.set(res.to_dict())
        await self.stocks[res_name.capitalize()].transform(lambda s: s - amt)
        await ctx.respond('Transaction complete!', embed=res.create_balance_embed(ctx.author.name))
        return

    @market.command(guild_ids=config.guild_ids)
    async def sell(self, ctx: discord.ApplicationContext,
                   res_name: commands.Option(str, 'Choose resource to sell', choices=pnwutils.constants.all_res),
                   amt: commands.Option(int, 'How much to sell', min_value=0)):
        """Sell some amount of a resource to the bank for money"""
        if not await self.market_open.get():
            await ctx.respond('The market is currently closed!')
            return

        prices = await self.prices.get()
        p = prices.get(res_name.capitalize())
        bal = self.balances[await self.nations[ctx.author.id].get()]
        res = pnwutils.Resources(**await bal.get())
        res[res_name.lower()] -= amt
        if res[res_name.lower()] < 0:
            await ctx.respond('You do not have enough money deposited to do that!')
            return
        res.money += amt * p
        await bal.set(res.to_dict())
        await self.stocks[res_name.capitalize()].transform(lambda s: s + amt)
        await ctx.respond('Transaction complete!', embed=res.create_balance_embed(ctx.author.name))
        return

    @market.command(name='set', guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def _set(self, ctx: discord.ApplicationContext,
                   res: commands.Option(str, 'Choose resource to set price', choices=pnwutils.constants.all_res),
                   price: commands.Option(int, 'Resource price', min_value=0)):
        """Set the buying/selling price of a resource"""
        if (await self.prices.get(None)) is None:
            await self.prices.set({})

        if price <= 0:
            await ctx.respond('Price must be positive!')
            return

        if res.lower() in pnwutils.constants.all_res:
            await self.prices[res.capitalize()].set(price)
            await ctx.respond(f'The price of {res} has been set to {price} ppu.')
            return

        await ctx.respond(f"{res} isn't a valid resource!")

    @market.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def open(self, ctx: discord.ApplicationContext):
        """Open or close the market"""
        await self.market_open.transform(operator.not_)
        s = 'open' if await self.market_open.get() else 'closed'
        await ctx.respond(f'The market is now {s}!')

    loan = commands.SlashCommandGroup('loan', 'Commands related to loans',
                                      guild_ids=config.guild_ids,
                                      parent=bank)

    @loan.command(name='return', guild_ids=config.guild_ids)
    async def _return(self, ctx: discord.ApplicationContext):
        """Return your loan from your balance, if any"""
        nation_id = await self.nations[ctx.author.id].get()
        loan = await self.loans[nation_id].get(None)
        if loan is None:
            await ctx.respond("You don't have an active loan!")
            return
        loan = financeutils.LoanData(**loan)
        bal = self.balances[nation_id]
        res = pnwutils.Resources(**await bal.get())
        res -= loan.resources
        if res.all_positive():
            await bal.set(res.to_dict())
            await self.loans[nation_id].delete()
            await ctx.respond('Your loan has been successfully repaid!')
            return
        await ctx.respond('You do not have enough resources to repay your loan.')

    @loan.command(guild_ids=config.guild_ids)
    async def status(self, ctx: discord.ApplicationContext):
        """Check the current status of your loan, if any"""
        loan = await self.loans[await self.nations[ctx.author.id].get()].get(None)
        if loan is None:
            await ctx.respond("You don't have an active loan!")
            return
        await ctx.respond(embed=financeutils.LoanData(**loan).to_embed())

    @loan.command(name='list', guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def loan_list(self, ctx: discord.ApplicationContext):
        loans = await self.loans.get()
        await ctx.respond('\n'.join(
            f'Loan of [{pnwutils.Resources(**loan["resources"])}] due on {loan["due_date"]}'
            for n, loan in loans.items()) or 'There are no active loans!')

    @commands.user_command(name='bank adjust', guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def adjust(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Manually adjust the resource values of someone's balance"""
        nation_id = await self.nations[member.id].get(None)
        if nation_id is None:
            await ctx.respond(f"{member.mention}'s nation id has not been set!",
                              allowed_mentions=discord.AllowedMentions.none())
            return
        await ctx.respond('Please check your DMs!')
        author = ctx.author
        res_select_view = financeutils.ResourceSelectView(author.id)
        msg_chk = discordutils.get_dm_msg_chk(author.id)
        await author.send('What resources would you like to adjust?', view=res_select_view)

        resources = await self.balances[nation_id].get(None)
        if resources is None:
            resources = pnwutils.Resources()
            await self.balances[nation_id].set({})
        else:
            resources = pnwutils.Resources(**resources)

        for res in await res_select_view.result():
            await author.send(f'How much would you like to adjust {res} by?')
            while True:
                try:
                    amt = (await self.bot.wait_for('message', check=msg_chk, timeout=config.timeout)
                           ).content
                except asyncio.TimeoutError:
                    await author.send('You took too long to reply! Aborting.')
                    return

                try:
                    amt = int(amt)
                except ValueError:
                    await author.send("That isn't a number! Please try again.")
                    continue
                break
            resources[res] += amt

        await self.balances[nation_id].set(resources.to_dict())
        await author.send(f'The balance of {member.mention} has been modified!',
                          embed=resources.create_balance_embed(member.name),
                          allowed_mentions=discord.AllowedMentions.none())

    @commands.user_command(name='bank set', guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def set(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Manually set the resource values of someone's balance"""
        nation_id = await self.nations[member.id].get(None)
        if nation_id is None:
            await ctx.respond(f"{member.mention}'s nation id has not been set!",
                              allowed_mentions=discord.AllowedMentions.none())
            return
        await ctx.respond('Please check your DMs!')

        author = ctx.author
        res_select_view = financeutils.ResourceSelectView(author.id)
        msg_chk = discordutils.get_dm_msg_chk(author.id)
        await author.send('What resources would you like to set?', view=res_select_view)

        resources = await self.balances[nation_id].get(None)
        if resources is None:
            resources = pnwutils.Resources()
            await self.balances[nation_id].set({})
        else:
            resources = pnwutils.Resources(**resources)

        for res in await res_select_view.result():
            await ctx.send(f'What would you like to set {res} to?')
            while True:
                try:
                    amt = (await self.bot.wait_for('message', check=msg_chk, timeout=config.timeout)
                           ).content
                except asyncio.TimeoutError:
                    await author.send('You took too long to reply! Aborting.')
                    return
                try:
                    amt = int(amt)
                except ValueError:
                    await author.send("That isn't a number! Please try again.")
                    continue
                break
            resources[res] = amt

        await self.balances[nation_id].set(resources.to_dict())
        await author.send(f'The balance of {member.mention} has been modified!',
                          embed=resources.create_balance_embed(member.name),
                          allowed_mentions=discord.AllowedMentions.none())

    @bank.command(name='contents', guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def bank_contents(self, ctx: discord.ApplicationContext):
        """Check the contents of the bank"""
        data = await pnwutils.api.post_query(
            self.bot.session, bank_info_query,
            {'alliance_id': config.alliance_id},
            'alliances'
        )
        resources = pnwutils.Resources(**data['data'].pop())
        await ctx.respond(embed=resources.create_embed(), ephemeral=True)

    @commands.command(guild_ids=config.guild_ids, default_permission=False)
    @commands.permissions.has_role(config.gov_role_id, guild_id=config.guild_id)
    async def offshore(self, ctx: discord.ApplicationContext):
        await ctx.respond('not implemented')


def setup(bot: dbbot.DBBot):
    bot.add_cog(BankCog(bot))

    @financeutils.WithdrawalView.register_callback('withdrawal_on_sent')
    async def on_sent(requester_id: int, req_res: pnwutils.Resources):
        await bot.get_user(requester_id).send(
            'Your withdrawal request has been sent to your nation!',
            embed=req_res.create_embed(title='Withdrawn Resources'))
