import asyncio
import datetime

import discord
from discord.ext import commands

from bot.utils import discordutils, pnwutils, config
from bot import dbbot
from bot.cogs.finance import finance_views
from bot.utils.queries import (
    bank_transactions_query, bank_info_query, nation_name_query, nation_resources_query, bank_revenue_query,
    leader_name_query, tax_bracket_query, nation_revenue_query, treasures_query, colours_query)


class BankCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.users_table = self.bot.database.get_table('users')
        self.loans_table = self.bot.database.get_table('loans')

        self.bot.tree.add_command(discord.app_commands.ContextMenu(
            name='Check Balance',
            callback=self.check_bal
        ))
        self.bot.tree.add_command(discord.app_commands.ContextMenu(
            name='Check Resources',
            callback=self.check_res
        ))

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

    bank = discord.app_commands.Group(name='bank', description='Bank related commands!')

    @bank.command()
    @discord.app_commands.describe(ephemeral='Whether to only allow you to see the message')
    async def balance(self, interaction: discord.Interaction, ephemeral: bool = True):
        """Check your bank balance"""
        rec = await self.bot.database.fetch_row(
            'SELECT balance, loaned, due_date FROM users LEFT JOIN loans ON users.discord_id = loans.discord_id '
            'WHERE users.discord_id = $1', interaction.user.id
        )

        # actual displaying
        if rec is None:
            await interaction.response.send_message('You have not been registered!')
            return

        await interaction.response.send_message(
            embed=pnwutils.Resources(**rec['balance']).create_balance_embed(interaction.user),
            ephemeral=ephemeral
        )
        if (date := rec['due_date']) is not None:
            await interaction.followup.send(
                f'You have a loan due {discord.utils.format_dt(date)} ({discord.utils.format_dt(date, "R")})',
                embed=pnwutils.Resources(**rec['loaned']).create_embed(title='Loaned Resources'),
                ephemeral=ephemeral
            )

    @bank.command()
    @discordutils.max_one
    async def deposit(self, interaction: discord.Interaction):
        """Deposit resources into your balance"""
        # various data access
        nation_id = await self.users_table.select_val('nation_id').where(discord_id=interaction.user.id)
        if nation_id is None:
            await interaction.response.send_message('Your nation id has not been registered!', ephemeral=True)
            return

        await interaction.response.send_message('Please check your DMs!', ephemeral=True)
        user = interaction.user

        # deposit check
        view = finance_views.DepositView('Deposit Link', pnwutils.link.bank('d', note='Deposit to balance'))
        start_time = datetime.datetime.now(tz=datetime.timezone.utc)
        await user.send(
            'You now have 5 minutes to deposit your resources into the bank. '
            'Once you are done, press the button.', view=view
        )

        try:
            await view.result()
        except asyncio.TimeoutError:
            await user.send('You have not responded for 5 minutes! '
                            'Automatically checking for deposits...')

        # get transactions since start_time involving deposits by nation
        deposited = sum(
            (transaction.resources.floor_values() for transaction in
             await self.get_transactions(nation_id, pnwutils.EntityType.NATION, pnwutils.TransactionType.DEPOSIT)
             if transaction.time >= start_time),
            pnwutils.Resources())
        if deposited:
            new_bal_rec = await self.users_table.update(f'balance = balance + {deposited.to_row()}').where(
                discord_id=user.id).returning_val('balance')
            await asyncio.gather(
                user.send('Deposits Recorded! Your balance is now:',
                          embed=pnwutils.Resources(**new_bal_rec).create_balance_embed(user)),
                self.bot.log(embeds=(
                    discordutils.create_embed(user=user, description=f'{user.mention} deposited some resources'),
                    deposited.create_embed(title='Resources Deposited')
                )))
            return
        await user.send('You did not deposit any resources! Aborting!')

    @bank.command()
    @discordutils.max_one
    async def withdraw(self, interaction: discord.Interaction):
        """Withdraw resources from your balance"""
        rec = await self.users_table.select_row('nation_id', 'balance').where(discord_id=interaction.user.id)
        if rec is None:
            await interaction.response.send_message('Your nation id has not been set!', ephemeral=True)
            return

        channel_id = await self.bot.database.get_kv('channel_ids').get('withdrawal_channel')
        if channel_id is None:
            await interaction.response.send_message('Output channel has not been set! Aborting...')
            return

        resources = pnwutils.Resources(**rec['balance'])
        if not resources:
            await interaction.response.send_message('You do not have anything to withdraw! Aborting...', ephemeral=True)
            return

        await interaction.response.send_message('Please check your DMs!', ephemeral=True)
        user = interaction.user

        await user.send('You current balance is:', embed=resources.create_balance_embed(user))

        res_select_view = finance_views.ResourceSelectView(res=resources.keys_nonzero())
        await user.send('What resources do you wish to withdraw?', view=res_select_view)

        msg_chk = discordutils.get_dm_msg_chk(user.id)
        req_resources = pnwutils.Resources()
        try:
            res_names = await res_select_view.result()
        except asyncio.TimeoutError:
            await user.send('You took too long to reply! Aborting.')
            return

        for res in res_names:
            await user.send(f'How much {res} do you wish to withdraw?')
            while True:
                try:
                    amt = (await self.bot.wait_for('message', check=msg_chk, timeout=config.timeout)
                           ).content
                except asyncio.TimeoutError:
                    await user.send('You took too long to reply! Aborting.')
                    return

                try:
                    amt = int(amt)
                except ValueError:
                    await user.send("That isn't a number! Please try again.")
                    continue
                if amt <= 0:
                    await user.send('You must withdraw at least 0 of this resource! Please try again.')
                    continue
                if amt > resources[res]:
                    await user.send(f'You cannot withdraw that much {res}! You only have {resources[res]:,} {res}!')
                    continue

                break
            req_resources[res] = amt

        await user.send('What is the reason for this withdrawal?')
        try:
            reason = (await self.bot.wait_for('message', check=msg_chk, timeout=config.timeout)
                      ).content
        except asyncio.TimeoutError:
            await user.send('You took too long to reply! Aborting.')
            return

        data = await nation_name_query.query(self.bot.session, nation_id=rec['nation_id'])
        name = data['data'][0]['nation_name']

        custom_id = await self.bot.get_custom_id()
        view = finance_views.WithdrawalView(
            user.id, pnwutils.Withdrawal(req_resources, rec['nation_id'], note='Withdrawal from balance'),
            custom_id=custom_id)

        msg = await self.bot.get_channel(channel_id).send(
            f'Withdrawal Request from balance for {user.mention}',
            embed=finance_views.withdrawal_embed(name, rec['nation_id'], reason, req_resources),
            view=view)
        await self.bot.add_view(view, message_id=msg.id)

        new_bal_rec = await self.users_table.update(f'balance = balance - {req_resources.to_row()}').where(
            discord_id=user.id).returning_val('balance')
        await asyncio.gather(
            user.send('Your withdrawal request has been recorded. '
                      'It will be sent to your nation soon.\n\nYour balance is now:',
                      embed=pnwutils.Resources(**new_bal_rec).create_balance_embed(user)),
            self.bot.log(embeds=(
                discordutils.create_embed(user=user, description=f'{user.mention} asked for a withdrawal'),
                req_resources.create_embed(title='Requested Resources')
            ))
        )

    @deposit.error
    @withdraw.error
    async def on_error(self, interaction: discord.Interaction,
                       error: discord.app_commands.AppCommandError) -> None:
        if isinstance(error.__cause__, commands.MaxConcurrencyReached):
            await interaction.response.send_message('You are already trying to withdraw/deposit!', ephemeral=True)
            return

        await self.bot.default_on_error(interaction, error)

    @bank.command()
    async def transfer(self, interaction: discord.Interaction, member: discord.Member):
        """Transfer some of your balance to someone else"""
        if member == interaction.user:
            await interaction.response.send_message('You cannot transfer resources to yourself!', ephemeral=True)
            return
        sender_bal_rec = await self.users_table.select_val('balance').where(discord_id=interaction.user.id)
        if sender_bal_rec is None:
            await interaction.response.send_message('Your nation id has not been set! Aborting...', ephemeral=True)
            return
        if not await self.users_table.exists(discord_id=member.id):
            await interaction.response.send_message("The recipient's nation id has not been set! Aborting...",
                                                    ephemeral=True)
            return

        sender_bal = pnwutils.Resources(**sender_bal_rec)
        if not sender_bal:
            await interaction.response.send_message('You do not have anything to transfer! Aborting...', ephemeral=True)
            return

        await interaction.response.send_message('Please check your DMs!', ephemeral=True)
        user = interaction.user

        res_select_view = finance_views.ResourceSelectView(user.id, sender_bal.keys_nonzero())
        await user.send('What resources do you wish to transfer?', view=res_select_view)

        msg_chk = discordutils.get_dm_msg_chk(user.id)
        t_resources = pnwutils.Resources()
        try:
            res_names = await res_select_view.result()
        except asyncio.TimeoutError:
            await user.send('You took too long to reply! Aborting.')
            return

        for res in res_names:
            await user.send(f'How much {res} do you wish to transfer?')
            while True:
                try:
                    amt = (await self.bot.wait_for('message', check=msg_chk, timeout=config.timeout)
                           ).content
                except asyncio.TimeoutError:
                    await user.send('You took too long to reply! Aborting.')
                    return

                try:
                    amt = int(amt)
                except ValueError:
                    await user.send("That isn't a number! Please try again.")
                    continue
                if amt < 0:
                    await user.send('You must transfer at least 0 of this resource! Please try again.')
                    continue
                if amt > sender_bal[res]:
                    await user.send(f'You cannot transfer that much {res}! You only have {sender_bal[res]:,} {res}!')
                    continue

                break
            t_resources[res] = amt
        if not t_resources:
            await user.send('You cannot transfer nothing! Aborting...')
            return
        final_sender_bal = sender_bal - t_resources
        await self.users_table.update(f'balance = {final_sender_bal.to_row()}').where(discord_id=user.id)
        final_receiver_bal_rec = await self.users_table.update(
            f'balance = balance + {t_resources.to_row()}').where(discord_id=member.id).returning_val('balance')
        t_embed = t_resources.create_embed(title='Transferred Resources')
        await asyncio.gather(
            user.send(f'You have sent {member.mention} the following resources:', embed=t_embed),
            member.send(f'You have   been transferred the following resources from {user.mention}:', embed=t_embed))
        await asyncio.gather(
            user.send('Your balance is now:', embed=final_sender_bal.create_balance_embed(user)),
            member.send(f'Your balance is now:',
                        embed=pnwutils.Resources(**final_receiver_bal_rec).create_balance_embed(member)),
            self.bot.log(embeds=(
                discordutils.create_embed(
                    user=user, description=f'{user.mention} transferred resources to {member.mention}'),
                t_embed
            )))

    loan = discord.app_commands.Group(name='loan', description='Commands related to loans', parent=bank)
    loan.guild_ids = config.guild_ids

    @loan.command(name='return')
    async def _return(self, interaction: discord.Interaction):
        """Return your loan using resources from your balance, if any"""
        rec = await self.bot.database.fetch_row(
            'SELECT balance, loaned FROM users INNER JOIN loans ON users.discord_id = loans.discord_id '
            'WHERE users.discord_id = $1', interaction.user.id)
        if rec is None:
            await interaction.response.send_message("You don't have an active loan!", ephemeral=True)
            return
        res = pnwutils.Resources(**rec['balance'])
        loaned = pnwutils.Resources(**rec['loaned'])
        res -= loaned
        if res.all_positive():
            await asyncio.gather(
                self.users_table.update(f'balance = {res.to_row()}').where(discord_id=interaction.user.id),
                self.loans_table.delete().where(discord_id=interaction.user.id),
                interaction.response.send_message('Your loan has been successfully repaid!\n\nYour balance is now:',
                                                  embed=res.create_balance_embed(interaction.user), ephemeral=True),
                self.bot.log(embeds=(
                    discordutils.create_embed(user=interaction.user,
                                              description=f'{interaction.user.mention} repaid their loan'),
                    loaned.create_embed(title='Loan Value')
                )))
            return
        await interaction.response.send_message('You do not have enough resources to repay your loan.', ephemeral=True,
                                                embed=loaned.create_embed(title=f"Loaned Resources"))

    @loan.command()
    async def status(self, interaction: discord.Interaction):
        """Check the current status of your loan, if any"""

        loan = await self.loans_table.select_row('loaned', 'due_date').where(discord_id=interaction.user.id)
        if loan is None:
            await interaction.response.send_message("You don't have an active loan!", ephemeral=True)
            return
        await interaction.response.send_message(embed=finance_views.LoanData(**loan).to_embed(), ephemeral=True)

    @discord.app_commands.default_permissions()
    async def check_bal(self, interaction: discord.Interaction, member: discord.Member):
        """Check the bank balance of this member"""
        bal_rec = await self.users_table.select_val('balance').where(discord_id=member.id)
        if bal_rec is None:
            await interaction.response.send_message('This user is not registered!')
            return
        await interaction.response.send_message(
            embed=pnwutils.Resources(**bal_rec).create_balance_embed(member),
            ephemeral=True
        )

    @discord.app_commands.default_permissions()
    async def check_res(self, interaction: discord.Interaction, member: discord.Member):
        """Check the resources this member has"""
        nation_id = await self.users_table.select_val('nation_id').where(discord_id=member.id)
        if nation_id is None:
            await interaction.response.send_message('This member has not registered their nation!', ephemeral=True)
            return

        data = await nation_resources_query.query(self.bot.session, nation_id=nation_id)
        data = data['data'][0]
        if data['money'] is None:
            await interaction.response.send_message('That member is not part of the alliance!', ephemeral=True)
            return
        name = data['nation_name']
        del data['nation_name']
        await interaction.response.send_message(
            embed=pnwutils.Resources(**data).create_embed(title=f"{name}'s Resources"),
            ephemeral=True)

    _bank = discord.app_commands.Group(name='_bank', description="Gov Bank Commands",
                                       default_permissions=None)

    check = discord.app_commands.Group(name='check', description="Commands for checking on members", parent=_bank)

    @check.command(name='balance')
    @discord.app_commands.describe(nation_id='ID of nation to check',
                                   ephemeral='Whether to only allow you to see the message')
    async def check_balance(self, interaction: discord.Interaction, nation_id: int, ephemeral: bool = True):
        """Check the bank balance of this nation"""
        bal_rec = await self.users_table.select_val('balance').where(nation_id=nation_id)
        if bal_rec is None:
            await interaction.response.send_message(f'No user with nation ID {nation_id} is registered!',
                                                    ephemeral=ephemeral)
            return
        await interaction.response.send_message(
            embed=pnwutils.Resources(**bal_rec).create_balance_embed(None),
            ephemeral=ephemeral
        )

    @_bank.command()
    @discord.app_commands.describe(ephemeral='Whether to only allow you to see the message')
    async def loan_list(self, interaction: discord.Interaction, ephemeral: bool = True):
        """List all the loans that are currently active"""
        paginator_pages = []
        async with self.bot.database.acquire() as conn:
            async with conn.transaction():
                loan_cursor = await self.loans_table.select().cursor(conn)
                while chunk := await loan_cursor.fetch(10):
                    embeds = []
                    for rec in chunk:
                        due_date = discord.utils.format_dt(rec['due_date'])
                        m = interaction.guild.get_member(rec['discord_id'])
                        if m is None:
                            embeds.append(pnwutils.Resources(**rec['loaned']).create_embed(
                                title=f"{rec['discord_id']}'s Loan due on {due_date}"))
                        else:
                            embeds.append(pnwutils.Resources(**rec['loaned']).create_embed(
                                title=f"{m.display_name}'s Loan due on {due_date}"))
                    paginator_pages.append(embeds)
        if paginator_pages:
            paginator = discordutils.Pager(paginator_pages)
            await paginator.respond(interaction, ephemeral=ephemeral)
            return
        await interaction.response.send_message('There are no active loans!', ephemeral=ephemeral)

    @_bank.command()
    @discord.app_commands.describe(
        adjusted='Whether to adjust for balances held by members',
        total='Whether to include offshore bank contents',
        ephemeral='Whether to only allow you to see the message'
    )
    async def contents(self, interaction: discord.Interaction, adjusted: bool = False, total: bool = False,
                       ephemeral: bool = True):
        """Check the current contents of the bank"""
        data = await bank_info_query.query(self.bot.session, alliance_id=config.alliance_id)
        resources = pnwutils.Resources(**data['data'][0])
        if adjusted:
            await interaction.response.defer(ephemeral=ephemeral)
            resources -= await self.get_total_balances()
        if total:
            off_contents = await bank_info_query.query(self.bot.session, api_key=config.offshore_api_key,
                                                       alliance_id=await pnwutils.get_offshore_id(self.bot.session))
            resources += pnwutils.Resources(**off_contents['data'][0])
        await discordutils.interaction_send(
            interaction,
            embed=resources.create_embed(title=f'{config.alliance_name} Bank'),
            ephemeral=ephemeral
        )

    @_bank.command()
    async def safekeep(self, interaction: discord.Interaction):
        """Send the entire bank to the offshore for safekeeping"""

        data = await bank_info_query.query(self.bot.session, alliance_id=config.alliance_id)
        resources = pnwutils.Resources(**data['data'][0])

        withdrawal = pnwutils.Withdrawal(resources, await pnwutils.get_offshore_id(self.bot.session),
                                         pnwutils.EntityType.ALLIANCE, 'Safekeeping')
        if await withdrawal.withdraw(self.bot.session) is pnwutils.WithdrawalResult.SUCCESS:
            await interaction.response.send_message('The bank contents have successfully been sent to the offshore!')
            return
        await interaction.response.send_message(
            'An unexpected error occurred: Bank does not have enough resources to send its contents.'
        )

    async def get_total_balances(self) -> pnwutils.Resources:
        async with self.bot.database.acquire() as conn:
            async with conn.transaction():
                total = pnwutils.Resources()
                async for bal in self.users_table.select('balance').cursor(conn):
                    total += pnwutils.Resources(**bal['balance'])
                return total

    @_bank.command()
    @discord.app_commands.describe(ephemeral='Whether to only allow you to see the message')
    async def total_balances(self, interaction: discord.Interaction, ephemeral: bool = True):
        """Find the total value of all balances"""
        await interaction.response.defer(ephemeral=ephemeral)
        total = await self.get_total_balances()
        await interaction.followup.send(
            embed=total.create_embed(title=f'Total Value of all Balances'),
            ephemeral=ephemeral
        )

    @_bank.command()
    @discord.app_commands.describe(ephemeral='Whether to only allow you to see the message')
    async def revenue(self, interaction: discord.Interaction, ephemeral: bool = True):
        """Find the resources generated by taxes last turn"""
        await interaction.response.defer(ephemeral=ephemeral)
        data = await bank_revenue_query.query(self.bot.session, alliance_id=config.alliance_id,
                                              after=pnwutils.time_after_turns(0).isoformat(' '))
        total = sum((pnwutils.Resources.from_dict(tax_rec) for tax_rec in data['data'][0]['taxrecs']),
                    pnwutils.Resources())
        await interaction.followup.send(
            embed=total.create_embed(title='Tax Revenue from Last Turn'),
            ephemeral=ephemeral
        )

    @_bank.command()
    async def edit(self, interaction: discord.Interaction, member: discord.Member):
        """Manually edit the resource values of someone's balance"""
        resources_rec = await self.users_table.select_val('balance').where(discord_id=member.id)
        if resources_rec is None:
            await interaction.response.send_message('This user has not been registered!', ephemeral=True)
            return
        resources = pnwutils.Resources(**resources_rec)
        before = resources.copy()

        await interaction.response.send_message('Please check your DMs!', ephemeral=True)

        user = interaction.user
        await user.send('Why is this balance being edited?')
        try:
            msg = await self.bot.wait_for('message', check=discordutils.get_dm_msg_chk(user.id), timeout=config.timeout)
        except asyncio.TimeoutError:
            await user.send('You took too long to respond! Aborting...')
            return

        kind_view = discordutils.Choices('Set', 'Adjust')
        await user.send('Do you wish to set or adjust the balance?', view=kind_view)
        adjust = await kind_view.result() == 'Adjust'
        text = 'adjust' if adjust else 'set'
        msg_chk = discordutils.get_dm_msg_chk(user.id)
        res_select_view = finance_views.ResourceSelectView(user.id)
        await user.send(f'What resources would you like to {text}?', view=res_select_view)
        last = 'by' if adjust else 'to'
        for res in await res_select_view.result():
            await user.send(f'What would you like to {text} {res} {last}?')
            while True:
                try:
                    amt = (await self.bot.wait_for('message', check=msg_chk, timeout=config.timeout)
                           ).content
                except asyncio.TimeoutError:
                    await user.send('You took too long to reply! Aborting.')
                    return
                try:
                    amt = int(amt)
                except ValueError:
                    await user.send("That isn't a number! Please try again.")
                    continue
                break
            if adjust:
                resources[res] += amt
            else:
                resources[res] = amt

        await asyncio.gather(
            self.users_table.update(f'balance = {resources.to_row()}').where(discord_id=member.id),
            user.send(f'The balance of {member.mention} has been modified!',
                      embed=resources.create_balance_embed(member)),
            self.bot.log(embeds=(
                discordutils.create_embed(
                    user=member,
                    description=f'{member.mention} had their balance modified by {user.mention} '
                                f'for the reason of `{msg.content}`'),
                before.create_embed(title='Balance before modification'),
                resources.create_embed(title='Balance after modification')
            )))

    @_bank.command()
    async def pending_resources(self, interaction: discord.Interaction):
        """Create a restocking link for all the resources that are waiting to be withdrawn"""
        await interaction.response.defer()
        total = pnwutils.Resources()
        async for view in self.bot.view_table.get_all():
            if isinstance(view, finance_views.WithdrawalView):
                total += view.withdrawal.resources

        await interaction.followup.send(view=discordutils.LinkView(
            'Restock Link',
            pnwutils.link.bank('wa', total, config.alliance_name,
                               alliance_id=await pnwutils.get_offshore_id(self.bot.session))))

    @_bank.command()
    async def total_taxed_prod(self, interaction: discord.Interaction):
        """Total revenue for nations with 75/75 or higher tax"""
        await interaction.response.defer()
        # lookup tax bracket ids
        tax_bracket_data = await tax_bracket_query.query(self.bot.session, alliance_id=config.alliance_id)
        tax_brackets = [b['id'] for b in tax_bracket_data['data'][0]['tax_brackets']
                        if b['tax_rate'] >= 75 and b['resource_tax_rate'] >= 75]
        nation_q = asyncio.create_task(nation_revenue_query.query(self.bot.session, tax_ids=tax_brackets))
        treasure_q = asyncio.create_task(treasures_query.query(self.bot.session))
        colour_data = await colours_query.query(self.bot.session)
        treasure_data = await treasure_q
        total = sum((pnwutils.models.Nation(nation).revenue(
            colour_data, pnwutils.formulas.treasure_bonus(treasure_data, nation['id'], nation['alliance_id'])
        ) for nation in (await nation_q)['data']), pnwutils.Resources())
        await interaction.followup.send(embed=total.create_embed(
            title='Total revenue for nations with 75/75 or higher tax'))

    @_bank.command()
    @discord.app_commands.describe(
        nation_id='Nation the withdrawal link is for',
        alliance_id='Alliance to withdraw from, the alliance by default')
    async def create_withdrawal_link(self, interaction: discord.Interaction,
                                     nation_id: discord.app_commands.Range[int, 1, None],
                                     alliance_id: discord.app_commands.Range[int, 1, None] = None):
        """Make a withdrawal link for withdrawing some amount of resources"""
        res_select_view = finance_views.ResourceSelectView(keep_interaction=True)
        await interaction.response.send_message(view=res_select_view, ephemeral=True)
        modal = finance_views.ResourceAmountModal('Withdrawal Link Resource Amounts', await res_select_view.result())
        await res_select_view.interaction.response.send_modal(modal)
        resources = await modal.result()
        await modal.interaction.response.send_message(view=discordutils.LinkView(
            'Withdrawal Link', pnwutils.link.bank(
                'w', resources,
                (await leader_name_query.query(self.bot.session, nation_id=nation_id))['data'][0]['leader_name'],
                alliance_id=alliance_id
            )
        ))
