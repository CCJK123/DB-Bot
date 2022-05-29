from __future__ import annotations

import abc
import asyncio
from collections.abc import Awaitable, Callable, Iterable
from typing import Any, Generic, TypeVar

__all__ = ('Database', 'Table', 'KVTable')

import asyncpg

R = TypeVar('R')


class RecordClass(asyncpg.Record):
    def __getattr__(self, item):
        return self['item']


class Database(abc.ABC, Generic[R]):
    __slots__ = ('on_init', 'tables')

    def __init__(self):
        self.on_init: list[Awaitable[object]] = []
        self.tables: dict[str, Table] = {}

    def add_on_init(self, coroutine_func: Callable[['Database'], Awaitable[object]]
                    ) -> Callable[['Database'], Awaitable[object]]:
        self.on_init.append(coroutine_func(self))
        return coroutine_func

    async def initialise(self) -> None:
        await asyncio.gather(*self.on_init)
        await asyncio.gather(*(table.create() for table in self.tables.values()))

    @abc.abstractmethod
    async def __aenter__(self):
        ...

    @abc.abstractmethod
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        ...

    @abc.abstractmethod
    async def execute(self, query, *args, timeout: float | None = None) -> str:
        ...

    @abc.abstractmethod
    async def execute_many(self, query, args, *, timeout: float | None = None) -> str:
        ...

    @abc.abstractmethod
    async def fetch(self, query, *args, timeout: float | None = None) -> Iterable[R]:
        ...

    @abc.abstractmethod
    async def fetch_row(self, query, *args, timeout: float | None = None) -> R | None:
        ...

    @abc.abstractmethod
    async def fetch_val(self, query, *args, timeout: float | None = None) -> Any:
        ...

    @abc.abstractmethod
    async def acquire(self) -> Any:
        ...

    def new_table(self, name: str, additional: str = '', **cols: str) -> None:
        table = Table(self, name, cols, additional)
        self.tables[name] = table

    def new_kv(self, name: str, t: str) -> None:
        table = KVTable(self, name, t)
        self.tables[table.name] = table

    def add_table(self, table: 'Table') -> None:
        self.tables[table.name] = table

    def get_table(self, name: str) -> 'Table':
        return self.tables[name]

    def get_kv(self, name: str) -> 'KVTable':
        return self.tables[name]  # type: ignore


T = TypeVar('T')


class Query(Awaitable[T]):
    __slots__ = ('query', 'table', 'coro', 'args')

    def __init__(self, table: Table, query: str, coro: Callable[..., Awaitable], args: Iterable | None = None):
        self.query = query
        self.table = table
        self.coro = coro
        self.args: Iterable = () if args is None else args

    def __await__(self):
        return self.coro(self.query, *self.args).__await__()

    def where(self, condition: str | None = None, **conditions: Any) -> Query:
        if condition is None:
            self.query += ' WHERE ' + ' AND '.join(f'{k} = ${i}' for i, k in enumerate(conditions.keys(), 1))
            self.args = conditions.values()
        else:
            self.query += f' WHERE {condition}'
        return self

    def returning(self, returning) -> Query:
        self.query += f' RETURNING {returning}'
        self.coro = self.table.database.fetch
        return self

    def returning_row(self, returning) -> Query:
        self.query += f' RETURNING {returning}'
        self.coro = self.table.database.fetch_row
        return self

    def returning_val(self, returning) -> Query:
        self.query += f' RETURNING {returning}'
        self.coro = self.table.database.fetch_val
        return self

    def cursor(self, conn):
        return conn.cursor(self.query, *self.args)

    def on_conflict(self, target: str):
        self.query += f'ON CONFLICT {target} DO'
        return self

    def action_nothing(self):
        self.query += ' NOTHING'
        return self

    def action_update(self, updates):
        self.query += f' UPDATE SET {updates}'
        return self

    def where_or(self, **conditions):
        self.query += ' OR '.join((f'{k} = {v}' for k, v in conditions.items()))
        return self


class Table:
    __slots__ = ('database', 'name', 'cols', 'additional')

    def __init__(self, database: Database, name: str, cols: dict[str, str], additional: str = ''):
        self.database = database
        self.name = name
        self.cols = cols
        self.additional = additional

    def create(self) -> Awaitable[str]:
        cols_string = ','.join(f'{n} {t}' for n, t in self.cols.items())
        return self.database.execute(f'CREATE TABLE IF NOT EXISTS {self.name} ({cols_string}{self.additional})')

    def _select_string(self, selecting: str):
        return f'SELECT {selecting} FROM {self.name}'

    def select(self, *to_select) -> Query[list]:
        if to_select:
            return Query(self, self._select_string(','.join(to_select)), self.database.fetch)
        return Query(self, self._select_string('*'), self.database.fetch)

    def select_row(self, *to_select: str) -> Query:
        return Query(self, self._select_string(','.join(to_select)), self.database.fetch_row)

    def select_val(self, col: str) -> Query:
        return Query(self, self._select_string(col), self.database.fetch_val)

    async def exists(self, **conditions: Any) -> bool:
        return await Query(self, self._select_string('true'), self.database.fetch_val).where(**conditions) is not None

    async def exists_or(self, **conditions: Any) -> bool:
        return await Query(self, self._select_string('true'), self.database.fetch_val
                           ).where_or(**conditions) is not None

    def insert(self, **to_insert: Any) -> Query[str]:
        values_string = ','.join(f'${i}' for i in range(1, len(to_insert) + 1))
        return Query(self, f'INSERT INTO {self.name}({",".join(to_insert.keys())}) VALUES ({values_string})',
                     self.database.execute, to_insert.values())

    def insert_many(self, *cols: str, values: Iterable[Iterable]) -> Query[None]:
        values_string = ','.join(f'${i}' for i in range(1, len(cols) + 1))
        return Query(self, f'INSERT INTO {self.name}({",".join(cols)}) VALUES ({values_string})',
                     self.database.execute_many, (values,))

    def update(self, updates: str) -> Query[str]:
        return Query(self, f'UPDATE {self.name} SET {updates}', self.database.execute)

    def delete(self) -> Query:
        return Query(self, f'DELETE FROM {self.name}', self.database.execute)


class KVTable(Table, Generic[T]):
    __slots__ = ()

    def __init__(self, database: Database, name: str, t: str):
        super().__init__(database, name, {'key': 'TEXT PRIMARY KEY', 'value': f'{t} NOT NULL'})

    def get(self, key: str) -> Awaitable[T | None]:
        return self.database.fetch_val(f'SELECT value FROM {self.name} WHERE key = $1', key)

    async def is_set(self, key: str) -> bool:
        return await self.database.fetch_val(f'SELECT TRUE FROM {self.name} WHERE key = $1', key) is not None

    async def all_set(self, *keys: str) -> bool:
        keys_string = ','.join(f'${i}' for i in range(1, len(keys) + 1))
        return await self.database.fetch_val(f'SELECT COUNT(*) FROM {self.name} WHERE key IN ({keys_string})',
                                             *keys) == len(keys)

    def set(self, key: str, value: T) -> Awaitable[str]:
        return self.database.execute(f'''
            INSERT INTO {self.name}(key, value) VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
        ''', key, value)

    def set_many(self, **kv: T):
        values_str = ','.join(f'({k},{v})' for k, v in kv.items())
        return self.database.execute(f'''
            INSERT INTO {self.name}(key, value) VALUES {values_str}
            ON CONFLICT (value) DO UPDATE SET value = EXCLUDED.value
        ''')
