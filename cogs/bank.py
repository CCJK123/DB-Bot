import asyncio
import datetime
import operator
from typing import Any, Optional, Union

from discord.ext import commands
import discord

from utils import financeutils, discordutils, pnwutils
import dbbot


class BankCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.balances = discordutils.MappingProperty[str, pnwutils.ResourceDict](self, 'balances')
        self.prices = discordutils.SavedProperty[dict[str, int]](self, 'prices')
        self.market_open = discordutils.SavedProperty[bool](self, 'market.open')

    @property
    def nations(self) -> discordutils.MappingProperty[int, str]:
        return self.bot.get_cog('UtilCog').nations  # type: ignore

    @property
    def loans(self) -> discordutils.MappingProperty[int, dict[str, Any]]:
        return self.bot.get_cog('FinanceCog').loans  # type: ignore

    async def get_transactions(self, entity_id: Optional[str] = None, kind: Optional[pnwutils.TransactionType] = None
                               ) -> list[pnwutils.Transaction]:
        if entity_id is None and kind is not None:
            raise ValueError('Please provide entity id!')

        transactions_query_str = '''
        query bank_transactions($alliance_id: [Int]) {
          alliances(id: $alliance_id, first: 1) {
            data {
              bankrecs {
                # id
                sid
                stype
                rid
                rtype
                # pid
                date
                money
                coal
                oil
                uranium
                iron
                bauxite
                lead
                gasoline
                munitions
                steel
                aluminum
                food
              }
            }
          }
        }
        '''
        # some notes on the format of this data
        # id: unique id of this transaction
        # sid: id of the sender
        # stype: type of the sender
        #  - 1: nation
        #  - 2: alliance
        # rid: id of the receiver
        # rtype: type of receiver
        #  numbers mean the same as in stype
        # pid: id of the banker (the person who initiated this transaction)
        # note that if stype is 1 then rtype is 2 and if rtype is 1 then stype is 2
        # but converse is not true due to the existence of inter-alliance transactions
        # if stype/rtype is 2 then sid/rid is definitely the alliance id unless both stype/rtype is 2

        data = await pnwutils.API.post_query(self.bot.session, transactions_query_str,
                                             {'alliance_id': pnwutils.Config.aa_id}, 'alliances')

        bank_recs = data['data'][0]['bankrecs']
        if entity_id is None:
            return [pnwutils.Transaction.from_api_dict(rec) for rec in bank_recs]

        transactions = []
        for bank_rec in bank_recs:
            transaction = pnwutils.Transaction.from_api_dict(bank_rec)
            if transaction.entity_id == entity_id and (kind is None or transaction.kind == kind):
                transactions.append(transaction)

        return transactions

    @commands.group(invoke_without_command=True)
    async def bank(self, ctx: commands.Context):
        await ctx.send_help(self.bank)

    @bank.group(invoke_without_command=True, aliases=('bal',))
    async def balance(self, ctx: commands.Context):
        """Check your balance"""
        
        await self.balances.initialise()
        nation_id = await self.nations[ctx.author.id].get(None)
        if nation_id is None:
            await ctx.send('Your nation id has not been set!')
            return

        resources = await self.balances[nation_id].get(None)
        if resources is None:
            resources = pnwutils.Resources()
            await self.balances[nation_id].set({})
        else:
            resources = pnwutils.Resources(**resources)

        loan = await self.loans[nation_id].get(None)

        await ctx.send(f"{ctx.author.mention}'s Balance",
                       embed=resources.create_balance_embed(ctx.author.name),
                       allowed_mentions=discord.AllowedMentions.none())
        if loan is not None:
            print(loan)
            await ctx.send(
                f'You have a loan due in <t:{int(datetime.datetime.fromisoformat(loan["due_date"]).timestamp())}:R>',
                embed=pnwutils.Resources(**loan['resources']).create_embed(title='Loaned Resources'))

    @discordutils.gov_check
    @balance.command()
    async def check(self, ctx: commands.Context, member: discord.Member = None):
        if member is None:
            member = await discordutils.get_member_from_context(ctx)
        
        nation_id = await self.nations[member.id].get(None)
        if nation_id is None:
            await ctx.send(f'{member.mention} nation id has not been set!',
                           allowed_mentions=discord.AllowedMentions.none())
            return

        resources = await self.balances[nation_id].get(None)
        if resources is None:
            resources = pnwutils.Resources()
            await self.balances[nation_id].set({})
        else:
            resources = pnwutils.Resources(**resources)

        await ctx.send(
            f"{member.mention}'s Balance",
            embed=resources.create_balance_embed(member.name),
            allowed_mentions=discord.AllowedMentions.none()
        )

    @bank.command(aliases=('dep',))
    @commands.max_concurrency(1, commands.BucketType.user)
    async def deposit(self, ctx: commands.Context):
        """Deposit resources"""
        nation_id = await self.nations[ctx.author.id].get(None)
        if nation_id is None:
            await ctx.send('Your nation id has not been set!')
            return

        if ctx.guild is not None:
            await ctx.send('Please check your DMs!')
        auth = ctx.author
        msg_chk = discordutils.get_dm_msg_chk(auth.id)

        start_time = datetime.datetime.now()
        await auth.send('You now have 5 minutes to deposit your resources into the bank. '
                        'Once you are done, send a message here.',
                        view=discordutils.LinkView('Deposit Link', pnwutils.Link.bank('d', note='Deposit to balance'))
                        )
        try:
            await self.bot.wait_for(
                'message',
                check=msg_chk,
                timeout=300)
        except asyncio.TimeoutError:
            await auth.send('You have not responded om 5 minutes! '
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
            await auth.send('Your balance is now:', embed=resources.create_balance_embed(auth.name))
            return
        await auth.send('You did not deposit any resources! Aborting!')

    @bank.command(aliases=('with',))
    @commands.max_concurrency(1, commands.BucketType.user)
    async def withdraw(self, ctx: commands.Context):
        """Withdraw resources"""
        nation_id = await self.nations[ctx.author.id].get(None)
        if nation_id is None:
            await ctx.send('Your nation id has not been set!')
            return

        channel = self.bot.get_cog('FinanceCog').send_channel  # type: ignore
        if (channel := await channel.get(None)) is None:
            await ctx.send('Output channel has not been set! Aborting.')
            return None

        if ctx.guild is not None:
            await ctx.send('Please check your DMs!')
        auth = ctx.author

        resources = await self.balances[nation_id].get(None)

        if resources is None:
            resources = pnwutils.Resources()
            await self.balances[nation_id].set({})
        else:
            resources = pnwutils.Resources(**resources)

        if not resources:
            await auth.send('You do not have anything to withdraw! Aborting...')
            return

        res_select_view = financeutils.ResourceSelectView(ctx.author.id, resources.keys_nonzero())
        await auth.send('What resources do you wish to withdraw?', view=res_select_view)

        msg_chk = discordutils.get_dm_msg_chk(auth.id)
        req_resources = pnwutils.Resources()
        try:
            res_names = res_select_view.result()
        except asyncio.TimeoutError:
            await auth.send('You took too long to reply! Aborting.')
            return

        for res in await res_names:
            if not resources[res]:
                await auth.send(f'You do not have any {res}! Skipping...')
                continue
            await auth.send(f'How much {res} do you wish to withdraw?')
            while True:
                try:
                    amt = (await self.bot.wait_for('message', check=msg_chk, timeout=discordutils.Config.timeout)
                           ).content
                except asyncio.TimeoutError:
                    await auth.send('You took too long to reply! Aborting.')
                    return

                try:
                    amt = int(amt)
                except ValueError:
                    await auth.send("That isn't a number! Please try again.")
                    continue
                if amt <= 0:
                    await auth.send('You must withdraw at more than 0 of this resource!')
                    continue
                if amt > resources[res]:
                    await auth.send(f'You cannot withdraw that much {res}! You only have {resources[res]} {res}!')
                    continue

                break
            req_resources[res] = amt

        await auth.send('Is there a reason for this withdrawal?')
        try:
            reason = (await self.bot.wait_for('message', check=msg_chk, timeout=discordutils.Config.timeout)
                      ).content
        except asyncio.TimeoutError:
            await auth.send('You took too long to reply! Aborting.')
            return

        name_query = '''
        query nation_name($nation_id: [Int]) {
          nations(id: $nation_id, first: 1) {
            data {
              nation_name
            }
          }
        }
        '''

        data = await pnwutils.API.post_query(self.bot.session, name_query, {'nation_id': nation_id}, 'nations')
        name = data['data'][0]['nation_name']
        link = pnwutils.Link.bank('w', req_resources, name, 'Withdrawal from balance')

        view = financeutils.WithdrawalView(link, self.on_sent, auth, req_resources)

        msg = await channel.send(f'Withdrawal Request from {auth.mention}',
                                 embed=financeutils.withdrawal_embed(name, nation_id, reason, req_resources),
                                 allowed_mentions=discord.AllowedMentions.none(),
                                 view=view)
        self.bot.add_view(view, message_id=msg.id)

        res = resources - req_resources
        await self.balances[nation_id].set(res.to_dict())
        await auth.send('Your withdrawal request has been sent. '
                        'It will be sent to your nation shortly.')

    @staticmethod
    async def on_sent(requester: Union[discord.User, discord.Member], req_res: pnwutils.Resources):
        await requester.send('Your withdrawal request has been sent to your nation!',
                             embed=req_res.create_embed(title='Withdrawn Resources'))

    @deposit.error
    @withdraw.error
    async def on_error(self, ctx: commands.Context,
                       error: commands.CommandError) -> None:
        if isinstance(error, commands.MaxConcurrencyReached):
            await ctx.send('You are already trying to withdraw/deposit!')
            return None
        await discordutils.default_error_handler(ctx, error)

    @bank.group(invoke_without_command=True, aliases=('m',), hidden=True)
    async def market(self, ctx: commands.Context):
        """Market related commands"""
        await ctx.send_help(self.market)

    @market.command(name='prices', aliases=('price', 'p'), hidden=True)
    async def _prices(self, ctx: commands.Context):
        """List out the prices of resources"""
        await ctx.send(embed=discordutils.construct_embed(await self.prices.get(), title='Bank Trading Prices'))

    @discordutils.gov_check
    @market.command(name='set', aliases=('s',))
    async def _set(self, ctx, res: str, price: int):
        """Set the buying/selling price of a resource"""
        if (await self.prices.get(None)) is None:
            await self.prices.set({})

        if price <= 0:
            await ctx.send('Price must be positive!')
            return

        if res.lower() in pnwutils.Constants.all_res:
            await self.prices[res.capitalize()].set(price)
            await ctx.send(f'The price of {res} has been set to {price} ppu.')
            return

        await ctx.send(f"{res} isn't a valid resource!")

    @discordutils.gov_check
    @market.command()
    async def open(self, ctx: commands.Context):
        """Open or close the market"""
        await self.market_open.transform(operator.not_)
        s = 'open' if await self.market_open.get() else 'closed'
        await ctx.send(f'The market is now {s}!')

    @market.command()
    async def buy(self, ctx: commands.Context, res_name: str, amt: int):
        """Purchase some amount of a resource for money"""
        if not await self.market_open.get():
            await ctx.send('The market is currently closed!')
            return

        prices = await self.prices.get()
        if p := prices.get(res_name.capitalize()):
            bal = self.balances[await self.nations[ctx.author.id].get()]
            res = pnwutils.Resources(**await bal.get())
            res.money -= amt * p
            if res.money < 0:
                await ctx.send('You do not have enough money deposited to do that!')
                return
            res[res_name.lower()] += amt
            await bal.set(res.to_dict())
            await ctx.send('Transaction complete!',
                           embed=res.create_balance_embed(ctx.author.name)
                           )

            return
        await ctx.send(f'{res_name} is not a valid resource!')

    @market.command()
    async def sell(self, ctx: commands.Context, res_name: str, amt: int):
        """Sell some amount of a resource to the bank for money"""
        if not await self.market_open.get():
            await ctx.send('The market is currently closed!')
            return

        prices = await self.prices.get()
        if p := prices.get(res_name.capitalize()):
            bal = self.balances[await self.nations[ctx.author.id].get()]
            res = pnwutils.Resources(**await bal.get())
            res[res_name.lower()] -= amt
            if res[res_name.lower()] < 0:
                await ctx.send('You do not have enough money deposited to do that!')
                return
            res.money += amt * p
            await bal.set(res.to_dict())
            await ctx.send('Transaction complete!',
                           embed=res.create_balance_embed(ctx.author.name)
                           )
            return
        await ctx.send(f'{res_name} is not a valid resource!')

    @bank.group(invoke_without_command=True)
    async def loan(self, ctx: commands.Context):
        """Loan related commands"""
        await ctx.send_help(self.loan)

    @loan.command(name='return', aliases=('ret',))
    async def _return(self, ctx: commands.Context):
        """Return your loan from your balance, if any"""
        nation_id = await self.nations[ctx.author.id].get()
        loan = await self.loans[nation_id].get(None)
        if loan is None:
            await ctx.send("You don't have an active loan!")
            return
        loan = financeutils.LoanData(**loan)
        bal = self.balances[nation_id]
        res = pnwutils.Resources(**await bal.get())
        res -= loan.resources
        if res.all_positive():
            await bal.set(res.to_dict())
            await self.loans[nation_id].delete()
            await ctx.send('Your loan has been successfully repaid!')
            return
        await ctx.send('You do not have enough resources to repay your loan.')

    @loan.command()
    async def status(self, ctx: commands.Context):
        """Check the current status of your loan, if any"""
        loan = await self.loans[await self.nations[ctx.author.id].get()].get(None)
        if loan is None:
            await ctx.send("You don't have an active loan!")
            return
        await ctx.send(embed=financeutils.LoanData(**loan).to_embed())

    @discordutils.gov_check
    @bank.command()
    async def adjust(self, ctx: commands.Context, member: discord.Member = None):
        """Manually adjust the resource values of someone's balance"""
        if member is None:
            member = await discordutils.get_member_from_context(ctx)
        nation_id = await self.nations[member.id].get(None)
        if nation_id is None:
            await ctx.send(f"{member.mention}'s nation id has not been set!",
                           allowed_mentions=discord.AllowedMentions.none())
            return

        res_select_view = financeutils.ResourceSelectView(ctx.author.id)
        await ctx.send('What resources would you like to adjust?', view=res_select_view)

        resources = await self.balances[nation_id].get(None)
        if resources is None:
            resources = pnwutils.Resources()
            await self.balances[nation_id].set({})
        else:
            resources = pnwutils.Resources(**resources)

        msg_chk = discordutils.get_msg_chk(ctx)
        for res in await res_select_view.result():
            await ctx.send(f'How much would you like to adjust {res} by?')
            while True:
                try:
                    amt = (await self.bot.wait_for('message', check=msg_chk, timeout=discordutils.Config.timeout)
                           ).content
                except asyncio.TimeoutError:
                    await ctx.send('You took too long to reply! Aborting.')
                    return

                try:
                    amt = int(amt)
                except ValueError:
                    await ctx.send("That isn't a number! Please try again.")
                    continue
                break
            resources[res] += amt

        await self.balances[nation_id].set(resources.to_dict())
        await ctx.send(f'The balance of {member.mention} has been modified!',
                       embed=resources.create_balance_embed(member.name),
                       allowed_mentions=discord.AllowedMentions.none())

    @discordutils.gov_check
    @bank.command()
    async def set(self, ctx: commands.Context, member: discord.Member = None):
        """Manually set the resource values of someone's balance"""
        if member is None:
            member = await discordutils.get_member_from_context(ctx)
        nation_id = await self.nations[member.id].get(None)
        if nation_id is None:
            await ctx.send(f"{member.mention}'s nation id has not been set!",
                           allowed_mentions=discord.AllowedMentions.none())
            return

        res_select_view = financeutils.ResourceSelectView(ctx.author.id)
        await ctx.send('What resources would you like to set?', view=res_select_view)

        resources = await self.balances[nation_id].get(None)
        if resources is None:
            resources = pnwutils.Resources()
            await self.balances[nation_id].set({})
        else:
            resources = pnwutils.Resources(**resources)

        msg_chk = discordutils.get_msg_chk(ctx)
        for res in await res_select_view.result():
            await ctx.send(f'What would you like to set {res} to?')
            while True:
                try:
                    amt = (await self.bot.wait_for('message', check=msg_chk, timeout=discordutils.Config.timeout)
                           ).content
                except asyncio.TimeoutError:
                    await ctx.send('You took too long to reply! Aborting.')
                    return
                try:
                    amt = int(amt)
                except ValueError:
                    await ctx.send("That isn't a number! Please try again.")
                    continue
                break
            resources[res] = amt

        await self.balances[nation_id].set(resources.to_dict())
        await ctx.send(f'The balance of {member.mention} has been modified!',
                       embed=resources.create_balance_embed(member.name),
                       allowed_mentions=discord.AllowedMentions.none())

    @discordutils.gov_check
    @bank.command(aliases=('check',))
    async def c(self, ctx: commands.Context):
        bank_query_string = '''
        query bank_info($alliance_id: [Int]) {
          alliances(id: $alliance_id, first: 1) {
            data {
              money
              food
              aluminum
              steel
              munitions
              gasoline
              bauxite
              iron
              lead
              uranium
              oil
              coal
            }
          }
        }
        '''
        data = await pnwutils.API.post_query(
            self.bot.session, bank_query_string,
            {'alliance_id': pnwutils.Config.aa_id},
            'alliances'
        )
        resources = pnwutils.Resources(**data['data'].pop())
        await ctx.send(embed=resources.create_embed())

    @discordutils.gov_check
    @commands.command()
    async def offshore(self, ctx: commands.Context):
        pass


def setup(bot: dbbot.DBBot):
    bot.add_cog(BankCog(bot))
