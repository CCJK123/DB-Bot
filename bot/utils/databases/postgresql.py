from __future__ import annotations

from collections.abc import Awaitable, Iterable
from typing import Any, TypeVar

import asyncpg

from . import classes

__all__ = ('PGDatabase',)

R = TypeVar('R')


class PGDatabase(classes.Database[R]):
    __slots__ = ('pool', 'coro')

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.pool = asyncpg.create_pool(*args, **kwargs)

    async def __aenter__(self):
        await self.pool.__aenter__()
        await self.initialise()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.pool.__aexit__(exc_type, exc_val, exc_tb)

    def execute(self, query, *args, timeout: float | None = None) -> Awaitable[str]:
        return self.pool.execute(query, *args, timeout=timeout)

    def execute_many(self, query, args, *, timeout: float | None = None) -> Awaitable[None]:
        return self.pool.executemany(query, args, timeout=timeout)

    def fetch(self, query, *args, timeout: float | None = None) -> Awaitable[Iterable]:
        return self.pool.fetch(query, *args, timeout=timeout)

    def fetch_row(self, query, *args, timeout: float | None = None) -> Awaitable[R | None]:
        return self.pool.fetchrow(query, *args, timeout=timeout)

    def fetch_val(self, query, *args, timeout: float | None = None) -> Awaitable[Any]:
        return self.pool.fetchval(query, *args, timeout=timeout)

    def acquire(self):
        return self.pool.acquire()
