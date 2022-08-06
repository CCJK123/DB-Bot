import asyncio
import datetime

import discord
from discord import commands
from discord.ext import commands as cmds, pages

from utils import financeutils, discordutils, pnwutils, config, dbbot
from utils.queries import (bank_transactions_query, bank_info_query, nation_name_query,
                           nation_resources_query, bank_revenue_query)


class BankCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.users_table = self.bot.database.get_table('users')
        self.loans_table = self.bot.database.get_table('loans')

    async def get_transactions(self, entity_id: 'str | int | None' = None,
                               entity_type: 'pnwutils.EntityType | None' = None,
                               transaction_type: 'pnwutils.TransactionType | None' = None
                               ) -> list[pnwutils.Transaction]:
        if entity_id is None and entity_type is not None:
            raise ValueError('Please provide entity id!')

        # get data from api
        data = await bank_transactions_query.query(self.bot.session, alliance_id=config.alliance_id)

        bank_recs = data['data'][0]['bankrecs']
        if entity_id is None:
            # if not filtering by ID
            return [pnwutils.Transaction.from_api_dict(rec) for rec in bank_recs]
        entity_id = int(entity_id)
        transactions = []
        for bank_rec in bank_recs:
            transaction = pnwutils.Transaction.from_api_dict(bank_rec)
            # otherwise, check before adding transaction
            if transaction.entity_id == entity_id and (entity_type is None or transaction.entity_type is entity_type) \
                    and (transaction_type is None or transaction.transaction_type is transaction_type):
                transactions.append(transaction)

        return transactions

    bank = commands.SlashCommandGroup('bank', 'Bank related commands!', guild_ids=config.guild_ids)

    @bank.command(guild_ids=config.guild_ids)
    async def balance(self, ctx: discord.ApplicationContext):
        """Check your bank balance"""
        '''
        rec = await self.users_table.select_row('balance', 'loaned', 'due_date').join(
            'INNER', self.loans_table, 'discord_id').where(discord_id=ctx.author.id)
        '''
        rec = await self.bot.database.fetch_row(
            'SELECT balance, loaned, due_date FROM users LEFT JOIN loans ON users.discord_id = loans.discord_id '
            'WHERE users.discord_id = $1', ctx.author.id
        )

        # actual displaying
        await ctx.respond(embed=pnwutils.Resources(**rec['balance']).create_balance_embed(ctx.author),
                          allowed_mentions=discord.AllowedMentions.none(),
                          ephemeral=True)
        if (date := rec['due_date']) is not None:
            await ctx.respond(
                f'You have a loan due {discord.utils.format_dt(date)} ({discord.utils.format_dt(date, "R")})',
                embed=pnwutils.Resources(**rec['loaned']).create_embed(title='Loaned Resources'), ephemeral=True)

    @bank.command(guild_ids=config.guild_ids)
    @cmds.max_concurrency(1, cmds.BucketType.user)
    async def deposit(self, ctx: discord.ApplicationContext):
        """Deposit resources into your balance"""
        # various data access
        nation_id = await self.users_table.select_val('nation_id').where(discord_id=ctx.author.id)
        if nation_id is None:
            await ctx.respond('Your nation id has not been set!', ephemeral=True)
            return

        await ctx.respond('Please check your DMs!', ephemeral=True)
        author = ctx.author

        # deposit check
        view = DepositView('Deposit Link', pnwutils.link.bank('d', note='Deposit to balance'))
        start_time = datetime.datetime.now(tz=datetime.timezone.utc)
        await author.send(
            'You now have 5 minutes to deposit your resources into the bank. '
            'Once you are done, press the button.', view=view
        )

        try:
            await view.result()
        except asyncio.TimeoutError:
            await author.send('You have not responded for 5 minutes! '
                              'Automatically checking for deposits...')

        # get transactions since start_time involving deposits by nation
        dep_transactions = list(filter(
            lambda t: t.time >= start_time,
            await self.get_transactions(nation_id, pnwutils.EntityType.NATION, pnwutils.TransactionType.DEPOSIT)))
        deposited = sum((transaction.resources.floor_values() for transaction in dep_transactions),
                        pnwutils.Resources())
        if deposited:
            new_bal_rec = await self.users_table.update(f'balance = balance + {deposited.to_row()}').where(
                discord_id=ctx.author.id).returning_val('balance')
            await asyncio.gather(
                author.send('Deposits Recorded! Your balance is now:',
                            embed=pnwutils.Resources(**new_bal_rec).create_balance_embed(author)),
                self.bot.log(embeds=(
                    discordutils.create_embed(user=author, description='Deposited some resources'),
                    deposited.create_embed(title='Resources Deposited')
                )))
            return
        await author.send('You did not deposit any resources! Aborting!')

    @bank.command(guild_ids=config.guild_ids)
    @cmds.max_concurrency(1, cmds.BucketType.user)
    async def withdraw(self, ctx: discord.ApplicationContext):
        """Withdraw resources from your balance"""
        rec = await self.users_table.select_row('nation_id', 'balance').where(discord_id=ctx.author.id)
        if rec is None:
            await ctx.respond('Your nation id has not been set!', ephemeral=True)
            return

        channel_id = await self.bot.database.get_kv('channel_ids').get('withdrawal_channel')
        if channel_id is None:
            await ctx.respond('Output channel has not been set! Aborting...')
            return None

        resources = pnwutils.Resources(**rec['balance'])
        if not resources:
            await ctx.respond('You do not have anything to withdraw! Aborting...', ephemeral=True)
            return

        await ctx.respond('Please check your DMs!', ephemeral=True)
        author = ctx.author

        await author.send('You current balance is:', embed=resources.create_balance_embed(author))

        res_select_view = financeutils.ResourceSelectView(author.id, resources.keys_nonzero())
        await author.send('What resources do you wish to withdraw?', view=res_select_view)

        msg_chk = discordutils.get_dm_msg_chk(author.id)
        req_resources = pnwutils.Resources()
        try:
            res_names = await res_select_view.result()
        except asyncio.TimeoutError:
            await author.send('You took too long to reply! Aborting.')
            return

        for res in res_names:
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
                    await author.send('You must withdraw at least 0 of this resource! Please try again.')
                    continue
                if amt > resources[res]:
                    await author.send(f'You cannot withdraw that much {res}! You only have {resources[res]:,} {res}!')
                    continue

                break
            req_resources[res] = amt

        await author.send('What is the reason for this withdrawal?')
        try:
            reason = (await self.bot.wait_for('message', check=msg_chk, timeout=config.timeout)
                      ).content
        except asyncio.TimeoutError:
            await author.send('You took too long to reply! Aborting.')
            return

        data = await nation_name_query.query(self.bot.session, nation_id=rec['nation_id'])
        name = data['data'][0]['nation_name']

        custom_id = await self.bot.get_custom_id()
        view = financeutils.WithdrawalView(
            author.id, pnwutils.Withdrawal(req_resources, rec['nation_id'], note='Withdrawal from balance'),
            custom_id=custom_id)

        msg = await self.bot.get_channel(channel_id).send(
            f'Withdrawal Request from {author.mention}',
            embed=financeutils.withdrawal_embed(name, rec['nation_id'], reason, req_resources),
            allowed_mentions=discord.AllowedMentions.none(),
            view=view)
        await self.bot.add_view(view, message_id=msg.id)

        new_bal_rec = await self.users_table.update(f'balance = balance - {req_resources.to_row()}').where(
            discord_id=ctx.author.id).returning_val('balance')
        await asyncio.gather(
            author.send('Your withdrawal request has been recorded. '
                        'It will be sent to your nation soon.\n\nYour balance is now:',
                        embed=pnwutils.Resources(**new_bal_rec).create_balance_embed(author)),
            self.bot.log(embeds=(
                discordutils.create_embed(user=author, description='Asked for a withdrawal'),
                req_resources.create_embed(title='Requested Resources')
            ))
        )

    @deposit.error
    @withdraw.error
    async def on_error(self, ctx: discord.ApplicationContext,
                       error: discord.ApplicationCommandError) -> None:
        if isinstance(error.__cause__, cmds.MaxConcurrencyReached):
            await ctx.respond('You are already trying to withdraw/deposit!', ephemeral=True)
            return

        await self.bot.default_on_error(ctx, error)

    @bank.command(guild_ids=config.guild_ids)
    async def transfer(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Transfer some of your balance to someone else"""
        if member == ctx.author:
            await ctx.respond('You cannot transfer resources to yourself!')
            return
        sender_bal_rec = await self.users_table.select_val('balance').where(discord_id=ctx.author.id)
        if sender_bal_rec is None:
            await ctx.respond('Your nation id has not been set! Aborting...', ephemeral=True)
            return
        if not await self.users_table.exists(discord_id=member.id):
            await ctx.respond("The recipient's nation id has not been set! Aborting...", ephemeral=True)
            return

        sender_bal = pnwutils.Resources(**sender_bal_rec)
        if not sender_bal:
            await ctx.respond('You do not have anything to transfer! Aborting...', ephemeral=True)
            return

        await ctx.respond('Please check your DMs!', ephemeral=True)
        author = ctx.author

        res_select_view = financeutils.ResourceSelectView(author.id, sender_bal.keys_nonzero())
        await author.send('What resources do you wish to transfer?', view=res_select_view)

        msg_chk = discordutils.get_dm_msg_chk(author.id)
        t_resources = pnwutils.Resources()
        try:
            res_names = await res_select_view.result()
        except asyncio.TimeoutError:
            await author.send('You took too long to reply! Aborting.')
            return

        for res in res_names:
            await author.send(f'How much {res} do you wish to transfer?')
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
                if amt < 0:
                    await author.send('You must transfer at least 0 of this resource! Please try again.')
                    continue
                if amt > sender_bal[res]:
                    await author.send(f'You cannot transfer that much {res}! You only have {sender_bal[res]:,} {res}!')
                    continue

                break
            t_resources[res] = amt
        if not t_resources:
            await author.send('You cannot transfer nothing! Aborting...')
            return
        final_sender_bal = sender_bal - t_resources
        await self.users_table.update(f'balance = {final_sender_bal.to_row()}').where(discord_id=author.id)
        final_receiver_bal_rec = await self.users_table.update(
            f'balance = balance - {t_resources.to_row()}').where(discord_id=member.id).returning_val('balance')
        await asyncio.gather(
            author.send(f'You have sent {member.display_name} [{t_resources}]!\n\nYour balance is now:',
                        embed=final_sender_bal.create_balance_embed(author)),
            member.send(
                f'You have been transferred [{t_resources}] from {author.display_name}!\n\nYour balance is now:',
                embed=pnwutils.Resources(**final_receiver_bal_rec).create_balance_embed(member)),
            self.bot.log(embeds=(
                discordutils.create_embed(user=author, description=f'Transferred resources to {member.mention}'),
                t_resources.create_embed(title='Transferred Resources')
            )))

    loan = bank.create_subgroup('loan', 'Commands related to loans')
    loan.guild_ids = config.guild_ids

    @loan.command(name='return', guild_ids=config.guild_ids)
    async def _return(self, ctx: discord.ApplicationContext):
        """Return your loan using resources from your balance, if any"""
        rec = await self.bot.database.fetch_row(
            'SELECT balance, loaned FROM users INNER JOIN loans ON users.discord_id = loans.discord_id '
            'WHERE users.discord_id = $1', ctx.author.id)
        if rec is None:
            await ctx.respond("You don't have an active loan!", ephemeral=True)
            return
        res = pnwutils.Resources(**rec['balance'])
        loaned = pnwutils.Resources(**rec['loaned'])
        res -= loaned
        if res.all_positive():
            await asyncio.gather(
                self.users_table.update(f'balance = {res.to_row()}'),
                self.loans_table.delete().where(discord_id=ctx.author.id),
                ctx.respond('Your loan has been successfully repaid!\n\nYour balance is now:',
                            embed=res.create_balance_embed(ctx.author), ephemeral=True),
                self.bot.log(embeds=(
                    discordutils.create_embed(user=ctx.author, description='Repaid their loan'),
                    loaned.create_embed(title='Loan Value')
                )))
            return
        await ctx.respond('You do not have enough resources to repay your loan.', ephemeral=True,
                          embed=loaned.create_embed(title=f"{ctx.author.mention}'s Loan"))

    @loan.command(guild_ids=config.guild_ids)
    async def status(self, ctx: discord.ApplicationContext):
        """Check the current status of your loan, if any"""

        loan = await self.loans_table.select_row('loaned', 'due_date').where(discord_id=ctx.author.id)
        if loan is None:
            await ctx.respond("You don't have an active loan!", ephemeral=True)
            return
        await ctx.respond(embed=financeutils.LoanData(**loan).to_embed(), ephemeral=True)

    @commands.user_command(name='check balance', guild_ids=config.guild_ids)
    @commands.default_permissions()
    async def check_bal(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Check the bank balance of this member"""
        bal_rec = await self.users_table.select_val('balance').where(discord_id=member.id)
        if bal_rec is None:
            await ctx.respond('This user is not registered!')
            return
        await ctx.respond(
            f"{member.mention}'s Balance",
            embed=pnwutils.Resources(**bal_rec).create_balance_embed(member),
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True
        )

    @commands.user_command(name='check resources', guild_ids=config.guild_ids)
    @commands.default_permissions()
    async def check_res(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Check the resources this member has"""
        nation_id = await self.users_table.select_val('nation_id').where(discord_id=member.id)
        if nation_id is None:
            await ctx.respond('This member has not registered their nation!', ephemeral=True)
            return

        data = await nation_resources_query.query(self.bot.session, nation_id=nation_id)
        data = data['data'][0]
        if data['money'] is None:
            await ctx.respond('That member is not part of the alliance!', ephemeral=True)
            return
        name = data['nation_name']
        del data['nation_name']
        await ctx.respond(embed=pnwutils.Resources(**data).create_embed(title=f"{name}'s Resources"),
                          ephemeral=True)

    _bank = commands.SlashCommandGroup('_bank', "Gov Bank Commands", guild_ids=config.guild_ids,
                                       default_member_permissions=discord.Permissions())

    @_bank.command(guild_ids=config.guild_ids)
    async def loan_list(self, ctx: discord.ApplicationContext):
        """List all the loans that are currently active"""
        paginator_pages = []
        async with self.bot.database.acquire() as conn:
            async with conn.transaction():
                loan_cursor = await self.loans_table.select().cursor(conn)
                while chunk := await loan_cursor.fetch(10):
                    embeds = []
                    for rec in chunk:
                        due_date = discord.utils.format_dt(rec['due_date'])
                        m = ctx.guild.get_member(rec['discord_id'])
                        embeds.append(pnwutils.Resources(**rec['loaned']).create_embed(
                            title=f"{m.display_name}'s Loan due on {due_date}"))
                    paginator_pages.append(embeds)
        if paginator_pages:
            paginator = pages.Paginator(paginator_pages, timeout=config.timeout)
            await paginator.respond(ctx.interaction)
            return
        await ctx.respond('There are no active loans!', ephemeral=True)

    @_bank.command(guild_ids=config.guild_ids)
    @discord.option('adjusted', bool, description='Whether to adjust for balances held by members')
    @discord.option('total', bool, description='Whether to include offshore bank contents')
    @discord.option('ephemeral', bool, description='Whether to only allow you to see the message')
    async def contents(self, ctx: discord.ApplicationContext, adjusted: bool = False, total: bool = False,
                       ephemeral: bool = True):
        """Check the current contents of the bank"""
        data = await bank_info_query.query(self.bot.session, alliance_id=config.alliance_id)
        resources = pnwutils.Resources(**data['data'][0])
        if adjusted:
            await ctx.defer()
            resources -= await self.get_total_balances()
        if total:
            off_contents = await bank_info_query.query(self.bot.session, api_key=config.offshore_api_key,
                                                       alliance_id=await self.bot.get_offshore_id())
            resources += pnwutils.Resources(**off_contents['data'][0])
        await ctx.respond(embed=resources.create_embed(title=f'{config.alliance_name} Bank'), ephemeral=ephemeral)

    @_bank.command(guild_ids=config.guild_ids)
    async def safekeep(self, ctx: discord.ApplicationContext):
        """Get a link to send the entire bank to an offshore"""

        data = await bank_info_query.query(self.bot.session, alliance_id=config.alliance_id)
        resources = pnwutils.Resources(**data['data'][0])

        withdrawal = pnwutils.Withdrawal(resources, await self.bot.get_offshore_id(),
                                         pnwutils.EntityType.ALLIANCE, 'Safekeeping')
        if await withdrawal.withdraw(self.bot.session) is pnwutils.WithdrawalResult.SUCCESS:
            await ctx.respond('The bank contents have successfully been sent to the offshore!')
            return
        await ctx.respond('An unexpected error occurred: Bank does not have enough resources to send its contents.')

    async def get_total_balances(self) -> pnwutils.Resources:
        async with self.bot.database.acquire() as conn:
            async with conn.transaction():
                total = pnwutils.Resources()
                async for bal in self.users_table.select('balance').cursor(conn):
                    total += pnwutils.Resources(**bal['balance'])
                return total

    @_bank.command(guild_ids=config.guild_ids)
    @discord.option('ephemeral', bool, description='Whether to only allow you to see the message')
    async def total_balances(self, ctx: discord.ApplicationContext, ephemeral: bool = True):
        """Find the total value of all balances"""
        await ctx.defer()
        total = await self.get_total_balances()
        await ctx.respond(embed=total.create_embed(title=f'Total Value of all Balances'), ephemeral=ephemeral)

    @_bank.command(guild_ids=config.guild_ids)
    @discord.option('ephemeral', bool, description='Whether to only allow you to see the message')
    async def revenue(self, ctx: discord.ApplicationContext, ephemeral: bool = True):
        """Find the resources generated by taxes last turn"""
        await ctx.defer()
        data = await bank_revenue_query.query(self.bot.session, alliance_id=config.alliance_id)
        tax_records = data['data'][0]['taxrecs']
        first_date = datetime.datetime.fromisoformat(tax_records[0]['date']).replace(minute=0, second=0, microsecond=0)
        total = pnwutils.Resources()
        for tax_rec in tax_records:
            if datetime.datetime.fromisoformat(tax_rec['date']) < first_date:
                break
            total += pnwutils.Resources.from_dict(tax_rec)
        await ctx.respond(embed=total.create_embed(title='Tax Revenue from Last Turn'), ephemeral=ephemeral)

    @_bank.command(guild_ids=config.guild_ids)
    async def edit(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Manually edit the resource values of someone's balance"""
        resources_rec = await self.users_table.select_val('balance').where(discord_id=member.id)
        if resources_rec is None:
            await ctx.respond('This user has not been registered!', ephemeral=True)
        resources = pnwutils.Resources(**resources_rec)

        await ctx.respond('Please check your DMs!', ephemeral=True)

        author = ctx.author
        res_select_view = financeutils.ResourceSelectView(author.id)
        kind_view = discordutils.Choices('Set', 'Adjust')
        await author.send('Do you wish to set or adjust the balance?', view=kind_view)
        adjust = await kind_view.result() == 'Adjust'
        text = 'adjust' if adjust else 'set'
        msg_chk = discordutils.get_dm_msg_chk(author.id)
        await author.send(f'What resources would you like to {text}?', view=res_select_view)

        for res in await res_select_view.result():
            await author.send(f'What would you like to {text} {res} to?')
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
            if adjust:
                resources[res] += amt
            else:
                resources[res] = amt

        await asyncio.gather(
            self.users_table.update(f'balance = {resources.to_row()}').where(discord_id=member.id),
            author.send(f'The balance of {member.mention} has been modified!',
                        embed=resources.create_balance_embed(member),
                        allowed_mentions=discord.AllowedMentions.none()),
            self.bot.log(embeds=(
                discordutils.create_embed(user=member, description=f'Had their balance modified by {author.mention}'),
                resources.create_embed(title='Balance after modification')
            )))


class DepositView(discordutils.Choices):
    def __init__(self, label: str, url: str):
        super().__init__('Done!')
        self.add_item(discordutils.LinkButton(label, url))


def setup(bot: dbbot.DBBot):
    bot.add_cog(BankCog(bot))
