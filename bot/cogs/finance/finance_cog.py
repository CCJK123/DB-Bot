from __future__ import annotations

import asyncio

import discord
from discord.ext import commands

from bot.utils import discordutils, pnwutils, config
from ... import dbbot
from bot.utils.queries import finance_nation_info_query

from . import finance_views


# Create Finance Cog to group finance related commands
class FinanceCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)

    # Main request command
    @discord.app_commands.command()
    @discordutils.max_one
    async def request(self, interaction: discord.Interaction) -> None:
        """Request for a grant, loan, or war aid (if enabled) from the bank"""
        # Command Run Validity Check -
        # Check if output channel has been set
        channel_ids_table = self.bot.database.get_kv('channel_ids')
        if not await channel_ids_table.all_set('process_channel', 'withdrawal_channel'):
            await interaction.response.send_message('Not all output channels have been set! Aborting...')
            return

        users_table = self.bot.database.get_table('users')
        nation_id: int = await users_table.select_val('nation_id').where(discord_id=interaction.user.id)
        if nation_id is None:
            await interaction.response.send_message('Your nation id has not been set! Aborting...', ephemeral=True)
            return

        user = interaction.user
        await asyncio.gather(
            interaction.response.send_message('Please check your DMs!', ephemeral=True),
            user.send('Welcome to the DB Finance Request Interface.'))

        # Check that reply was sent from same author in DMs
        msg_chk = discordutils.get_dm_msg_chk(user.id)

        data = await finance_nation_info_query.query(self.bot.session, nation_id=nation_id)
        data = data['data']
        if data:
            # Data contains a nation, hence nation with given id exists
            data = data.pop()
            req_data = finance_views.RequestData(user, nation_id, data['nation_name'])
        else:
            # Data has no nation, hence no nation with given id exists
            await user.send(
                "You do not have a valid nation id set!"
                'Please set your nation id again.'
            )
            return

        # Get Request Type
        req_types = ['Grant', 'Loan']
        if await self.bot.database.get_kv('kv_bools').get('has_war_aid'):
            req_types.append('War Aid')

        req_type_choice = discordutils.Choices(*req_types)
        await user.send('What kind of request is this?', view=req_type_choice)
        try:
            req_data.kind = await req_type_choice.result()
        except asyncio.TimeoutError:
            await user.send('You took too long to respond! Exiting...')
            return

        # Redirect Accordingly
        if req_data.kind == 'Grant':
            grant_type_choice = discordutils.Choices('City', 'Project', 'Various Resources', 'Other')
            await user.send('What type of grant do you want?',
                            view=grant_type_choice)
            try:
                grant_type = await grant_type_choice.result()
            except asyncio.TimeoutError:
                await user.send('You took too long to respond! Exiting...')
                return

            if grant_type == 'City':
                # Get data of projects which affect city cost
                has_up = data['urban_planning']
                has_aup = data['advanced_urban_planning']
                has_mp = data['metropolitan_planning']
                # Calculate city cost
                req_data.resources = pnwutils.Resources(
                    money=(
                            50000 * (data['num_cities'] - 1) ** 3 +
                            150000 * data['num_cities'] + 75000 -
                            50_000000 * has_up - 100_000000 * has_aup - 150_000000 * has_mp
                    )
                )
                if data['government_support_agency']:
                    req_data.resources //= 40
                    req_data.resources *= 37
                else:
                    req_data.resources //= 20
                    req_data.resources *= 19
                # Create embed

                project_string = ', '.join(
                    k for k, v in {
                        'Urban Planning': has_up,
                        'Advanced Urban Planning': has_aup,
                        'Metropolitan Planning': has_mp
                    }.items() if v) or 'None'
                req_data.reason = f'City {data["num_cities"] + 1}'
                req_data.note = f'{req_data.reason} Grant'
                req_data.additional_info = {'Projects': project_string, 'Domestic Policy': data['domestic_policy']}
                req_data.presets = {
                    'Half Amount': req_data.resources // 2
                }
                await self.on_request_fixed(req_data)
                return

            elif grant_type == 'Project':
                project_field_names = {
                    'Center for Civil Engineering': 'center_for_civil_engineering',
                    'Intelligence Agency': 'central_intelligence_agency',
                    'Propaganda Bureau': 'propaganda_bureau',
                    'Urban Planning': 'urban_planning',
                    'Advanced Urban Planning': 'advanced_urban_planning',
                    'Metropolitan Planning': 'metropolitan_planning',
                    'Missile Launch Pad': 'missile_launch_pad',
                    'Iron Dome': 'iron_dome',
                    'Vital Defense System': 'vital_defense_system',
                    'Research and Development Center': 'research_and_development_center',
                    'Space Program': 'space_program',
                    'Other': 'other'
                }
                data['other'] = None
                disabled = set()
                for label, field in project_field_names.items():
                    if data[field]:
                        disabled.add(label)
                if data['num_cities'] < 11:
                    disabled.add('Urban Planning')
                if data['num_cities'] < 16 or not data['urban_planning']:
                    disabled.add('Advanced Urban Planning')
                if data['num_cities'] < 21 or not data['advanced_urban_planning']:
                    disabled.add('Metropolitan Planning')
                project_choice = discordutils.Choices(*project_field_names.keys(), disabled=disabled)
                await user.send(
                    'Which project are you requesting a grant for? '
                    'Note that for many of these projects, we will require 100/100 or only do up to partial grants.',
                    view=project_choice)

                try:
                    project = await project_choice.result()
                except asyncio.TimeoutError:
                    await user.send('You took too long to respond! Exiting...')
                    return

                # Redirect accordingly
                if project == 'Other':
                    await user.send('Other projects are not eligible for grants. Kindly request for a loan.')
                    return

                project_field_name = project_field_names[project]
                req_data.resources = pnwutils.constants.project_costs[project_field_name].copy()
                if data['government_support_agency']:
                    req_data.resources //= 40
                    req_data.resources *= 37
                else:
                    req_data.resources //= 20
                    req_data.resources *= 19
                half = req_data.resources // 2
                presets = {
                    'center_for_civil_engineering': {},
                    'central_intelligence_agency': {},
                    'propaganda_bureau': {},
                    'urban_planning': {
                        'Half Everything': half
                    },
                    'advanced_urban_planning': {
                        'Half Everything': half
                    },
                    'metropolitan_planning': {
                        'Half Everything': half
                    }
                }

                req_data.presets = presets[project_field_name]
                req_data.reason = project
                req_data.note = f'{project} Project Grant'
                await self.on_request_fixed(req_data)
                return
            elif grant_type == 'Various Resources':
                await user.send('Why are you requesting these various resources?')
                try:
                    # Wait for user to input loan request
                    req_data.reason = (await self.bot.wait_for(
                        'message',
                        check=msg_chk,
                        timeout=config.timeout)).content
                except asyncio.TimeoutError:
                    await user.send('You took too long to reply. Aborting request!')
                    return

                res_select_view = finance_views.ResourceSelectView()
                await user.send('What resources are you requesting?', view=res_select_view)
                try:
                    selected_res = await res_select_view.result()
                except asyncio.TimeoutError:
                    await user.send('You took too long to respond! Exiting...')
                    return
                for res_name in selected_res:
                    await user.send(f'How much {res_name} are you requesting?')
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
                            await user.send('Kindly input a whole number.')
                            continue
                        except asyncio.TimeoutError:
                            await user.send(
                                'You took too long to reply. Aborting request!')
                            return

                # Ensure that user didn't request for nothing
                if req_data.resources:
                    req_data.note = 'Misc'
                    await self.on_request_fixed(req_data)
                    return
                else:
                    # No resources requested
                    await user.send(
                        "You didn't request for any resources. Please run the command again and redo your request."
                    )
                    return
            else:
                await user.send('Other Grants have not been implemented! Please try again next time.')
                return

        elif req_data.kind == 'Loan':
            if await self.bot.database.get_table('loans').exists(discord_id=user.id):
                await user.send('You already have an active loan! Repay that before requesting another.')
                return
            await user.send('What are you requesting a loan for?')
            try:
                # Wait for user to input loan request
                req_data.reason = (await self.bot.wait_for(
                    'message',
                    check=msg_chk,
                    timeout=config.timeout)).content
            except asyncio.TimeoutError:
                await user.send('You took too long to reply. Aborting request!')
                return

            res_select_view = finance_views.ResourceSelectView()
            await user.send('What resources are you requesting?', view=res_select_view)
            try:
                selected_res = await res_select_view.result()
            except asyncio.TimeoutError:
                await user.send('You took too long to respond! Exiting...')
                return
            for res_name in selected_res:
                await user.send(f'How much {res_name} are you requesting?')
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
                        await user.send('Kindly input a whole number.')
                        continue
                    except asyncio.TimeoutError:
                        await user.send('You took too long to reply. Aborting request!')
                        return

            # Ensure that user didn't request for nothing
            if req_data.resources:
                req_data.note = f'{req_data.reason.title()} Loan'
                await self.on_request_fixed(req_data)
                return
            else:
                # No resources requested
                await user.send(
                    "You didn't request for any resources. Please run the command again and redo your request."
                )
                return

        elif req_data.kind == 'War Aid':
            war_aid_type_choice = discordutils.Choices(
                'Buy Military Units', 'Rebuild Military Improvements',
                'Rebuild Infrastructure', 'Various Resources'
            )
            await user.send('What type of war aid are you requesting?',
                            view=war_aid_type_choice)
            try:
                war_aid_type = await war_aid_type_choice.result()
            except asyncio.TimeoutError:
                await user.send('You took too long to respond! Exiting...')
                return
            wars = data['wars']
            num_off = sum(war['att_id'] == nation_id for war in wars)
            req_data.additional_info = {
                'Beige Turns': data['beige_turns'],
                'Active Wars': f'''
                    Offensive: {num_off}
                    Defensive: {len(wars) - num_off}
                '''
                # fsr the value of turns_left when war is over seems to be always -12? I am not sure
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
                await user.send(
                    f'To get to max military units, you will need an additional {needed_units["soldiers"]} soldiers, '
                    f'{needed_units["tanks"]} tanks, {needed_units["aircraft"]} aircraft and '
                    f'{needed_units["ships"]} ships.'
                )
                # Calculate resources needed to buy needed military units
                req_data.resources = pnwutils.Resources(
                    money=(
                            5 * needed_units['soldiers'] + 60 * needed_units['tanks']
                            + 4000 * needed_units['aircraft'] + 50000 * needed_units['ships']),
                    steel=int(0.5 * (needed_units['tanks']) + 1) + 30 * needed_units['ships'],
                    aluminum=5 * needed_units['aircraft']
                )
                req_data.reason = 'Buy up to Max Military Units'
                req_data.note = 'War Aid'
                await self.on_request_fixed(req_data)
                return

            elif war_aid_type == 'Rebuild Military Improvements':
                # Calculate amount of military improvements needed
                needed_improvements = {
                    'barracks': 5 * data['num_cities'],
                    'factory': 5 * data['num_cities'],
                    'hangar': 5 * data['num_cities'],
                    'drydock': 3 * data['num_cities']
                }
                for city in data['cities']:
                    for improvement in needed_improvements.keys():
                        needed_improvements[improvement] -= city[improvement]

                await user.send(
                    f'To get to max military improvements, you require an additional {needed_improvements["barracks"]} '
                    f'barracks, {needed_improvements["factory"]} factories, {needed_improvements["hangar"]} '
                    f'hangars and {needed_improvements["drydock"]} drydocks.'
                )
                # Calculate resources needed to buy needed military improvements
                req_data.resources = pnwutils.Resources(
                    money=(
                            3000 * needed_improvements['barracks'] + 15000 * needed_improvements['factory'] +
                            100000 * needed_improvements['hangar'] + 250000 * needed_improvements['drydock']),
                    steel=10 * needed_improvements['hangar'],
                    aluminum=5 * needed_improvements['factory'] + 20 * needed_improvements['drydock'])

                req_data.reason = 'Rebuild to Max Military Improvements'
                req_data.note = 'War Aid'
                await self.on_request_fixed(req_data)
                return

            elif war_aid_type == 'Rebuild Infrastructure':
                await user.send('To what infra level would you request aid to rebuild to? Do note that '
                                'the money given would assume your domestic policy is Urbanisation.')
                while True:
                    try:
                        # Wait for user to input loan request
                        infra_level = (await self.bot.wait_for(
                            'message',
                            check=msg_chk,
                            timeout=config.timeout)).content
                    except asyncio.TimeoutError:
                        await user.send('You took too long to reply. Aborting request!')
                        return
                    try:
                        infra_level = int(infra_level)
                    except ValueError:
                        await user.send('That is not a number! Please try again.')
                        continue
                    if infra_level % 100:
                        await user.send('That is not a multiple of 100! Please try again.')
                        continue
                    break

                # Calculate infra cost for each city
                for city in data['cities']:
                    if city['infrastructure'] < infra_level:
                        req_data.resources.money += pnwutils.formulas.infra_price(city['infrastructure'], infra_level)
                # Account for Urbanisation and cost reducing projects (CCE and AEC)
                req_data.resources.money *= 0.95 - 0.05 * (data['center_for_civil_engineering'] +
                                                           data['advanced_engineering_corps'])
                req_data.resources.money = int(req_data.resources.money + 0.5)
                # Check if infrastructure in any city under cap
                if req_data.resources.money == 0:
                    await user.send(
                        'Since all your cities have an infrastructure level above the selected '
                        f'infra rebuild level ({infra_level}), the request is cancelled.'
                    )
                    return

                req_data.reason = f'Rebuild Infrastructure up to {infra_level}'
                req_data.note = f'Rebuild Aid'
                req_data.additional_info['Domestic Policy'] = data['domestic_policy']
                await self.on_request_fixed(req_data)
                return
            else:
                await user.send('Why are you requesting these various resources?')
                try:
                    # Wait for user to input loan request
                    req_data.reason = (await self.bot.wait_for(
                        'message',
                        check=msg_chk,
                        timeout=config.timeout)).content
                except asyncio.TimeoutError:
                    await user.send('You took too long to reply. Aborting request!')
                    return

                res_select_view = finance_views.ResourceSelectView()
                await user.send('What resources are you requesting?', view=res_select_view)
                try:
                    selected_res = await res_select_view.result()
                except asyncio.TimeoutError:
                    await user.send('You took too long to respond! Exiting...')
                    return
                for res_name in selected_res:
                    await user.send(f'How much {res_name} are you requesting?')
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
                            await user.send('Kindly input a whole number.')
                            continue
                        except asyncio.TimeoutError:
                            await user.send(
                                'You took too long to reply. Aborting request!')
                            return

                # Ensure that user didn't request for nothing
                if req_data.resources:
                    req_data.note = 'War Aid'
                    await self.on_request_fixed(req_data)
                    return
                else:
                    # No resources requested
                    await user.send(
                        "You didn't request for any resources. Please run the command again and redo your request."
                    )
                    return

    async def on_request_fixed(self, req_data: finance_views.RequestData) -> None:
        author = req_data.requester
        assert author is not None
        agree_terms = discordutils.Choices('Yes', 'No')
        await author.send(
            'Do you agree to return the money and/or resources in a timely manner in the event that you leave the '
            'alliance / get kicked from the alliance for inactivity or other reasons?', view=agree_terms)
        try:
            if await agree_terms.result() == 'No':
                await author.send('Exiting the DB Finance Request Interface.')
                return None
        except asyncio.TimeoutError:
            await author.send('You took too long to respond! Exiting...')
            return

        embed = req_data.create_embed(title='Please confirm your request.', colour=discord.Colour.blue())
        confirm_request_choice = discordutils.Choices('Yes', 'No')
        await author.send('Is this your request?', embed=embed, view=confirm_request_choice)
        try:
            confirmed = await confirm_request_choice.result() == 'Yes'
        except asyncio.TimeoutError:
            await author.send('You took too long to respond! Exiting...')
            return
        if confirmed:
            await author.send(
                'Your request has been sent. Thank you for using the DB Finance Request Interface.'
            )
            embed.title = None
            custom_id = await self.bot.get_custom_id()
            process_view = finance_views.RequestButtonsView(req_data, custom_id=custom_id)

            process_channel = self.bot.get_channel(await self.bot.database.get_kv('channel_ids').get('process_channel'))
            msg = await process_channel.send(
                f'New {req_data.kind} Request from {author.mention}',
                embed=embed,
                view=process_view
            )
            embed.title = 'Request Details'
            embed.colour = discordutils.blank_colour
            embed.remove_author()
            await asyncio.gather(
                self.bot.add_view(process_view, message_id=msg.id),
                self.bot.log(embeds=(
                    discordutils.create_embed(user=author, description=f'{author.mention} completed a request'),
                    embed
                )))
            return
        await author.send(
            'Exiting the DB Finance Request Interface. Please run the command again and redo your request.'
        )

    @request.error
    async def request_error(self, interaction: discord.Interaction,
                            error: discord.app_commands.AppCommandError) -> None:
        if isinstance(error.__cause__, commands.MaxConcurrencyReached):
            await interaction.response.send_message('You are already making a request!', ephemeral=True)
            return

        await self.bot.default_on_error(interaction, error)
