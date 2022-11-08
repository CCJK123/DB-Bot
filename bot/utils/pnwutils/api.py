from __future__ import annotations

from typing import Any, Iterable

import aiohttp

__all__ = ('APIError', 'APIQuery')

from . import constants
from .. import config


class APIError(Exception):
    """Error raised when an exception occurs when trying to call the API."""

    def __init__(self, message: str, info: Any = None):
        super().__init__(message)
        self.info = info


class APIQuery:
    def __init__(self, query_text: str, check_more: bool = False, bot_headers: bool = False,
                 **variable_types: type | list[type]):

        self.query_text = query_text
        self.variable_types = variable_types
        self.check_more = check_more
        self.bot_headers = bot_headers

        if check_more:
            self.variable_types['page'] = int

    def get_query(self, variables: dict[str, Any]) -> dict[str, str | dict[str, Any]]:
        return {'query': self.query_text, 'variables': variables}

    async def _query(self, session: aiohttp.ClientSession, api_key: str, variables: dict):
        headers = {'X-Bot-Key': config.api_key_mut, 'X-Api-Key': config.api_key} if self.bot_headers else {}
        async with session.post(constants.base_api_url, params={'api_key': api_key},
                                json=self.get_query(variables), headers=headers) as response:
            data = await response.json()

        try:
            data = data['data']
        except KeyError:
            raise APIError(f'Error in fetching data: {data["errors"]}', data['errors']) from None
        except TypeError:
            if isinstance(data, list):
                error_msg = data[0]["errors"][0]["message"]
                raise APIError(f'Error in fetching data: {error_msg}', error_msg) from None
            raise

        # get the only child of the dict
        return next(iter(data.values()))

    async def query(self, session: aiohttp.ClientSession, *, api_key: str = config.api_key,
                    **variables) -> Iterable[dict[str, Any]] | dict[str, Any]:
        # alex put a limit of 500 entries returned per call, check_more decides if we should
        # try to get the next 500 entries
        # Set page to first page if more entries than possible in 1 call wanted
        if not set(variables.keys()) <= set(self.variable_types.keys()):
            raise APIError(f'Key mismatch! Variables: {self.variable_types}, Passed: {variables}')

        for k in variables:
            ty = self.variable_types[k]
            if isinstance(ty, list):
                variables[k] = list(map(ty[0], variables[k]))
            else:
                variables[k] = ty(variables[k])

        data = await self._query(session, api_key, variables)

        if self.check_more:
            result = data['data']
            while data['paginatorInfo']['hasMorePages']:
                variables['page'] += 1
                data = await self._query(session, api_key, variables)
                result.extend(data['data'])

            # linter does not realise that in this case, the query call will always return Iterable[dict[str, Any]]
            return result
        return data
