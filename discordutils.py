import asyncio
import operator
import sys
import traceback
import os   # For env variables
from typing import Awaitable, Mapping

import discord
from discord.ext import commands



# Setup what is exported by default
__all__ = ('Config', 'Choices', 'construct_embed', 'gov_check')



# Setup discord bot configuration variables
class Config:
    token: str = os.environ['bot_token']
    timeout: float = 300
    gov_role_id: int = 595155137274839040



# Setup buttons for user to make choices
class Choice(discord.ui.Button['Choices']):
    def __init__(self, label: str):
        super().__init__()
        self.label = label


    async def callback(self, interaction: discord.Interaction) -> None:
        self.view.set_result(self.label)
        self.style = discord.ButtonStyle.success
        for child in self.view.children:
            # assert isinstance(child, discord.ui.Button)  # just to shut up the linter
            child.disabled = True
        self.view.stop()
        await interaction.response.edit_message(view=self.view)



class Choices(discord.ui.View):
    def __init__(self, *choices: str):
        super().__init__()
        self._fut = asyncio.get_event_loop().create_future()
        for c in choices:
            self.add_item(Choice(c))


    def set_result(self, r: str) -> None:
        self._fut.set_result(r)


    def result(self) -> Awaitable[str]:
        return self._fut
    

    async def on_timeout(self):
        self._fut.set_exception(asyncio.TimeoutError())
    


# Create embed from dictionary of key-value pairs
def construct_embed(fields: Mapping[str, str], /, **kwargs: str) -> discord.Embed:
    embed = discord.Embed(**kwargs)
    for k, v in fields.items():
        embed.add_field(name=k, value=v)
    return embed



# Check if user in DB government
async def gov_check(ctx: commands.Context) -> bool:    
    # Check if command was sent in DB server or in DM
    if isinstance(ctx.author, discord.Member):
        # Sent from DB server - Check server roles
        # Check if server member has id of "The Black Hand" role
        if Config.gov_role_id in map(operator.attrgetter('id'), ctx.author.roles):
            return True
        # Inform non-gov members about their lack of permissions
        await ctx.send("You do not have the necessary permissions to run this command.")

    else:
        # type(ctx.author) == discord.User
        # Sent from DM - Ignore
        await ctx.send("Kindly run this command on the DB server.")
        
    return False



async def default_error_handler(context: commands.Context, exception: commands.CommandError) -> None:
    print(f'Ignoring exception in command {context.command}:', file=sys.stderr)
    traceback.print_exception(type(exception), exception, exception.__traceback__, file=sys.stderr)


class Storage:
    pass