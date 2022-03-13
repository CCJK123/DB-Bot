import asyncio
import logging
import datetime
from typing import Any

import discord
from discord import commands
from discord.ext import commands as cmds

from utils import discordutils, pnwutils, config
from utils.financeutils import RequestData, LoanData, RequestStatus, RequestChoices, ResourceSelectView, WithdrawalView
from utils.queries import nation_query
import dbbot

logger = logging.getLogger(__name__)


# Create Finance Cog to group finance related commands
class FinanceCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.has_war_aid = discordutils.CogProperty[bool](self, 'has_war_aid')
        self.infra_rebuild_cap = discordutils.CogProperty[int](self, 'infra_rebuild_cap')
        self.process_channel = discordutils.ChannelProperty(self, 'process_channel')
        self.withdrawal_channel = discordutils.ChannelProperty(self, 'withdraw_channel')
        self.loans = discordutils.MappingProperty[int, dict[str, Any]](self, 'loans')

    @property
    def nations(self) -> discordutils.MappingProperty[int, str]:
        return self.bot.get_cog('UtilCog').nations  # type: ignore

    # Main request command
    @commands.command(guild_ids=config.guild_ids)
    @cmds.max_concurrency(1, cmds.BucketType.user)
    async def request(self, ctx: discord.ApplicationContext) -> None:
        """Request for a grant, loan, or war aid (if enabled) from the bank."""
        await self.loans.initialise()
        # Command Run Validity Check
        # Check if output channel has been set
        if await self.process_channel.get(None) is None or await self.withdrawal_channel.get(None) is None:
            await ctx.respond('Output channel has not been set! Aborting...')
            return

        nation_id = await self.nations[ctx.author.id].get(None)
        if nation_id is None:
            await ctx.respond('Your nation id has not been set! Aborting...', ephemeral=True)
            return

        await ctx.respond('Please check your DMs!', ephemeral=True)

        author = ctx.author
        await author.send('Welcome to the DB Finance Request Interface.')

        # Check that reply was sent from same author in DMs
        msg_chk = discordutils.get_dm_msg_chk(author.id)

        data = await nation_query.query(self.bot.session, nation_id=nation_id)
        data = data['data']
        if data:
            # Data contains a nation, hence nation with given id exists
            data = data.pop()
            req_data = RequestData(author, nation_id, data['nation_name'])
        else:
            # Data has no nation, hence no nation with given id exists
            await author.send(
                "You do not have a valid nation id set!"
                'Please set your nation id again.'
            )
            return

        # Get Request Type
        req_types = ['Grant', 'Loan']
        if await self.has_war_aid.get():
            req_types.append('War Aid')

        req_type_choice = discordutils.Choices(*req_types)
        await author.send('What kind of request is this?', view=req_type_choice)
        try:
            req_data.kind = await req_type_choice.result()
        except asyncio.TimeoutError:
            await author.send('You took too long to respond! Exiting...')
            return

        # Redirect Accordingly
        if req_data.kind == 'Grant':
            grant_type_choice = discordutils.Choices('City', 'Project', 'Other')
            await author.send('What type of grant do you want?',
                              view=grant_type_choice)
            try:
                grant_type = await grant_type_choice.result()
            except asyncio.TimeoutError:
                await author.send('You took too long to respond! Exiting...')
                return

            if grant_type == 'City':
                # Get data of projects which affect city cost
                has_up = data['city_planning']
                has_aup = data['adv_city_planning']
                # Calculate city cost
                req_data.resources = pnwutils.Resources(
                    money=(50000 * (data['num_cities'] - 1) ** 3 +
                           150000 * data['num_cities'] + 75000 -
                           50000000 * has_up - 100000000 * has_aup) // 20 * 19)
                # Create embed
                project_string = ('Urban Planning' * has_up + ' and ' * (has_up and has_aup) +
                                  'Advanced Urban Planning' * has_aup) or 'None'
                req_data.reason = f'City {data["num_cities"] + 1}'
                req_data.note = f'{req_data.reason} Grant'
                req_data.additional_info = {'Projects': project_string}
                await self.on_request_fixed(req_data)
                return None

            elif grant_type == 'Project':
                project_field_names = {
                    'Center for Civil Engineering': 'cfce',
                    'Intelligence Agency': 'cia',
                    'Propaganda Bureau': 'propb',
                    'Urban Planning': 'city_planning',
                    'Advanced Urban Planning': 'adv_city_planning',
                    'Other': 'other'
                }
                data['other'] = None
                disabled = set()
                for label, field in project_field_names.items():
                    if data[field]:
                        disabled.add(label)

                project_choice = discordutils.Choices(*project_field_names.keys(), disabled=disabled)
                await author.send('Which project do you want?', view=project_choice)

                try:
                    project = await project_choice.result()
                except asyncio.TimeoutError:
                    await author.send('You took too long to respond! Exiting...')
                    return

                # Redirect accordingly
                if project == 'Center for Civil Engineering':
                    req_data.resources = pnwutils.Resources(oil=1000,
                                                            iron=1000,
                                                            bauxite=1000,
                                                            money=3000000)
                elif project == 'Intelligence Agency':
                    req_data.resources = pnwutils.Resources(steel=500,
                                                            gasoline=500,
                                                            money=5000000)
                elif project == 'Propaganda Bureau':
                    req_data.resources = pnwutils.Resources(aluminum=1500, money=15000000)
                elif project == 'Urban Planning':
                    if data['num_cities'] < 11:
                        await author.send(
                            'The Urban Planning project requires 11 cities to build, however you only have '
                            f'{data["num_cities"]} cities. Please try again next time.'
                        )
                        return None
                    else:
                        req_data.resources = pnwutils.Resources(coal=10000,
                                                                oil=10000,
                                                                aluminum=20000,
                                                                munitions=10000,
                                                                gasoline=10000,
                                                                food=1000000)
                elif project == 'Advanced Urban Planning':
                    if not data['city_planning']:
                        await author.send(
                            'You have not built the Urban Planning project, which is needed to build the Advanced '
                            'Urban Planning project. Please try again next time.'
                        )
                        return None
                    elif data['num_cities'] < 16:
                        await author.send(
                            'The Advanced Urban Planning project requires 16 cities to build, however you only have '
                            f'{data["num_cities"]} cities. Please try again next time.'
                        )
                        return None
                    else:
                        req_data.resources = pnwutils.Resources(uranium=10000,
                                                                aluminum=40000,
                                                                steel=20000,
                                                                munitions=20000,
                                                                food=2500000)
                else:
                    await author.send(
                        'Other projects are not eligible for grants. Kindly request for a loan.'
                    )
                    return None
                req_data.reason = project
                req_data.note = f'{project} Project Grant'
                await self.on_request_fixed(req_data)
                return None

            else:
                await author.send(
                    'Other Grants have not been implemented! Please try again next time.'
                )
                return None

        elif req_data.kind == 'Loan':
            if await self.loans[req_data.requester_id].get(False):
                await author.send('You already have an active loan! Repay that before requesting another.')
                return
            await author.send('What are you requesting a loan for?')
            try:
                # Wait for user to input loan request
                req_data.reason = (await self.bot.wait_for(
                    'message',
                    check=msg_chk,
                    timeout=config.timeout)).content
            except asyncio.TimeoutError:
                await author.send('You took too long to reply. Aborting request!'
                                  )
                return None

            res_select_view = ResourceSelectView()
            await author.send('What resources are you requesting?', view=res_select_view)
            try:
                selected_res = await res_select_view.result()
            except asyncio.TimeoutError:
                await author.send('You took too long to respond! Exiting...')
                return
            for res_name in selected_res:
                await author.send(f'How much {res_name} are you requesting?')
                while True:
                    try:
                        # Wait for user to input how much of each res they want
                        res_amt = int((await self.bot.wait_for(
                            'message',
                            check=msg_chk,
                            timeout=config.timeout)).content)
                        if res_amt > 0:
                            req_data.resources[res_name] = res_amt
                        break
                    except ValueError:
                        await author.send('Kindly input a whole number.')
                        continue
                    except asyncio.TimeoutError:
                        await author.send('You took too long to reply. Aborting request!')
                        return

            # Ensure that user didn't request for nothing
            if req_data.resources:
                req_data.note = f'{req_data.reason.title()} Loan'
                await self.on_request_fixed(req_data)
                return
            else:
                # No resources requested
                await author.send(
                    "You didn't request for any resources. Please run the command again and redo your request."
                )
                return

        elif req_data.kind == 'War Aid':
            war_aid_type_choice = discordutils.Choices(
                'Buy Military Units', 'Rebuild Military Improvements',
                'Rebuild Infrastructure', 'Various Resources'
            )
            await author.send('What type of war aid are you requesting?',
                              view=war_aid_type_choice)
            try:
                war_aid_type = await war_aid_type_choice.result()
            except asyncio.TimeoutError:
                await author.send('You took too long to respond! Exiting...')
                return
            req_data.additional_info = {
                'Beige Turns': data['beigeturns'],
                'Active Wars': f'''
                    Offensive: {sum(w["turnsleft"] > 0 for w in data["offensive_wars"])}
                    Defensive: {sum(w["turnsleft"] > 0 for w in data["defensive_wars"])}
                '''
                # fsr the value of turnsleft when war is over seems to be always -12? idk
                # maybe its diff for wars that ended recently? did not check
            }

            if war_aid_type == 'Buy Military Units':
                # Calculate amount of military units needed
                needed_units = {
                    # Capacity per improvement * max improvements * city count - existing units
                    'soldiers': 3000 * 5 * data['num_cities'] - data['soldiers'],
                    'tanks': 250 * 5 * data['num_cities'] - data['tanks'],
                    'aircraft': 15 * 5 * data['num_cities'] - data['aircraft'],
                    'ships': 5 * 3 * data['num_cities'] - data['ships']
                }
                await author.send(
                    f'To get to max military units, you will need an additional {needed_units["soldiers"]} soldiers, '
                    f'{needed_units["tanks"]} tanks, {needed_units["aircraft"]} aircraft and '
                    f'{needed_units["ships"]} ships.'
                )
                # Calculate resources needed to buy needed military units
                req_data.resources = pnwutils.Resources(
                    money=5 * needed_units['soldiers'] + 60 * needed_units['tanks'] + 4000 * needed_units['aircraft']
                    + 50000 * needed_units['ships'],
                    steel=int(0.5 * (needed_units['tanks']) + 1) + 30 * needed_units['ships'],
                    aluminum=5 * needed_units['aircraft']
                )
                req_data.reason = 'Buy up to Max Military Units'
                req_data.note = f'War Aid to {req_data.reason}'
                await self.on_request_fixed(req_data)
                return

            elif war_aid_type == 'Rebuild Military Improvements':
                # Calculate amount of military improvements needed
                needed_improvements = {
                    'barracks': 5 * data['num_cities'],
                    'factory': 5 * data['num_cities'],
                    'airforcebase': 5 * data['num_cities'],
                    'drydock': 3 * data['num_cities']
                }
                for city in data['cities']:
                    for improvement in needed_improvements.keys():
                        needed_improvements[improvement] -= city[improvement]

                await author.send(
                    f'To get to max military improvements, you require an additional {needed_improvements["barracks"]} '
                    f'barracks, {needed_improvements["factory"]} factories, {needed_improvements["airforcebase"]} '
                    f'hangars and {needed_improvements["drydock"]} drydocks.'
                )
                # Calculate resources needed to buy needed military improvements
                req_data.resources = pnwutils.Resources(
                    money=3000 * needed_improvements['barracks'] + 15000 * needed_improvements['factory'] +
                    100000 * needed_improvements['airforcebase'] + 250000 * needed_improvements['drydock'],
                    steel=10 * needed_improvements['airforcebase'],
                    aluminum=5 * needed_improvements['factory'] + 20 * needed_improvements['drydock'])

                req_data.reason = 'Rebuild to Max Military Improvements'
                req_data.note = f'War Aid to {req_data.reason}'
                await self.on_request_fixed(req_data)
                return

            elif war_aid_type == 'Rebuild Infrastructure':
                irc = await self.infra_rebuild_cap.get()
                await author.send(
                    f'The current infrastructure rebuild cap is set at {irc}. '
                    f'This means that money will only be provided to rebuild infrastructure below {irc} up to that '
                    'amount. The amount calculated assumes that domestic policy is set to Urbanisation.'
                )
                # Calculate infra cost for each city
                for city in data['cities']:
                    if city['infrastructure'] < irc:
                        req_data.resources.money += pnwutils.infra_price(city['infrastructure'], irc)
                # Account for Urbanisation and cost reducing projects (CCE and AEC)
                req_data.resources.money *= 0.95 - 0.05 * (data['cfce'] +
                                                           data['adv_engineering_corps'])
                req_data.resources.money = int(req_data.resources.money + 0.5)
                # Check if infrastructure in any city under cap
                if req_data.resources.money == 0:
                    await author.send(
                        'Since all your cities have an infrastructure level above '
                        f'the current infrastructure rebuild cap ({irc}), you are '
                        'not eligible for war aid to rebuild infrastructure.'
                    )
                    return

                req_data.reason = f'Rebuild Infrastructure up to {irc}'
                req_data.note = f'War Aid to {req_data.reason}'
                await self.on_request_fixed(req_data)
                return
            else:
                await author.send('Why are you requesting these various resources?')
                try:
                    # Wait for user to input loan request
                    req_data.reason = (await self.bot.wait_for(
                        'message',
                        check=msg_chk,
                        timeout=config.timeout)).content
                except asyncio.TimeoutError:
                    await author.send('You took too long to reply. Aborting request!')
                    return

                res_select_view = ResourceSelectView()
                await author.send('What resources are you requesting?', view=res_select_view)
                try:
                    selected_res = await res_select_view.result()
                except asyncio.TimeoutError:
                    await author.send('You took too long to respond! Exiting...')
                    return
                for res_name in selected_res:
                    await author.send(f'How much {res_name} are you requesting?')
                    while True:
                        try:
                            # Wait for user to input how much of each res they want
                            res_amt = int((await self.bot.wait_for(
                                'message',
                                check=msg_chk,
                                timeout=config.timeout)).content)
                            if res_amt > 0:
                                req_data.resources[res_name] = res_amt
                            break
                        except ValueError:
                            await author.send('Kindly input a whole number.')
                            continue
                        except asyncio.TimeoutError:
                            await author.send(
                                'You took too long to reply. Aborting request!')
                            return

                # Ensure that user didn't request for nothing
                if req_data.resources:
                    req_data.note = f'War Aid to {req_data.reason}'
                    await self.on_request_fixed(req_data)
                    return
                else:
                    # No resources requested
                    await author.send(
                        "You didn't request for any resources. Please run the command again and redo your request."
                    )
                    return

    async def on_request_fixed(self, req_data: RequestData) -> None:
        auth = req_data.requester
        agree_terms = discordutils.Choices('Yes', 'No')
        await auth.send(
            'Do you agree to return the money and/or resources in a timely manner in the event that you leave the '
            'alliance / get kicked from the alliance for inactivity or other reasons?', view=agree_terms)
        try:
            if await agree_terms.result() == 'No':
                await auth.send('Exiting the DB Finance Request Interface.')
                return None
        except asyncio.TimeoutError:
            auth.send('You took too long to respond! Exiting...')
            return

        embed = req_data.create_embed(title='Please confirm your request.')
        confirm_request_choice = discordutils.Choices('Yes', 'No')
        await auth.send('Is this your request?',
                        embed=embed,
                        view=confirm_request_choice)
        try:
            confirmed = await confirm_request_choice.result() == 'Yes'
        except asyncio.TimeoutError:
            await auth.send('You took too long to respond! Exiting...')
            return
        if confirmed:
            logger.info(f'request sent: {req_data}')
            await auth.send(
                'Your request has been sent. Thank you for using the DB Finance Request Interface.'
            )
            embed.title = None
            process_view = RequestChoices('on_processed', req_data)

            msg = await (await self.process_channel.get()).send(
                f'New Request from {auth.mention}',
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
                view=process_view
            )
            await self.bot.add_view(process_view, message_id=msg.id)

            return

        await auth.send(
            'Exiting the DB Finance Request Interface. Please run the command again and redo your request.'
        )

    @request.error
    async def request_error(self, ctx: discord.ApplicationContext,
                            error: discord.ApplicationCommandError) -> None:
        if isinstance(error, cmds.MaxConcurrencyReached):
            await ctx.respond('You are already making a request!')
            return
        await discordutils.default_error_handler(ctx, error)


# Setup Finance Cog as an extension
def setup(bot: dbbot.DBBot) -> None:
    bot.add_cog(FinanceCog(bot))

    @RequestChoices.register_callback('on_processed', FinanceCog.__cog_name__)
    async def on_processed(cog_name: str, status: RequestStatus,
                           interaction: discord.Interaction, req_data: RequestData) -> None:
        cog: FinanceCog = bot.get_cog(cog_name)  # type: ignore
        logger.info(f'processing {status} request: {req_data}')
        req_data.set_requester(bot)
        if status == RequestStatus.ACCEPTED:
            if req_data.kind == 'Loan':
                data = LoanData(datetime.datetime.now() + datetime.timedelta(days=30), req_data.resources)
                await req_data.requester.send(
                    'The loan has been added to your bank balance. '
                    'You will have to use `bank withdraw` to withdraw the loan from your bank balance to your nation. '
                    'Kindly remember to return the requested resources by depositing it back into your bank balance '
                    'and using `bank loan return` by '
                    f'<t:{int(data.due_date.timestamp())}:R>. '
                    'You can check your loan status with `bank loan status`.'
                )
                bal = bot.get_cog('BankCog').balances[req_data.requester_id]
                if (res_dict := await bal.get(None)) is None:
                    res = pnwutils.Resources()
                else:
                    res = pnwutils.Resources(**res_dict)
                await bal.set((res + req_data.resources).to_dict())

                await interaction.message.edit(embed=interaction.message.embeds[0].add_field(
                    name='Return By',
                    value=data.display_date,
                    inline=True))
                await cog.loans[req_data.requester_id].set(data.to_dict())
            else:
                await req_data.requester.send(
                    f'Your {req_data.kind} request for `{req_data.reason}` '
                    'has been accepted! The resources will be sent to you soon. '
                )
                channel = await cog.withdrawal_channel.get()
                withdrawal_view = WithdrawalView('request_on_sent', req_data.create_link(), req_data, can_reject=False)
                msg = await channel.send(f'Withdrawal Request from {req_data.requester.mention}',
                                         embed=req_data.create_withdrawal_embed(),
                                         view=withdrawal_view,
                                         allowed_mentions=discord.AllowedMentions.none())
                await bot.add_view(withdrawal_view, message_id=msg.id)

        else:
            await interaction.user.send(
                f'What was the reason for rejecting the {req_data.kind} request '
                f'for `{req_data.reason}`?'
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
            await req_data.requester.send(
                f'Your {req_data.kind} request for `{req_data.reason}`'
                f'has been rejected!\nReason: `{reject_reason}`')
            await interaction.message.edit(embed=interaction.message.embeds.pop().add_field(
                name='Rejection Reason', value=reject_reason, inline=True))

        await interaction.message.edit(
            content=f'{status.value} Request from {req_data.requester.mention}',
            allowed_mentions=discord.AllowedMentions.none())

    @WithdrawalView.register_callback('request_on_sent')
    async def on_sent(label: str, _: discord.Interaction, req_data: RequestData):
        assert label == 'Sent'
        await req_data.set_requester(bot).send(
            f'Your {req_data.kind} request for `{req_data.reason}` has been sent to your nation!'
        )
