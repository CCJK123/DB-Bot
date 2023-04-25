from __future__ import annotations

import pickle
from collections.abc import AsyncIterable, Awaitable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bot.utils import discordutils

from . import classes


class ViewTable(classes.Table):
    def __init__(self, database: classes.Database, name: str):
        super().__init__(database, name, {'id': 'INT PRIMARY KEY', 'data': 'BYTEA NOT NULL'})

    async def create(self) -> str:
        return (await super().create() + '\n' +
                await self.database.execute(f'CREATE SEQUENCE IF NOT EXISTS view_id_seq OWNED BY {self.name}.id'))

    async def get(self, view_id: int) -> discordutils.PersistentView:
        return pickle.loads(await self.database.fetch_val(f'SELECT data FROM {self.name} WHERE id = $1', view_id))

    async def get_all(self) -> AsyncIterable[discordutils.PersistentView]:
        async with self.database.acquire() as conn:
            async with conn.transaction():
                async for record in conn.cursor(f'SELECT data FROM {self.name}'):
                    yield pickle.loads(record['data'])

    def add(self, view: discordutils.PersistentView) -> Awaitable[object]:
        data = pickle.dumps(view)
        return self.database.execute(f'INSERT INTO {self.name}(id, data) VALUES ($1, $2)', view.custom_id, data)

    def remove(self, view_id: int) -> Awaitable[object]:
        return self.database.execute(f'DELETE FROM {self.name} WHERE id = $1', view_id)

    def get_id(self) -> Awaitable[int]:
        return self.database.fetch_val("SELECT nextval('view_id_seq')")
