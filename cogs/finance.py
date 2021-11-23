from __future__ import annotations

import aiohttp
import asyncio
import logging
import operator
from datetime import date, timedelta
from time import time
from typing import Literal

import discord
from discord.ext import commands

import discordutils
import pnwutils
from financeutils import RequestData, RequestChoices, ResourceSelectView



logger = logging.getLogger(__name__)



# Create Finance Cog to group finance related commands
class FinanceCog(discordutils.CogBase):
    def __init__(self, bot: discordutils.DBBot):
        super().__init__(bot, __name__)
        self.has_war_aid = discordutils.SavedProperty[bool](self, 'has_war_aid')
        self.infra_rebuild_cap = discordutils.SavedProperty[int](self, 'infra_rebuild_cap')
        self.channel = discordutils.ChannelProperty(self, 'channel')


    # Main request command
    @commands.group(invoke_without_command=True, aliases=('req', ))
    @commands.max_concurrency(1, commands.BucketType.user)
    async def request(self, ctx: commands.Context) -> None:
        ## Command Run Validity Check
        # Check if output channel has been set
        if await self.channel.get(None) is None:
            await ctx.send('Output channel has not been set! Aborting.')
            return None
        
        if ctx.guild is not None:
            await ctx.send('Please check your DMs!')
        
        auth = ctx.author
        await auth.send(
            'Welcome to the DB Finance Request Interface. '
            'Enter your nation id to continue.'
        )

        # Check that reply was sent from same author in DMs
        def msg_chk(m: discord.Message) -> bool:
            return m.author == auth and m.guild is None

        ## Get Nation ID
        async with aiohttp.ClientSession() as session:
            while True:
                try:
                    # Wait for user to input nation id
                    nation_id: str = (await self.bot.wait_for(
                        'message',
                        check=msg_chk,
                        timeout=discordutils.Config.timeout)).content

                except asyncio.TimeoutError:
                    # Exit if user takes too long
                    await auth.send(
                        'You took too long to reply. Aborting request!')
                    return None

                if nation_id.lower() == 'exit':
                    # Exit if user wants to exit
                    await auth.send('Exiting DB FRI.')
                    return None

                # Extract nation id if users input nation url instead of nation id
                if (pnwutils.Constants.base_url + "nation/id=") in nation_id:
                    nation_id = nation_id.replace(
                        pnwutils.Constants.base_url + "nation/id=", "")
                # nation_id_msg = nation_id_msg.removeprefix(pnwutils.Constants.base_url + 'nation/id=')
                # ^ Only works for Python 3.9+

                # Test validity of nation id
                try:
                    int(nation_id)
                except ValueError:
                    await auth.send(
                        "That isn't a number! Please enter your nation id.")
                    continue

                # Define fields about the nation to query
                nation_query_str = '''
                query nation_info($nation_id: [Int]) {
                    nations(id: $nation_id, first: 1) {
                        data {
                            # Display Request
                            nation_name
                            
                            # Alliance Check
                            alliance_id
                            
                            # City Grants, Project Grants & War Aid
                            num_cities
                            
                            # City Grants & Project Grants 
                            city_planning
                            adv_city_planning
                            
                            # Project Grants
                            cia
                            propb

                            # Project Grants & War Aid
                            cfce
                        
                            # War Aid
                            soldiers
                            tanks
                            aircraft
                            ships
                            beigeturns
                            offensive_wars {
                                __typename
                            }
                            defensive_wars {
                                __typename
                            }
                            cities {
                                barracks
                                factory
                                airforcebase
                                drydock
                                name
                                infrastructure
                            }
                            adv_engineering_corps
                        }
                    }
                }
                '''

                # Fetch nation info
                data = await pnwutils.API.post_query(session, nation_query_str,
                                                     {'nation_id': nation_id},
                                                     'nations')
                data = data['data']
                if data:
                    # Data contains a nation, hence nation with given id exists
                    data = data.pop()
                    nation_link = pnwutils.Link.nation(nation_id)
                    if data['alliance_id'] == pnwutils.Config.aa_id:
                        nation_confirm_choice = discordutils.Choices(
                            'Yes', 'No')
                        await auth.send(f'Is this your nation? ' + nation_link,
                                        view=nation_confirm_choice)
                        try:
                            if await nation_confirm_choice.result() == 'Yes':
                                break
                            else:
                                await auth.send('Please enter your nation id!')
                                continue
                        except asyncio.TimeoutError:
                            await auth.send('You took too long to respond! Exiting...')
                            return
                    else:
                        await auth.send(
                            f"{nation_link} isn't in {pnwutils.Config.aa_name}!"
                            " Please enter your nation id.")
                        continue
                else:
                    # Data has no nation, hence no nation with given id exists
                    await auth.send(
                        "That isn't a valid nation id! Please enter your nation id."
                    )
                    continue

        ## Get Request Type
        req_types = ['Grant', 'Loan']
        if await self.has_war_aid.get():
            req_types.append('War Aid')

        req_type_choice = discordutils.Choices(*req_types)
        await auth.send('What kind of request is this?', view=req_type_choice)
        try:
            req_type = await req_type_choice.result()
        except asyncio.TimeoutError:
            await auth.send('You took too long to respond! Exiting...')
            return
        
        ## Redirect Accordingly
        if req_type == 'Grant':
            grant_type_choice = discordutils.Choices('City', 'Project',
                                                     'Other')
            await auth.send('What type of grant do you want?',
                            view=grant_type_choice)
            try:
                grant_type = await grant_type_choice.result()
            except asyncio.TimeoutError:
                await auth.send('You took too long to respond! Exiting...')
                return
            
            if grant_type == 'City':
                # Get data of projects which affect city cost
                has_up = data['city_planning']
                has_aup = data['adv_city_planning']
                # Calculate city cost
                req_res = pnwutils.Resources(
                    money=(50000 * (data['num_cities'] - 1)**3 +
                           150000 * data['num_cities'] + 75000 -
                           50000000 * has_up - 100000000 * has_aup) // 20 * 19)
                # Create embed
                project_string = 'Urban Planning' * has_up + ' and ' * (has_up and has_aup) +\
                                 'Advanced Urban Planning' * has_aup + 'None' * (not has_up and not has_aup)
                await self.on_request_fixed(
                    RequestData(auth, req_type, f'City {data["num_cities"] + 1}',
                                data['nation_name'], nation_link, req_res,
                                f'City {data["num_cities"] + 1} Grant',
                                {'Projects': project_string}))
                return None

            elif grant_type == 'Project':
                project_choice = discordutils.Choices(
                    'Center for Civil Engineering', 'Intelligence Agency',
                    'Propaganda Bureau', 'Urban Planning',
                    'Advanced Urban Planning', 'Other')
                await auth.send('Which project do you want?',
                                view=project_choice)
                try:
                    project = await project_choice.result()
                except asyncio.TimeoutError:
                    await auth.send('You took too long to respond! Exiting...')
                    return
                project_field_name = {
                    'Center for Civil Engineering': 'cfce',
                    'Intelligence Agency': 'cia',
                    'Propaganda Bureau': 'propb',
                    'Urban Planning': 'city_planning',
                    'Advanced Urban Planning': 'adv_city_planning',
                    'Other': 'other'
                }
                data['other'] = None
                # Check if they already have project
                if data[project_field_name[project]] == True:
                    await auth.send(
                        f'You already have the {project} project. Please try again with a different project.'
                    )
                    return
                # If not, then redirect accordingly
                elif project == 'Center for Civil Engineering':
                    req_res = pnwutils.Resources(oil=1000,
                                                 iron=1000,
                                                 bauxite=1000,
                                                 money=3000000)
                elif project == 'Intelligence Agency':
                    req_res = pnwutils.Resources(steel=500,
                                                 gasoline=500,
                                                 money=5000000)
                elif project == 'Propaganda Bureau':
                    req_res = pnwutils.Resources(aluminum=1500, money=15000000)
                elif project == 'Urban Planning':
                    if data['num_cities'] < 11:
                        await auth.send(
                            f'The Urban Planning project requires 11 cities to build, however you only have {data["num_cities"]} cities. Please try again next time.'
                        )
                        return None
                    else:
                        req_res = pnwutils.Resources(coal=10000,
                                                     oil=10000,
                                                     aluminum=20000,
                                                     munitions=10000,
                                                     gasoline=10000,
                                                     food=1000000)
                elif project == 'Advanced Urban Planning':
                    if data['city_planning'] == False:
                        await auth.send(
                            'You have not built the Urban Planning project, which is needed to build the Advanced Urban Planning project. Please try again next time.'
                        )
                        return None
                    elif data['num_cities'] < 16:
                        await auth.send(
                            f'The Advanced Urban Planning project requires 16 cities to build, however you only have {data["num_cities"]} cities. Please try again next time.'
                        )
                        return None
                    else:
                        req_res = pnwutils.Resources(uranium=10000,
                                                     aluminum=40000,
                                                     steel=20000,
                                                     munitions=20000,
                                                     food=2500000)
                else:
                    await auth.send(
                        'Other projects are not eligble for grants. Kindly request for a loan.'
                    )
                    return None
                await self.on_request_fixed(
                    RequestData(auth, req_type, project, data['nation_name'],
                                nation_link, req_res,
                                f'{project} Project Grant'))
                return None

            else:
                await auth.send(
                    'Other Grants have not been implemented! Please try again next time.'
                )
                return None

        elif req_type == 'Loan':
            await auth.send('What are you requesting a loan for?')
            try:
                # Wait for user to input loan request
                loan_req: str = (await self.bot.wait_for(
                    'message',
                    check=msg_chk,
                    timeout=discordutils.Config.timeout)).content
            except asyncio.TimeoutError:
                await auth.send('You took too long to reply. Aborting request!'
                                )
                return None

            req_res = {}
            res_select_view = ResourceSelectView(discordutils.Config.timeout)
            await auth.send('What resources are you requesting?', view=res_select_view)
            try:
                selected_res = await res_select_view.result()
            except asyncio.TimeoutError:
                await auth.send('You took too long to respond! Exiting...')
                return
            for res_name in selected_res:
                await auth.send(f'How much {res_name} are you requesting?')
                while True:
                    try:
                        # Wait for user to input how much of each res they want
                        res_amt: int = int((await self.bot.wait_for(
                            'message',
                            check=msg_chk,
                            timeout=discordutils.Config.timeout)).content)
                        if res_amt > 0:
                            req_res[res_name] = res_amt
                        break
                    except ValueError:
                        await auth.send('Kindly input a whole mumber.')
                        continue
                    except asyncio.TimeoutError:
                        await auth.send(
                            'You took too long to reply. Aborting request!')
                        return None

            # Ensure that user didn't request for nothing
            if not req_res:
                # No resources requested
                await auth.send(
                    'You didn\'t request for any resources. Please run the command again and redo your request.'
                )
                return None
            else:
                req_res = pnwutils.Resources(**req_res)
                await self.on_request_fixed(
                    RequestData(auth, req_type, loan_req, data['nation_name'],
                                nation_link, req_res,
                                f'{loan_req.title()} Loan'))
                return None

        elif req_type == 'War Aid':
            war_aid_type_choice = discordutils.Choices(
                'Buy Military Units', 'Rebuild Military Improvements',
                'Rebuild Infrastructure')
            await auth.send('What type of war aid are you requesting?',
                            view=war_aid_type_choice)
            try:
                war_aid_type = await war_aid_type_choice.result()
            except asyncio.TimeoutError:
                await auth.send('You took too long to respond! Exiting...')
                return
            additional_info = {
                'Beige Turns':
                data['beigeturns'],
                'Active Wars':
                f'''
                    Offensive: {len(data["offensive_wars"])}
                    Defensive: {len(data["defensive_wars"])}
                '''
            }

            if war_aid_type == 'Buy Military Units':
                # Calculate amount of military units needed
                needed_units = {
                    # Capacity per improvement * max improvements * city count - existing units
                    'soldiers':
                    3000 * 5 * data['num_cities'] - data['soldiers'],
                    'tanks': 250 * 5 * data['num_cities'] - data['tanks'],
                    'aircraft': 15 * 5 * data['num_cities'] - data['aircraft'],
                    'ships': 5 * 3 * data['num_cities'] - data['ships']
                }
                await auth.send(
                    f'To get to max military units, you will need an additional {needed_units["soldiers"]} soldiers, {needed_units["tanks"]} tanks, {needed_units["aircraft"]} aircraft and {needed_units["ships"]} ships.'
                )
                # Calculate resources needed to buy needed military units
                req_res = pnwutils.Resources(
                    money=5 * needed_units['soldiers'] +
                    60 * needed_units['tanks'] +
                    4000 * needed_units['aircraft'] +
                    50000 * needed_units['ships'],
                    steel=int(0.5 * (needed_units['tanks']) + 1) +
                    30 * needed_units['ships'],
                    aluminum=5 * needed_units['aircraft']
                )
                aid_req = 'Buy up to Max Military Units'
                await self.on_request_fixed(
                    RequestData(
                        auth, req_type, aid_req, data['nation_name'],
                        nation_link, req_res,
                        f'War Aid to {aid_req}',
                        additional_info))
                return None

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

                await auth.send(
                    f'To get to max military improvements, you will need an additional {needed_improvements["barracks"]} barracks, {needed_improvements["factory"]} factories, {needed_improvements["airforcebase"]} hangars and {needed_improvements["drydock"]} drydocks.'
                )
                # Calculate resources needed to buy needed military improvements
                req_res = pnwutils.Resources(
                    money=3000 * needed_improvements['barracks'] +
                    15000 * needed_improvements['factory'] +
                    100000 * needed_improvements['airforcebase'] +
                    250000 * needed_improvements['drydock'],
                    steel=10 * needed_improvements['airforcebase'],
                    aluminum=5 * needed_improvements['factory'] +
                    20 * needed_improvements['drydock'])

                aid_req = 'Rebuild to Max Military Improvements'
                await self.on_request_fixed(
                    RequestData(
                        auth, req_type, aid_req, data['nation_name'],
                        nation_link, req_res,
                        f'War Aid to {aid_req}',
                        additional_info))
                return None

            elif war_aid_type == 'Rebuild Infrastructure':
                irc = await self.infra_rebuild_cap.get()
                await auth.send(
                    f'The current infrastructure rebuild cap is set at {irc}. '
                    f'This means that money will only be provided to rebuild infrastructure below {irc} up to that amount. '
                    'The amount calculated assumes that domestic policy is set to Urbanisation.'
                )
                # Calculate infra cost for each city
                req_res = pnwutils.Resources()
                for city in data['cities']:
                    if city['infrastructure'] < irc:
                        for infra_lvl in range(city['infrastructure'], irc + 1):
                            if infra_lvl < 10:
                                req_res.money += 300
                            else:
                                req_res.money += 300 + (infra_lvl -
                                                        10) ** 2.2 / 710
                # Account for Urbanisation and cost reducing projects (CCE and AEC)
                req_res.money *= 0.95 - 0.05 * (data['cfce'] +
                                                data['adv_engineering_corps'])
                req_res.money = int(req_res.money + 0.5)
                # Check if infrastucture in any city under cap
                if req_res.money == 0:
                    await auth.send(
                        'Since all your cities have an infrastructure level above '
                        f'the current infrastructure rebuild cap ({irc}), you are '
                        'not eligible for war aid to rebuild infrastructure.'
                    )
                    return None
                
                aid_req = f'Rebuild Infrastructure up to {irc}'
                await self.on_request_fixed(
                    RequestData(
                        auth, req_type, aid_req, data['nation_name'],
                        nation_link, req_res,
                        f'War Aid to {aid_req}',
                        additional_info))
                return None


    async def on_request_fixed(self, req_data: RequestData) -> None:
        auth = req_data.requester
        agree_terms = discordutils.Choices('Yes', 'No')
        await auth.send(
            'Do you agree to return the money and/or resources in a timely manner in the event that you leave the alliance / get kicked from the alliance for inactivity or other reasons?',
            view=agree_terms)
        try:
            if await agree_terms.result() == 'No':
                await auth.send('Exiting the DB Finance Request Interface.')
                return None
        except asyncio.TimeoutError:
            auth.send('You took too long to respond! Exiting...')
            return
        
        embed = discordutils.construct_embed(
            {
                'Nation':
                f'[{req_data.nation_name}]({req_data.nation_link})',
                'Request Type': req_data.kind,
                'Requested': req_data.reason,
                'Requested Resources': req_data.resources,
                **req_data.additional_info
            },
            title='Please confirm your request.')
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
            embed.add_field(
                name='Withdrawal Link',
                value=
                f'[Link]({req_data.resources.create_link("w", recipient=req_data.nation_name, note=req_data.note)})'
            )
            process_view = RequestChoices(self.on_processed, req_data)
            self.bot.add_view(process_view)
            await (await self.channel.get()).send(
                f'New Request from {auth.mention}',
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none(),
                view=process_view)

            return None
        
        await auth.send(
            'Exiting the DB Finance Request Interface. Please run the command again and redo your request.'
        )


    async def on_processed(self, status: Literal['Accepted', 'Rejected',
                                                 'Sent'],
                           req_data: RequestData, user: discord.abc.User,
                           message: discord.Message):
        logger.info(f'processing {status} request: {req_data}')
        if status == 'Accepted':
            await req_data.requester.send(
                f'Your {req_data.kind} request {"to" if (req_data.kind == "War Aid") else "for"} {req_data.reason} has been accepted! The resources will be sent to you soon.'
            )
            #db['active_reqs'].remove(message)

        elif status == 'Rejected':
            await user.send(
                f'What was the reason for rejecting the {req_data.kind} request {"to" if (req_data.kind == "War Aid") else "for"} {req_data.reason}?'
            )

            def msg_chk(m: discord.Message) -> bool:
                return m.author == user and m.guild is None

            try:
                reject_reason: str = (await self.bot.wait_for(
                    'message', check=msg_chk,
                    timeout=discordutils.Config.timeout)).content
            except asyncio.TimeoutError():
                await user.send('You took too long to respond! Default rejection reason set.')
                reject_reason = 'not given'
            await req_data.requester.send(
                f'Your {req_data.kind} request {"to" if (req_data.kind == "War Aid") else "for"} {req_data.reason} has been rejected!\n'
                f'Reason: {reject_reason}')
            await message.edit(embed=message.embeds.pop().add_field(
                name='Rejection Reason', value=reject_reason, inline=True))

        if status == 'Sent':
            await req_data.requester.send(
                f'Your {req_data.kind} request {"to" if (req_data.kind == "War Aid") else "for"} {req_data.reason} has been sent to your nation!'
            )
            if req_data.kind == 'Loan':
                await req_data.requester.send(f'Kindly remember to return the requested resources <t:{round(time() + 30*24*60*60)}:R>. Once you have done so, ping and inform the Finance staff in #finance-and-audits.')
                await message.edit(embed=message.embeds.pop().add_field(
                name='Return Date', value=(date.today() + timedelta(days=30)).strftime('%d %b, %Y'), inline=True))

        await message.edit(
            f'{status if status != "Sent" else "Accepted and Sent"} Request from {req_data.requester.mention}',
            allowed_mentions=discord.AllowedMentions.none())

    @request.error
    async def request_error(self, ctx: commands.Context,
                            error: commands.CommandError) -> None:
        if isinstance(error, commands.MaxConcurrencyReached):
            await ctx.send('You are already making a request!')
            return None
        await discordutils.default_error_handler(ctx, error)


    @commands.guild_only()
    @commands.check(discordutils.gov_check)
    @request.group(invoke_without_command=True)
    async def set(self, ctx: commands.Context) -> None:
        await ctx.send('Subcommands: `channel`, `war_aid`, `infra_rebuild_cap`'
                       )


    @commands.guild_only()
    @commands.check(discordutils.gov_check)
    @set.command(aliases=('channel', ))
    async def chan(self, ctx: commands.Context) -> None:
        await self.channel.set(ctx.channel)
        await ctx.send(
            'Output channel set! New responses will now be sent here.')

    @commands.guild_only()
    @commands.check(discordutils.gov_check)
    @set.command(aliases=('aid', ))
    async def war_aid(self, ctx: commands.Context) -> None:
        await self.has_war_aid.transform(operator.not_)
        await ctx.send(
            f'War Aid is now {(not await self.has_war_aid.get()) * "not "}available!')

    @commands.guild_only()
    @commands.check(discordutils.gov_check)
    @set.command(aliases=('infra_cap', 'cap'))
    async def infra_rebuild_cap(self, ctx: commands.Context, cap: int) -> None:
        await self.infra_rebuild_cap.set(max(0, 50 * round(cap/50)))
        await ctx.send(
            f'The infrastructure rebuild cap has been set to {await self.infra_rebuild_cap.get()}.'
        )


    @infra_rebuild_cap.error
    async def infra_cap_set_error(self, ctx: commands.Context,
                                  error: commands.CommandError) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                'Usage: `request set_infra_rebuild_cap 2000`, where `2000` is your desired cap.'
            )
            return
        if isinstance(error, commands.BadArgument):
            await ctx.send('Please provide a whole number to set the cap to!')
            return
        await discordutils.default_error_handler(ctx, error)



# Setup Finance Cog as an extension
def setup(bot: discordutils.DBBot) -> None:
    bot.add_cog(FinanceCog(bot))