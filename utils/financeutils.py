from __future__ import annotations

import asyncio
import datetime
import pickle
from dataclasses import dataclass, field
from typing import Awaitable, Iterable, TypedDict

import discord

from . import pnwutils, config, discordutils

__all__ = ('RequestData', 'LoanData', 'withdrawal_embed', 'ResourceSelectView')


@dataclass()
class RequestData:
    requester: discord.abc.User | None = None
    nation_id: int = 0
    nation_name: str = ''
    kind: str = ''
    reason: str = ''
    resources: pnwutils.Resources = field(default_factory=pnwutils.Resources)
    note: str = ''
    additional_info: dict[str, str] = field(default_factory=dict)
    _requester_id: int | None = None
    presets: dict[str, pnwutils.Resources] = field(default_factory=dict)

    @property
    def nation_link(self):
        return pnwutils.link.nation(self.nation_id)

    @property
    def requester_id(self):
        if self._requester_id is None:
            self._requester_id = self.requester.id
        return self._requester_id

    def create_embed(self, **kwargs) -> discord.Embed:
        embed = discord.Embed(**kwargs)
        embed.set_author(name=self.requester.name, icon_url=self.requester.display_avatar.url)
        embed.add_field(name='Nation', value=f'[{self.nation_name}]({self.nation_link})')
        embed.add_field(name='Request Type', value=self.kind)
        embed.add_field(name='Reason', value=self.reason)
        embed.add_field(name='Requested Resources', value=str(self.resources))
        for n, v in self.additional_info.items():
            embed.add_field(name=n, value=v)
        return embed

    def create_link(self) -> str:
        return pnwutils.link.bank("w", self.resources, self.nation_name,
                                  self.note if self.note else self.reason if self.kind != 'War Aid' else 'War Aid')

    def create_withdrawal_embed(self, **kwargs) -> discord.Embed:
        return withdrawal_embed(self.nation_name, self.nation_id, self.reason, self.resources, **kwargs)

    def create_withdrawal(self) -> pnwutils.Withdrawal:
        return pnwutils.Withdrawal(self.resources, self.nation_id, pnwutils.EntityType.NATION, self.note)

    def create_withdrawal_view(self, custom_id: int):
        return WithdrawalView(self.requester_id, self.create_withdrawal(), custom_id=custom_id)

    def __getstate__(self) -> tuple:
        return (0, self.requester_id, self.nation_id, self.nation_name, self.kind, self.reason,
                self.resources.to_dict(), self.note, self.additional_info, self.presets)

    def __setstate__(self, state):
        if state[0] == 0:
            (_, self._requester_id, self.nation_id, self.nation_name, self.kind,
             self.reason, res_dict, self.note, self.additional_info, self.presets) = state
            self.resources = pnwutils.Resources(**res_dict)
            self.requester = None
        else:
            raise pickle.UnpicklingError(f'Unrecognised state version {state[0]} for RequestData')

    def set_requester(self, client: discord.Client) -> discord.abc.User:
        """Used to set the requester attribute using the client, after unpickling, as the requester is not saved."""
        self.requester = client.get_user(self.requester_id)
        return self.requester


class LoanDataDict(TypedDict):
    due_date: str
    loaned: pnwutils.ResourceDict


class LoanData:
    __slots__ = ('due_date', 'loaned')

    def __init__(self, due_date: str | datetime.datetime, loaned: pnwutils.Resources | pnwutils.ResourceDict):
        if isinstance(due_date, datetime.datetime):
            self.due_date = due_date
        else:
            self.due_date = datetime.datetime.fromisoformat(due_date)

        if isinstance(loaned, pnwutils.Resources):
            self.loaned = loaned
        else:
            self.loaned = pnwutils.Resources(**loaned)

    @property
    def display_date(self) -> str:
        return discord.utils.format_dt(self.due_date, 'f')

    def to_dict(self) -> LoanDataDict:
        return {'due_date': self.due_date.isoformat(), 'loaned': self.loaned.to_dict()}

    def to_embed(self, **kwargs: str) -> discord.Embed:
        embed = self.loaned.create_embed(**kwargs)
        embed.insert_field_at(0, name='Due Date', value=self.display_date)
        return embed


def withdrawal_embed(name: str, nation_id: str | int, reason: str, resources: pnwutils.Resources,
                     **kwargs) -> discord.Embed:
    embed = discord.Embed(colour=discord.Colour.blue(), **kwargs)
    embed.add_field(name='Nation', value=f'[{name}]({pnwutils.link.nation(nation_id)})')
    embed.add_field(name='Reason', value=reason)
    embed.add_field(name='Requested Resources', value=str(resources))
    return embed


# noinspection PyAttributeOutsideInit
class ResourceSelector(discord.ui.Select['ResourceSelectView']):
    def __init__(self, res: Iterable[str]):
        options = [discord.SelectOption(label=s, emoji=config.resource_emojis[s]) for s in res]
        super().__init__(placeholder='Choose the resources you want',
                         min_values=1,
                         max_values=len(options),
                         options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.view.user_id is not None and interaction.user.id != self.view.user_id:
            await interaction.channel.send('You are not the intended recipient of this component, '
                                           f'{interaction.user.mention}',
                                           allowed_mentions=discord.AllowedMentions.none())
            return
        self.view.future.set_result(self.values)
        self.disabled = True
        await interaction.response.edit_message(view=self.view)


class ResourceSelectView(discord.ui.View):
    def __init__(self, user_id: int | None = None, res: Iterable[str] | None = None,
                 timeout: float = config.timeout):
        super().__init__(timeout=timeout)

        if res:
            res = set(res)
            assert res <= set(pnwutils.Resources.all_res)
        else:
            res = pnwutils.Resources.all_res
        self.future = asyncio.get_event_loop().create_future()
        self.user_id = user_id
        self.add_item(ResourceSelector(res))

    def result(self) -> Awaitable[list[str]]:
        return self.future

    async def on_timeout(self):
        if not self.future.done():
            self.future.set_exception(asyncio.TimeoutError())


class RequestButtonsView(discordutils.PersistentView):
    def __init__(self, data: RequestData, *, custom_id: int):
        self.data = data

        super().__init__(custom_id=custom_id)

    def get_state(self) -> tuple:
        return {}, self.data

    @classmethod
    async def withdraw_for_request(cls, data: RequestData, processor: discord.User):
        result = await data.create_withdrawal().withdraw(cls.bot.session)
        messages = {
            pnwutils.WithdrawalResult.SUCCESS: (
                'You should have received the resources.',
                'Requested resources have been sent'),
            pnwutils.WithdrawalResult.LACK_RESOURCES: (
                'The resources will be sent once available.',
                'Withdrawal Request created due to insufficient resources in the bank'),
            pnwutils.WithdrawalResult.BLOCKADED: (
                'You are currently under a blockade, the resources can only be sent once it is broken.',
                'Withdrawal Request created due to a blockade on the receiving nation.'
            )
        }
        await asyncio.gather(
            data.requester.send(
                f'Your {data.kind} request for `{data.reason}` '
                'has been accepted! ' +
                messages[result][0]
            ),
            cls.bot.log(embeds=(
                discordutils.create_embed(
                    user=data.requester,
                    description=f"{data.requester.mention}'s {data.kind} Request for `{data.reason}` "
                                f'accepted by {processor.mention}\n\n' +
                                messages[result][1]),
                data.resources.create_embed(title='Requested Resources')
            )))
        if result is not pnwutils.WithdrawalResult.SUCCESS:
            await cls.send_withdrawal_view(data)

    @classmethod
    async def send_withdrawal_view(cls, data):
        view = data.create_withdrawal_view(await cls.bot.get_custom_id())

        channel = cls.bot.get_channel(await cls.bot.database.get_kv('channel_ids').get('withdrawal_channel'))
        msg = await channel.send(f'Withdrawal Request from {data.requester.mention}',
                                 embed=data.create_withdrawal_embed(),
                                 allowed_mentions=discord.AllowedMentions.none(),
                                 view=view)
        await cls.bot.add_view(view, message_id=msg.id)

    @discordutils.persistent_button(label='Accept')
    async def accept(self, button: discord.ui.Button, interaction: discord.Interaction):
        button.style = discord.ButtonStyle.success
        discordutils.disable_all(self)
        self.stop()
        await self.bot.remove_view(self)

        self.data.set_requester(self.bot)
        if self.data.kind == 'Loan':
            # process loan
            loan_data = LoanData(
                datetime.datetime.now().replace(minute=0, second=0) + datetime.timedelta(days=30),
                self.data.resources)
            embed = interaction.message.embeds[0]
            embed.add_field(name='Return By', value=loan_data.display_date, inline=True)
            embed.colour = discord.Colour.green()
            await interaction.response.edit_message(view=self, embed=embed)
            # change balance
            users_table = self.bot.database.get_table('users')
            new_bal = pnwutils.Resources(**await users_table.update(
                f'balance = balance + {loan_data.loaned.to_row()}'
            ).where(discord_id=self.data.requester_id).returning_val('balance'))
            await asyncio.gather(
                self.bot.database.execute(
                    f'INSERT INTO loans(discord_id, due_date, loaned) VALUES ($1, $2, {self.data.resources.to_row()})',
                    self.data.requester_id, loan_data.due_date),
                interaction.edit_original_response(
                    content=f'{self.data.kind} Request from {self.data.requester.mention}',
                    allowed_mentions=discord.AllowedMentions.none()),
                self.data.requester.send(
                    'Your loaned resources have been added to your bank balance.',
                    embed=self.data.resources.create_embed(title='Loaned Resources')),
                self.bot.log(embeds=(
                    discordutils.create_embed(
                        user=self.data.requester,
                        description=f"{self.data.requester.mention}'s Loan Request for {self.data.reason} "
                                    f"accepted by {interaction.user.mention}"),
                    self.data.resources.create_embed(title='Loaned Resources')
                )))

            await self.data.requester.send(
                'Your current balance is:',
                embed=new_bal.create_balance_embed(self.data.requester)
            )
            await self.data.requester.send(
                'You will have to use `bank withdraw` to withdraw the loan from your bank balance to your nation. '
                'Kindly remember to return the requested resources by depositing it back into your bank balance '
                f'and using `bank loan return` by {discord.utils.format_dt(loan_data.due_date, "D")} '
                f'({discord.utils.format_dt(loan_data.due_date, "R")}). '
                'You can check your loan status with `bank loan status`.')
            return
        # process other
        embed = interaction.message.embeds[0]
        embed.colour = discord.Colour.green()
        # split things up in order to use allowed_mentions
        await asyncio.gather(
            interaction.response.edit_message(view=self, embed=embed),
            interaction.edit_original_response(
                content=f'Accepted {self.data.kind} Request from {self.data.requester.mention}',
                allowed_mentions=discord.AllowedMentions.none()),
            self.withdraw_for_request(self.data, interaction.user))

    @discordutils.persistent_button(label='Reject')
    async def reject(self, button: discord.ui.Button, interaction: discord.Interaction):
        self.data.set_requester(self.bot)
        reason_modal = discordutils.single_modal(
            'Why is this request being rejected?', 'Rejection Reason', discord.TextStyle.paragraph)
        await interaction.response.send_modal(reason_modal)
        reject_reason = await reason_modal.result()
        # sent modal, must respond to its interaction to close it
        await discordutils.respond_to_interaction(reason_modal.interaction)

        button.style = discord.ButtonStyle.success
        discordutils.disable_all(self)
        self.stop()
        embed = interaction.message.embeds[0]
        embed.add_field(name='Rejection Reason', value=reject_reason, inline=True)
        embed.colour = discord.Colour.red()
        await asyncio.gather(
            self.data.requester.send(
                f'Your {self.data.kind} request for `{self.data.reason}` '
                f'has been rejected!\n\nReason:\n`{reject_reason}`'),
            interaction.edit_original_response(
                content=f'Rejected {self.data.kind} Request from {self.data.requester.mention}',
                view=self, embed=embed, allowed_mentions=discord.AllowedMentions.none()),
            self.bot.remove_view(self),
            self.bot.log(embeds=(
                discordutils.create_embed(
                    user=self.data.requester,
                    description=f"{self.data.requester.mention}'s {self.data.kind} Request for `{self.data.reason}` "
                                f'rejected by {interaction.user.mention} for the reason of `{reject_reason}`'),
                self.data.resources.create_embed(title='Requested Resources')
            ))
        )

    @discordutils.persistent_button(label='Modify')
    async def modify(self, button: discord.ui.Button, interaction: discord.Interaction):
        button.style = discord.ButtonStyle.success
        discordutils.disable_all(self)
        self.data.set_requester(self.bot)
        user = interaction.user
        old_res = self.data.resources.copy()
        embed = interaction.message.embeds[0]
        embed.description = f'Undergoing modification by {user.mention}'
        embed.colour = discord.Colour.yellow()
        preset_view = PresetView(self)
        await asyncio.gather(
            interaction.response.edit_message(view=self, embed=embed),
            user.send('How would you like to modify this grant request?', view=preset_view))

        try:
            reason = await preset_view.future
        except (asyncio.TimeoutError, asyncio.CancelledError) as e:
            await user.send('You took too long to respond! Aborting...'
                            if isinstance(e, asyncio.TimeoutError) else
                            'Cancelling modification...')

            discordutils.enable_all(self)
            button.style = discord.ButtonStyle.secondary
            embed.description = ''
            embed.colour = discord.Colour.blue()
            await interaction.edit_original_response(view=self, embed=embed)
            return
        discordutils.disable_all(self)
        self.stop()
        await self.bot.remove_view(self)
        custom_id = await self.bot.get_custom_id()
        response_view = ModificationResponseView(self.data, user.id, reason, custom_id)
        updated_res_embed = self.data.resources.create_embed(title='Updated Resources')
        embed.description = f'Modified by {user.mention}'
        embed.colour = discord.Colour.green()
        embed.add_field(name='Updated Resources', value=self.data.resources)
        await asyncio.gather(
            interaction.edit_original_response(
                content=f'Modified {self.data.kind} Request from {self.data.requester.mention}',
                embed=embed, view=self,
                allowed_mentions=discord.AllowedMentions.none(),
            ),
            self.bot.log(embeds=(
                discordutils.create_embed(
                    user=self.data.requester,
                    description=f"{self.data.requester.mention}'s {self.data.kind} Request for `{self.data.reason}` "
                                f'modified by {user.mention} for reason of `{reason}`'),
                old_res.create_embed(title='Previous Resources'),
                updated_res_embed
            )),
            user.send('Request Modification Complete!', embed=updated_res_embed),
            response_view.send_response()
        )


class PresetView(discord.ui.View):
    def __init__(self, parent_view: RequestButtonsView):
        super().__init__(timeout=config.timeout)
        self.parent_view = parent_view
        self.add_item(CustomPresetButton())
        for b in PresetButton.create_buttons(parent_view.data.presets):
            self.add_item(b)
        self.add_item(CancelButton())
        self.reason: str | None = None
        self.future: asyncio.Future[str] = asyncio.get_event_loop().create_future()

    def result(self) -> Awaitable[str]:
        return self.future

    async def on_timeout(self) -> None:
        self.future.set_exception(asyncio.TimeoutError())


class CancelButton(discord.ui.Button[PresetView]):
    def __init__(self):
        super().__init__(label='Cancel')

    async def callback(self, interaction: discord.Interaction):
        self.style = discord.ButtonStyle.success
        discordutils.disable_all(self.view)
        self.view.stop()
        await interaction.response.edit_message(view=self.view)
        self.view.future.set_exception(asyncio.CancelledError())


class PresetButton(discord.ui.Button[PresetView]):
    @classmethod
    def create_buttons(cls, presets: dict[str, pnwutils.Resources]) -> Iterable[PresetButton]:
        return (cls(n, r) for n, r in presets.items())

    def __init__(self, name: str, resources: pnwutils.Resources):
        self.resources = resources
        super().__init__(label=name)

    async def callback(self, interaction: discord.Interaction):
        self.style = discord.ButtonStyle.success
        discordutils.disable_all(self.view)
        reason_modal = discordutils.single_modal(
            'Why is this request being modified?', 'Modification Reason', discord.TextStyle.paragraph)
        await asyncio.gather(
            interaction.edit_original_response(view=self.view),
            interaction.response.send_modal(reason_modal))

        self.view.stop()
        self.view.parent_view.data.resources = self.resources
        self.view.future.set_result(await reason_modal.result())
        await discordutils.respond_to_interaction(reason_modal.interaction)


class CustomPresetButton(discord.ui.Button[PresetView]):
    def __init__(self):
        super().__init__(label='Custom Modification')

    async def callback(self, interaction: discord.Interaction):
        self.style = discord.ButtonStyle.success
        discordutils.disable_all(self.view)
        self.view.stop()
        modal = CustomModificationModal(self.view.parent_view)
        await interaction.response.send_modal(modal)
        self.view.future.set_result(await modal.future)
        await interaction.edit_original_response(view=self.view)


class CustomModificationModal(discord.ui.Modal):
    def __init__(self, view: RequestButtonsView):
        super().__init__(title='How would you like to modify this request?', timeout=config.timeout)
        self.view = view
        self.future: asyncio.Future[str] = asyncio.get_event_loop().create_future()
        self.res_input = []

        self.reason_input = discord.ui.TextInput(
            label='What is the reason for this modification?',
            style=discord.TextStyle.paragraph)
        self.add_item(self.reason_input)
        for res_name, amt in view.data.resources.items_nonzero():
            text_input = discord.ui.TextInput(
                label=f'How much {res_name} should this request be for?',
                placeholder=str(amt),
                required=False)
            self.add_item(text_input)
            self.res_input.append(text_input)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        for res_name, input_text in zip(self.view.data.resources.keys_nonzero(), self.res_input):
            if input_text.value is not None:
                self.view.data.resources[res_name] = int(input_text.value)
        self.future.set_result(self.reason_input.value)
        await interaction.response.send_message('The request has been updated!', embed=self.view.data.create_embed())


class ModificationResponseView(discordutils.PersistentView):
    def __init__(self, data: RequestData, processor_id: int, reason: str, custom_id: int):
        super().__init__(custom_id=custom_id)
        self.data = data
        self.processor_id = processor_id
        self.reason = reason

    async def send_response(self):
        await self.data.requester.send(
            f'Your request has been modified for the reason of `{self.reason}`. Is this modified request acceptable, '
            'or should the request be cancelled?', embed=self.data.create_withdrawal_embed(), view=self)

    def get_state(self) -> tuple:
        return {}, self.data, self.processor_id

    @discordutils.persistent_button(label='Accept')
    async def accept(self, button: discord.ui.Button, interaction: discord.Interaction):
        button.style = discord.ButtonStyle.success
        discordutils.disable_all(self)
        self.stop()

        embed = self.data.resources.create_embed(title='Request Resources')
        await asyncio.gather(
            interaction.response.edit_message(view=self, embed=embed),
            self.bot.log(embeds=(
                discordutils.create_embed(
                    user=self.data.requester,
                    description=f'{self.data.requester.mention} accepted their modified {self.data.kind} request '
                                f'for `{self.data.reason}`'),
                self.data.resources.create_embed(title='Request Resources')
            )),
            RequestButtonsView.withdraw_for_request(self.data, self.bot.get_user(self.processor_id))
        )

    @discordutils.persistent_button(label='Reject')
    async def reject(self, button: discord.ui.Button, interaction: discord.Interaction):
        button.style = discord.ButtonStyle.success
        discordutils.disable_all(self)
        self.stop()

        embed = self.data.resources.create_embed(title='Request Resources')
        await asyncio.gather(
            interaction.response.edit_message(view=self, embed=embed),
            self.bot.log(embeds=(
                discordutils.create_embed(
                    user=self.data.requester,
                    description=f'{self.data.requester.mention} rejected their modified {self.data.kind} request '
                                f'for `{self.data.reason}`'),
                embed
            )))


class WithdrawalView(discordutils.PersistentView):
    def __init__(self, receiver_id: int, withdrawal: pnwutils.Withdrawal, *, custom_id: int):
        self.receiver_id = receiver_id
        self.withdrawal = withdrawal
        super().__init__(custom_id=custom_id)

    def get_state(self) -> tuple:
        return {}, self.receiver_id, self.withdrawal

    @discordutils.persistent_button(label='Send')
    async def send(self, button: discordutils.PersistentButton, interaction: discord.Interaction):
        result = await self.withdrawal.withdraw(self.bot.session)
        if result is pnwutils.WithdrawalResult.SUCCESS:
            button.style = discord.ButtonStyle.success
            discordutils.disable_all(self)
            self.stop()
            embed = interaction.message.embeds[0]
            embed.colour = discord.Colour.green()
            member = interaction.guild.get_member(self.receiver_id)
            contents_embed = self.withdrawal.resources.create_embed(title='Withdrawal Contents')
            await asyncio.gather(
                self.bot.remove_view(self),
                interaction.response.edit_message(view=self, embed=embed),
                member.send('Your withdrawal request for the following has been sent to your nation!',
                            embed=contents_embed),
                self.bot.log(embeds=(
                    discordutils.create_embed(
                        user=member, description=f"{member.mention}'s withdrawal Sent by {interaction.user.mention}"),
                    contents_embed)))
            return
        await interaction.response.send_message(
            'The bank does not have enough on hand to fulfill this withdrawal!'
            if result is pnwutils.WithdrawalResult.LACK_RESOURCES else
            'The recipient is currently blockaded and cannot receive resources.')

    @discordutils.persistent_button(label='Cancel')
    async def cancel(self, button: discordutils.PersistentButton, interaction: discord.Interaction):
        reason_modal = discordutils.single_modal(
            f'Why is this withdrawal request being cancelled?', 'Cancellation Reason', discord.TextStyle.paragraph)
        await interaction.response.send_modal(reason_modal)
        cancel_reason = await reason_modal.result()
        # close modal
        await discordutils.respond_to_interaction(reason_modal.interaction)

        await self.bot.database.get_table('users').update(
            f'balance = balance + {self.withdrawal.resources.to_row()}').where(discord_id=self.receiver_id)

        button.style = discord.ButtonStyle.success
        discordutils.disable_all(self)
        self.stop()
        embed = interaction.message.embeds[0]
        embed.colour = discord.Colour.red()
        embed.add_field(name='Cancellation Reason', value=cancel_reason)
        member = interaction.guild.get_member(self.receiver_id)
        contents_embed = self.withdrawal.resources.create_embed(title='Withdrawal Contents')
        await asyncio.gather(
            self.bot.remove_view(self),
            interaction.edit_original_response(view=self, embed=embed),
            member.send(f'Your withdrawal request for the following has been cancelled!\n\nReason:\n`{cancel_reason}`',
                        embed=contents_embed),
            self.bot.log(embeds=(
                discordutils.create_embed(
                    user=member,
                    description=f"{member.mention}'s withdrawal was cancelled "
                                f'by {interaction.user.mention} for reason of `{cancel_reason}`'),
                contents_embed
            )))
