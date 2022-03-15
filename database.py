import pickle
from typing import Any

import aiofiles


class RudimentaryDatabase:
    def __init__(self, filename: str):
        self.filename = filename
        self.data = {}

    async def get(self, key: str) -> Any:
        return self.data[key]

    async def set(self, key: str, value: Any) -> None:
        self.data[key] = value

    async def keys(self):
        return self.data.keys()

    async def values(self):
        return self.data.values()

    async def items(self):
        return self.data.items()

    async def load(self):
        try:
            async with aiofiles.open(self.filename, 'rb') as f:
                self.data = pickle.loads(await f.read())
        except FileNotFoundError:
            pass

    async def save(self):
        pickled = pickle.dumps(self.data, 5)
        async with aiofiles.open(self.filename, 'wb') as f:
            await f.write(pickled)

    async def __aenter__(self) -> 'RudimentaryDatabase':
        await self.load()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.save()
