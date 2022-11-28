from __future__ import annotations

import asyncio
import datetime

import discord

from .. import dbbot
from ..utils import discordutils, pnwutils


class ResendCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.resend_table = self.bot.database.get_table('to_resend')
        self.sleep_task: asyncio.Task | None = None

    async def cog_load(self) -> None:
        asyncio.create_task(self.wait())

    async def wait(self):
        await self.bot.wait_until_ready()
        while True:
            next_resend = await self.bot.database.fetch_row(
                'SELECT time, channel_id, message_id FROM to_resend ORDER BY time ASC LIMIT 1')
            if next_resend is None:

                return
            now = datetime.datetime.now(tz=datetime.timezone.utc)
            self.sleep_task = asyncio.create_task(
                asyncio.sleep((next_resend['time'] - now).total_seconds() - 3))

            try:
                await self.sleep_task
            except asyncio.CancelledError:
                # cancelled - new resend, next_resend might have changed
                continue

            # resend message
            channel = self.bot.get_channel(next_resend['channel_id'])
            message = await channel.fetch_message(next_resend['message_id'])
            content = message.content
            if content[:3] == '```' == content[-3:]:
                content = content[3:-3]
            await channel.send(content, reference=message)
            # time and message_id should be enough to uniquely identify
            await self.resend_table.delete().where(time=next_resend['time'], message_id=next_resend['message_id'])

    @discord.app_commands.command()
    @discord.app_commands.describe(
        time='When this should be resent, should be as `5t -15m` or `2h 1m`, t - turns, h - hours, m - minutes',
        message_id='Message to resend. If not specified, takes your last message in this channel.')
    async def resend(self, interaction: discord.Interaction, time: str, message_id: int = 0):
        """Resends a message. If message is wrapped in ``` it will remove it"""
        # get message
        if message_id:
            message = await interaction.channel.fetch_message(message_id)
            if message is None:
                await interaction.response.send_message('That message id is not valid!')
                return
        else:
            message = await discord.utils.find(
                lambda m: m.author.id == interaction.user.id, interaction.channel.history())
            if message is None:
                await interaction.response.send_message('A message from you in this channel was not found!')
                return
            message_id = message.id

        # parse time
        resend_time = datetime.datetime.now(tz=datetime.timezone.utc).replace(second=0, microsecond=0)
        try:
            offset = 0
            for token in time.split(' '):
                ty = token[-1]
                amt = int(token[:-1])
                if ty == 't':
                    resend_time = pnwutils.time_after_turns(amt, resend_time)
                elif ty == 'h':
                    offset += amt * 60
                elif ty == 'm':
                    offset += amt
                else:
                    # incorrect format
                    raise ValueError
        except ValueError:
            await interaction.response.send_message(
                'Incorrect time format! Use `1t -15m` for 15 minutes before next turn.\n'
                '`t` - turns, `h` - hours, `m` - minutes')
            return
        resend_time += datetime.timedelta(minutes=offset)
        if resend_time <= datetime.datetime.now(tz=datetime.timezone.utc):
            await interaction.response.send_message('This time is in the past! Aborting...')
            return

        # add to_resend
        await self.resend_table.insert(time=resend_time, channel_id=interaction.channel_id, message_id=message_id)
        # reset sleep task
        if self.sleep_task is not None:
            self.sleep_task.cancel('new resend')
        else:
            asyncio.create_task(self.wait())
        await interaction.response.send_message(
            f'This message will be resent at {discord.utils.format_dt(resend_time)}',
            view=discordutils.LinkView('Message', message.jump_url))


async def setup(bot: dbbot.DBBot) -> None:
    await bot.add_cog(ResendCog(bot))
