import asyncio
from datetime import datetime, timezone, timedelta

import aiofiles
import aiohttp

from . import types, constants


class Recruiter:
    def __init__(self, session: aiohttp.ClientSession, data: types.SettingsDict):
        self.session = session
        self.settings = data
        self.contacted: list[str] | None = None

    async def login(self):
        payload = {
            'email': self.settings['email'],
            'password': self.settings['password'],
            'loginform': 'Login'
        }
        async with self.session.post(constants.login_url, data=payload) as resp:
            print(await resp.read())

        async with aiofiles.open(self.settings['contacted_path']) as f:
            self.contacted = (await f.read()).split(',')

    async def run_once(self, now: datetime):
        api_url = (f'{constants.api_base_url}nations/{self.settings["api_key"]}/&v_mode=0&alliance_position=0'
                   f'&min_cities={self.settings["restrictions"]["min_cities"]}')
        async with self.session.get(api_url) as resp:
            data = await resp.json()

        contacting = []
        for nation in data:
            if await self.should_contact(nation, now):
                await self.send_message(nation)
                contacting.append(nation['nationid'])
                await asyncio.sleep(0.01)

        if contacting:
            async with aiofiles.open(self.settings['contacted_path'], 'a') as f:
                await f.write(',' + ','.join(contacting))
            self.contacted.extend(contacting)

    async def send_message(self, nation: dict[str, str]):
        payload = {
            'newconversation': 'true',
            'receiver': nation['leader'],
            'carboncopy': "",
            'subject': self.replace_parameters(self.settings['message']['subject'], nation),
            'body': self.replace_parameters(self.settings['message']['body'], nation),
            'sndmsg': 'Send Message'
        }
        async with self.session.post(constants.api_base_url, data=payload) as resp:
            print(await resp.read())

    async def should_contact(self, nation: dict[str, str | int], now: datetime):
        if int(nation['minutessinceactive']) > self.settings['restrictions']['max_inactive']:
            return False
        if int(nation['nationid']) in self.settings['restrictions']['exclude']:
            return False
        if nation['nationid'] in self.contacted:
            return False
        if datetime.fromisoformat(nation['founded']).replace(tzinfo=timezone.utc) - now < timedelta(minutes=4):
            return False
        return True

    @staticmethod
    def replace_parameters(text: str, nation: dict) -> str:
        params = {
            'nation': nation['nation'],
            'leader': nation['leader'],
            'id': nation['nationid'],
            'score': nation['score'],
            'cities': nation['cities'],
            'infra': nation['infrastructure'],
            'color': nation['color']
        }
        for param, value in params.items():
            text = text.replace(f'${{{param}}}', str(value))
        return text
