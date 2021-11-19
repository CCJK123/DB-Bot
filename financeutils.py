from __future__ import annotations

import asyncio
from typing import Callable, Awaitable, Literal, Optional
from dataclasses import dataclass, field

import discord

import pnwutils



__all__ = ('RequestData', 'RequestChoices', 'ResourceSelectView')



@dataclass
class RequestData:
    requester: discord.abc.User
    kind: str
    reason: str
    nation_name: str
    nation_link: str
    resources: pnwutils.Resources
    note: str
    additional_info: Optional[dict[str, str]] = field(default_factory=dict)



class RequestChoice(discord.ui.Button['RequestChoices']):
    def __init__(self, label: str):
        super().__init__(row=0, custom_id=label)
        self.label = label

    async def callback(self, interaction: discord.Interaction) -> None:
        self.style = discord.ButtonStyle.success
        for child in self.view.children:
            if self.label != 'Accepted' or child.label != 'Sent':
                # If self.label == Accepted and child.label ==. Sent, dont disable
                child.disabled = True
        if self.label != 'Accepted':
            self.view.stop()
        await interaction.response.edit_message(view=self.view)
        await self.view.callback(self.label, self.view.data, interaction.user,
                                 interaction.message)



class RequestChoices(discord.ui.View):
    def __init__(self, callback: Callable[[
        Literal['Accepted', 'Rejected',
                'Sent'], RequestData, discord.abc.User, discord.Message
    ], Awaitable[None]], req_data: RequestData):
        # Callback would be called with 'Accepted', 'Rejected', or 'Sent'
        super().__init__(timeout=None)
        self.data = req_data
        self.callback = callback
        for c in ('Accepted', 'Rejected', 'Sent'):
            self.add_item(RequestChoice(c))



class ResourceSelector(discord.ui.Select['ResourceSelectView']):
    def __init__(self):
        options = [
            discord.SelectOption(label=s) for s in pnwutils.Constants.all_res
        ]
        super().__init__(placeholder='Choose the resources you want',
                         min_values=1,
                         max_values=len(options),
                         options=options)

    async def callback(self, interaction: discord.Interaction):
        if self.view.user_id is not None and interaction.user.id != self.view.user_id:
            await interaction.send('You are not the intended recipent of this component, '
                                   f'{interaction.user.mention}',
                                   allowed_mentions=discord.AllowedMentions.none())
            return 
        self.view.set_result(self.values)
        self.disabled = True
        await interaction.response.edit_message(view=self.view)



class ResourceSelectView(discord.ui.View):
    def __init__(self, timeout: float, user_id: Optional[int] = None):
        super().__init__(timeout=timeout)
        self._fut = asyncio.get_event_loop().create_future()
        self.add_item(ResourceSelector(user_id))

    def set_result(self, r: list[str]) -> None:
        self._fut.set_result(r)

    def result(self) -> Awaitable[list[str]]:
        return self._fut
    
    async def on_timeout(self):
        self._fut.set_exception(asyncio.TimeoutError())