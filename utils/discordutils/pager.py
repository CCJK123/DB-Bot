from collections import abc

import discord

from utils import config, discordutils

__all__ = ('Pager',)


class PagerButton(discord.ui.Button['Pager']):
    def __init__(self):
        super().__init__()

    async def callback(self, interaction: discord.Interaction) -> object:
        pass


class Pager(discord.ui.View):
    def __init__(self, embeds: abc.Sequence[discord.Embed | abc.Sequence[discord.Embed]],
                 *, timeout: float = config.timeout, initial_index: int = 0):
        super().__init__(timeout=timeout)
        self.interaction: discord.Interaction | None = None
        self.embeds = embeds
        self.index = initial_index
        self.left_left.disabled = self.left.disabled = initial_index == 0
        self.right_right.disabled = self.right.disabled = len(embeds) == initial_index + 1
        self.number.disabled = True
        self.number.label = f'Page {initial_index + 1}/{len(self.embeds)}'

    @discord.ui.button(label='<<')
    async def left_left(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.right.disabled:
            self.right_right.disabled = self.right.disabled = False

        self.index = 0
        button.disabled = self.left.disabled = True
        self.number.label = f'Page 1/{len(self.embeds)}'

        if isinstance(e := self.embeds[self.index], discord.Embed):
            await interaction.response.edit_message(view=self, embed=e)
            return
        await interaction.response.edit_message(view=self, embeds=e)

    @discord.ui.button(label='<')
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.right.disabled:
            self.right_right.disabled = self.right.disabled = False

        self.index -= 1
        self.left_left.disabled = button.disabled = self.index == 0
        self.number.label = f'Page {self.index + 1}/{len(self.embeds)}'

        if isinstance(e := self.embeds[self.index], discord.Embed):
            await interaction.response.edit_message(view=self, embed=e)
            return
        await interaction.response.edit_message(view=self, embeds=e)

    @discord.ui.button()
    async def number(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label='>')
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.left.disabled:
            self.left_left.disabled = self.left.disabled = False

        self.index += 1
        self.right_right.disabled = button.disabled = self.index + 1 == len(self.embeds)
        self.number.label = f'Page {self.index + 1}/{len(self.embeds)}'

        if isinstance(e := self.embeds[self.index], discord.Embed):
            await interaction.response.edit_message(view=self, embed=e)
            return
        await interaction.response.edit_message(view=self, embeds=e)

    @discord.ui.button(label='>>')
    async def right_right(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.left.disabled:
            self.left_left.disabled = self.left.disabled = False

        self.index = len(self.embeds) - 1
        button.disabled = self.right.disabled = self.index + 1 == len(self.embeds)
        self.number.label = f'Page {len(self.embeds)}/{len(self.embeds)}'

        if isinstance(e := self.embeds[self.index], discord.Embed):
            await interaction.response.edit_message(view=self, embed=e)
            return
        await interaction.response.edit_message(view=self, embeds=e)

    async def on_timeout(self) -> None:
        self.left.disabled = True
        self.right.disabled = True
        self.stop()
        await self.interaction.edit_original_response(view=self)

    async def respond(self, interaction: discord.Interaction, ephemeral: bool = False):
        self.interaction = interaction
        if isinstance(e := self.embeds[self.index], discord.Embed):
            await discordutils.interaction_send(interaction, view=self, embed=e, ephemeral=ephemeral)
            return
        await discordutils.interaction_send(interaction, view=self, embeds=e, ephemeral=ephemeral)

    async def update(self):
        if isinstance(e := self.embeds[self.index], discord.Embed):
            await self.interaction.edit_original_response(view=self, embed=e)
            return
        await self.interaction.edit_original_response(view=self, embeds=e)
