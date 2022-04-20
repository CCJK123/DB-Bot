import asyncio
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord import commands
from discord.ext import commands as cmds, pages

from utils import financeutils, discordutils, pnwutils, config, dbbot
from utils.queries import (bank_transactions_query, bank_info_query, nation_name_query, alliance_name_query,
                           nation_resources_query, bank_revenue_query)
if TYPE_CHECKING:
    from cogs.finance import FinanceCog


class BankCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.balances = discordutils.MappingProperty[str, pnwutils.ResourceDict](self, 'balances')
        # discord id : resources in dict form
        self.offshore_id = discordutils.CogProperty[str](self, 'offshore_id')

    @property
    def nations(self) -> discordutils.MappingProperty[int, int]:
        return self.bot.get_cog('UtilCog').nations

    @property
    def finance_cog(self) -> 'FinanceCog':
        return self.bot.get_cog('FinanceCog')  # type: ignore

    async def get_transactions(self, entity_id: 'str | int | None' = None,
                               kind: 'pnwutils.TransactionType | None' = None) -> list[pnwutils.Transaction]:
        if entity_id is None and kind is not None:
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
            if transaction.entity_id == entity_id and (kind is None or transaction.kind == kind):
                transactions.append(transaction)

        return transactions

    bank = commands.SlashCommandGroup('bank', 'Bank related commands!', guild_ids=config.guild_ids)

    @bank.command()
    async def balance(self, ctx: discord.ApplicationContext):
        """Check your bank balance"""
        # various data access
        await self.balances.initialise()

        resources = await self.balances[ctx.author.id].get(None)
        if resources is None:
            resources = pnwutils.Resources()
            await self.balances[ctx.author.id].set({})
        else:
            resources = pnwutils.Resources(**resources)

        loan = await self.finance_cog.loans[ctx.author.id].get(None)

        # actual displaying
        await ctx.respond(f"{ctx.author.mention}'s Balance",
                          embed=resources.create_balance_embed(ctx.author.display_name),
                          allowed_mentions=discord.AllowedMentions.none(),
                          ephemeral=True)
        if loan is not None:
            date = datetime.fromisoformat(loan["due_date"])
            await ctx.respond(
                f'You have a loan due {discord.utils.format_dt(date)} ({discord.utils.format_dt(date, "R")})',
                embed=pnwutils.Resources(**loan['resources']).create_embed(title='Loaned Resources'), ephemeral=True)

    @bank.command(guild_ids=config.guild_ids)
    @cmds.max_concurrency(1, cmds.BucketType.user)
    async def deposit(self, ctx: discord.ApplicationContext):
        """Deposit resources into your balance"""
        # various data access
        nation_id = await self.nations[ctx.author.id].get(None)
        if nation_id is None:
            await ctx.respond('Your nation id has not been set!', ephemeral=True)
            return

        await ctx.respond('Please check your DMs!', ephemeral=True)
        author = ctx.author
        msg_chk = discordutils.get_dm_msg_chk(author.id)

        # deposit check
        start_time = datetime.now()
        await author.send('You now have 5 minutes to deposit your resources into the bank. '
                          'Once you are done, send a message here.',
                          view=discordutils.LinkView('Deposit Link', pnwutils.link.bank('d', note='Deposit to balance'))
                          )
                          
        await author.send('test')
        try:
            await self.bot.wait_for(
                'message',
                check=msg_chk,
                timeout=300)
        except asyncio.TimeoutError:
            await author.send('You have not responded for 5 minutes! '
                              'Automatically checking for deposits...')

        # get balance
        resources = await self.balances[ctx.author.id].get(None)
        if resources is None:
            resources = pnwutils.Resources()
            await self.balances[ctx.author.id].set({})
        else:
            resources = pnwutils.Resources(**resources)

        # get transactions since start_time involving deposits by nation
        dep_transactions = list(filter(lambda t: t.time >= start_time,
                                       await self.get_transactions(nation_id, pnwutils.TransactionType.dep)))
        if dep_transactions:
            for transaction in dep_transactions:
                resources += transaction.resources.floor_values()
            await self.balances[ctx.author.id].set(resources.to_dict())
            await author.send('Your balance is now:', embed=resources.create_balance_embed(author.display_name))
            return
        await author.send('You did not deposit any resources! Aborting!')

    @bank.command(guild_ids=config.guild_ids)
    @cmds.max_concurrency(1, cmds.BucketType.user)
    async def withdraw(self, ctx: discord.ApplicationContext):
        """Withdraw resources from your balance"""
        nation_id = await self.nations[ctx.author.id].get(None)
        if nation_id is None:
            await ctx.respond('Your nation id has not been set!', ephemeral=True)
            return

        channel = self.bot.get_cog_from_class(FinanceCog).withdrawal_channel  # type: ignore
        if (channel := await channel.get(None)) is None:
            await ctx.respond('Output channel has not been set! Aborting...')
            return None

        resources = await self.balances[ctx.author.id].get(None)

        if resources is None:
            await self.balances[ctx.author.id].set({})
            await ctx.respond('You do not have anything to withdraw! Aborting...', ephemeral=True)
            return

        resources = pnwutils.Resources(**resources)

        if not resources:
            await ctx.respond('You do not have anything to withdraw! Aborting...', ephemeral=True)
            return

        await ctx.respond('Please check your DMs!', ephemeral=True)
        author = ctx.author

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
                    await author.send('You must withdraw at more than 0 of this resource! Please try again.')
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

        data = await nation_name_query.query(self.bot.session, nation_id=nation_id)
        name = data['data'][0]['nation_name']
        link = pnwutils.link.bank('w', req_resources, name, 'Withdrawal from balance')

        view = financeutils.WithdrawalView('withdrawal_on_sent', link, author.id, req_resources, reason)

        msg = await channel.send(f'Withdrawal Request from {author.mention}',
                                 embed=financeutils.withdrawal_embed(name, nation_id, reason, req_resources,
                                                                     colour=discord.Colour.blue()),
                                 allowed_mentions=discord.AllowedMentions.none(),
                                 view=view)
        await self.bot.add_view(view, message_id=msg.id)

        res = resources - req_resources
        await self.balances[ctx.author.id].set(res.to_dict())
        await author.send('Your withdrawal request has been sent. '
                          'It will be sent to your nation shortly.')

    @deposit.error
    @withdraw.error
    async def on_error(self, ctx: discord.ApplicationContext,
                       error: discord.ApplicationCommandError) -> None:
        if isinstance(error, cmds.MaxConcurrencyReached):
            await ctx.respond('You are already trying to withdraw/deposit!', ephemeral=True)
            return

        await discordutils.default_error_handler(ctx, error)

    loan = bank.create_subgroup('loan', 'Commands related to loans')
    loan.guild_ids = config.guild_ids

    @loan.command(name='return', guild_ids=config.guild_ids)
    async def _return(self, ctx: discord.ApplicationContext):
        """Return your loan using resources from your balance, if any"""
        nation_id = await self.nations[ctx.author.id].get(None)
        if nation_id is None:
            await ctx.respond('Your nation id has not been set!', ephemeral=True)
        loans = self.finance_cog.loans
        loan = await loans[ctx.author.id].get(None)
        if loan is None:
            await ctx.respond("You don't have an active loan!", ephemeral=True)
            return
        loan = financeutils.LoanData(**loan)
        bal = self.balances[ctx.author.id]
        res = pnwutils.Resources(**await bal.get())
        res -= loan.resources
        if res.all_positive():
            await bal.set(res.to_dict())
            await loans[ctx.author.id].delete()
            await ctx.respond('Your loan has been successfully repaid!', ephemeral=True)
            await ctx.respond('Your balance is now:', embed=res.create_balance_embed(ctx.author.mention))

            return
        await ctx.respond('You do not have enough resources to repay your loan.', ephemeral=True,
                          embed=loan.resources.create_embed(title=f"{ctx.author.mention}'s Loan"))

    @loan.command(guild_ids=config.guild_ids)
    async def status(self, ctx: discord.ApplicationContext):
        """Check the current status of your loan, if any"""

        loan = await self.bot.get_cog_from_class(self.finance_cog).loans[ctx.author.id].get(None)
        if loan is None:
            await ctx.respond("You don't have an active loan!", ephemeral=True)
            return
        await ctx.respond(embed=financeutils.LoanData(**loan).to_embed(), ephemeral=True)

    @commands.user_command(name='bank transfer', guild_ids=config.guild_ids)
    async def transfer(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Transfer some of your balance to someone else"""
        if member == ctx.author:
            await ctx.respond('You cannot transfer resources to yourself!')
            return
        nation_id_t = await self.nations[ctx.author.id].get(None)
        if nation_id_t is None:
            await ctx.respond('Your nation id has not been set!', ephemeral=True)
            return
        nation_id_r = await self.nations[member.id].get(None)
        if nation_id_r is None:
            await ctx.respond("The recipient's nation id has not been set!", ephemeral=True)
            return
        bal_r = self.balances[member.id]
        resources = await self.balances[ctx.author.id].get(None)

        if resources is None:
            await self.balances[ctx.author.id].set({})
            await ctx.respond('You do not have anything to transfer! Aborting...', ephemeral=True)
            return

        resources = pnwutils.Resources(**resources)

        if not resources:
            await ctx.respond('You do not have anything to transfer! Aborting...', ephemeral=True)
            return

        await ctx.respond('Please check your DMs!', ephemeral=True)
        author = ctx.author

        res_select_view = financeutils.ResourceSelectView(author.id, resources.keys_nonzero())
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
                if amt > resources[res]:
                    await author.send(f'You cannot transfer that much {res}! You only have {resources[res]:,} {res}!')
                    continue

                break
            t_resources[res] = amt
        if not t_resources:
            await author.send('You cannot transfer nothing! Aborting...')
            return
        resources_f_t = resources - t_resources
        resources_f_r = pnwutils.Resources(**await bal_r.get()) + t_resources
        await self.balances[author.id].set(resources_f_t.to_dict())
        await bal_r.set(resources_f_r.to_dict())
        await author.send(f'You have sent {member.display_name} [{t_resources}]!')
        await author.send('Your balance is now:', embed=resources_f_t.create_balance_embed(author.display_name))
        await member.send(f'You have been transferred [{t_resources}] from {author.display_name}!')
        await member.send('Your balance is now:', embed=resources_f_r.create_balance_embed(member.display_name))

    @commands.user_command(name='check balance', guild_ids=config.guild_ids, default_permission=False)
    @commands.has_role(config.bank_gov_role_id, guild_id=config.guild_id)
    async def check_bal(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Check the bank balance of this member"""
        resources = await self.balances[member.id].get(None)
        if resources is None:
            resources = pnwutils.Resources()
            await self.balances[member.id].set({})
        else:
            resources = pnwutils.Resources(**resources)
        await ctx.respond(
            f"{member.mention}'s Balance",
            embed=resources.create_balance_embed(member.display_name),
            allowed_mentions=discord.AllowedMentions.none(),
            ephemeral=True
        )

    @commands.user_command(name='check resources', guild_ids=config.guild_ids, default_permission=False)
    @commands.has_role(config.bank_gov_role_id, guild_id=config.guild_id)
    async def check_res(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Check the resources this member has"""
        nation_id = await self.nations[member.id].get(None)
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
                                       default_permission=False, permissions=[config.bank_gov_role_permission])

    @_bank.command(guild_ids=config.guild_ids, default_permission=False)
    async def loan_list(self, ctx: discord.ApplicationContext):
        """List all the loans that are currently active"""
        loans = await self.finance_cog.loans.get()
        if loans:
            paginator_pages = []
            for chunk in discord.utils.as_chunks(loans, 10):
                embeds = []
                for d in chunk:
                    loan = loans[d]
                    due_date = discord.utils.format_dt(datetime.fromisoformat(loans['due_date']))
                    embeds.append(pnwutils.Resources(**loan['resources']).create_embed(
                        title=f"<@{d}>'s Loan due on {due_date}"))
                paginator_pages.append(embeds)
            paginator = pages.Paginator(paginator_pages, timeout=config.timeout)
            await paginator.respond(ctx.interaction)
        await ctx.respond('There are no active loans!', ephemeral=True)

    @_bank.command(guild_ids=config.guild_ids, default_permission=False)
    async def contents(self, ctx: discord.ApplicationContext,
                       adjusted: commands.Option(bool, 'Whether to adjust for balances held by members',
                                                 default=False)):
        """Check the current contents of the bank"""
        data = await bank_info_query.query(self.bot.session, alliance_id=config.alliance_id)
        resources = pnwutils.Resources(**data['data'].pop())
        if adjusted:
            resources -= await self.get_total_balances()
        await ctx.respond(embed=resources.create_embed(title=f'{config.alliance_name} Bank'), ephemeral=True)

    @_bank.command(guild_ids=config.guild_ids, default_permission=False)
    async def safekeep(self, ctx: discord.ApplicationContext):
        """Get a link to send the entire bank to an offshore"""
        off_id = await self.offshore_id.get(None)
        if off_id is None:
            await ctx.respond('Offshore alliance has not been set!', ephemeral=True)
            return

        data = await bank_info_query.query(self.bot.session, alliance_id=config.alliance_id)
        resources = pnwutils.Resources(**data['data'].pop())

        try:
            aa_name = (await alliance_name_query.query(self.bot.session, alliance_id=off_id))['data'][0]['name']
        except IndexError:
            # failed on trying to access 0th elem, list is empty
            await ctx.respond(f'It appears an alliance with the set ID {off_id} does not exist! '
                              'Is the offshore ID outdated?', ephemeral=True)
            return

        view = discordutils.MultiLinkView({f'Withdrawal Link {i + 1}': link for i, link in enumerate(
            pnwutils.link.bank_split_link('wa', resources, aa_name, 'Safekeeping'))})
        await ctx.respond('Safekeeping Link', view=view, ephemeral=True)

    async def get_total_balances(self) -> pnwutils.Resources:
        balances = await self.balances.get()
        return sum((pnwutils.Resources(**bal) for bal in balances.values()), pnwutils.Resources())

    @_bank.command(guild_ids=config.guild_ids, default_permission=False)
    async def balances_total(self, ctx: discord.ApplicationContext):
        """Find the total value of all balances"""
        total = await self.get_total_balances()
        await ctx.respond(embed=total.create_embed(title=f'Total Balances Value'), ephemeral=True)

    @_bank.command(guild_ids=config.guild_ids, default_permission=False)
    async def revenue(self, ctx: discord.ApplicationContext):
        """Find the resources generated by taxes last turn"""
        await ctx.defer()
        data = await bank_revenue_query.query(self.bot.session, alliance_id=config.alliance_id)
        tax_records = data['data'][0]['taxrecs']
        first_date = datetime.fromisoformat(tax_records[0]['date']).replace(minute=0, second=0, microsecond=0)
        total = pnwutils.Resources()
        for tax_rec in tax_records:
            if datetime.fromisoformat(tax_rec['date']) < first_date:
                break
            total += pnwutils.Resources.from_dict(tax_rec)
        await ctx.respond(embed=total.create_embed(title='Tax Revenue from Last Turn'), ephemeral=True)

    @_bank.command(guild_ids=config.guild_ids, default_permission=False)
    async def edit(self, ctx: discord.ApplicationContext, member: discord.Member):
        """Manually edit the resource values of someone's balance"""
        await ctx.respond('Please check your DMs!', ephemeral=True)

        author = ctx.author
        res_select_view = financeutils.ResourceSelectView(author.id)
        kind_view = discordutils.Choices('Set', 'Adjust')
        await author.send('Do you wish to set or adjust the balance?', view=kind_view)
        adjust = await kind_view.result() == 'Adjust'
        text = 'adjust' if adjust else 'set'
        msg_chk = discordutils.get_dm_msg_chk(author.id)
        await author.send(f'What resources would you like to {text}?', view=res_select_view)

        resources = await self.balances[ctx.author.id].get(None)
        if resources is None:
            resources = pnwutils.Resources()
            await self.balances[ctx.author.id].set({})
        else:
            resources = pnwutils.Resources(**resources)

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

        await self.balances[ctx.author.id].set(resources.to_dict())
        await author.send(f'The balance of {member.mention} has been modified!',
                          embed=resources.create_balance_embed(member.mention),
                          allowed_mentions=discord.AllowedMentions.none())


def setup(bot: dbbot.DBBot):
    bot.add_cog(BankCog(bot))

    @financeutils.WithdrawalView.register_callback('withdrawal_on_sent')
    async def on_sent(label: str, interaction: discord.Interaction, requester_id: int,
                      req_res: pnwutils.Resources, reason: str):
        if label == 'Sent':
            await bot.get_user(requester_id).send(
                'Your withdrawal request has been sent to your nation!',
                embed=req_res.create_embed(title='Withdrawn Resources'))
            embed = interaction.message.embeds[0]
            embed.colour = discord.Colour.green()
            await interaction.message.edit(embed=embed)
        else:
            bank_cog = bot.get_cog_from_class(BankCog)
            assert isinstance(bank_cog, BankCog)
            bal = bank_cog.balances[requester_id]
            await bal.set((pnwutils.Resources(**await bal.get()) + req_res).to_dict())
            await interaction.user.send(
                f'What was the reason for rejecting the withdrawal request for `{reason}`?'
            )

            def msg_chk(m: discord.Message) -> bool:
                return m.author == interaction.user and m.guild is None

            try:
                reject_reason: str = (await bot.wait_for(
                    'message', check=msg_chk,
                    timeout=config.timeout)).content
            except asyncio.TimeoutError():
                await interaction.user.send('You took too long to respond! Default rejection reason set.')
                reject_reason = 'not given'
            await bot.get_user(requester_id).send(
                f'Your withdrawal request for `{reason}` '
                f'has been rejected!\nReason: `{reject_reason}`')
            embed = interaction.message.embeds[0]
            embed.add_field(name='Rejection Reason', value=reject_reason, inline=True)
            embed.colour = discord.Colour.green()
            await interaction.message.edit(embed=embed)
