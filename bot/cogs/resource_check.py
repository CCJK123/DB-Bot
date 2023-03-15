import operator

import discord
from discord.ext import tasks

from .. import dbbot
from ..utils import discordutils
from ..utils.queries import alliance_member_res_query


class ResourceCheckCog(discordutils.CogBase):
    def __init__(self, bot: dbbot.DBBot):
        super().__init__(bot, __name__)
        self.task.start()

    @tasks.loop(hours=2)
    async def task(self):
        data = await alliance_member_res_query.query(self.bot.session, alliance_id=config.alliance_id)
        result = {'Food': [], 'Food And Uranium': [], 'Uranium': []}
        ids = set()
        for nation in data:
            if nation['alliance_position'] == 'APPLICANT' or nation['vacation_mode_turns'] > 0:
                continue
            needs_food = not nation['food']
            # check for nuclear power and uranium amounts
            needs_ura = not nation['uranium'] and any(map(operator.itemgetter('nuclear_power'), nation['cities']))

            if needs_food and needs_ura:
                result['Food And Uranium'].append((nation['id'], nation['nation_name']))
            elif needs_food:
                result['Food'].append((nation['id'], nation['nation_name']))
            elif needs_ura:
                result['Uranium'].append((nation['id'], nation['nation_name']))
            else:
                continue
            ids.add(nation['id'])
        if ids:
            async with self.bot.database.acquire() as conn:
                async with conn.transaction():
                    map_discord = {
                        rec['nation_id']: rec['discord_id']
                        async for rec in
                        self.bot.database
                            .get_table('users')
                            .select('discord_id', 'nation_id')
                            .where(f'nation_id IN ({",".join(map(str, ids))})')
                            .cursor(conn)
                    }
            embed = discord.Embed(title='Ran Out Of...')
            for k, ns in result.items():
                string = '\n'.join((f'<@{d_id}>' if (d_id := map_discord.get(na[0])) else
                                    f'[{na[1]}/{na[0]}]({pnwutils.link.nation(na[0])})') for na in ns)
                if string:
                    embed.add_field(name=k, value=string)
            channel = self.bot.get_channel(await self.bot.database.get_kv("channel_ids").get("res_check_channel"))
            await channel.send(embed=embed)


async def setup(bot: dbbot.DBBot) -> None:
    await bot.add_cog(ResourceCheckCog(bot))
