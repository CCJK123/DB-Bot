from itertools import chain
from typing import Any, Iterable

import aiohttp

__all__ = ('APIError', 'APIQuery')

from . import constants


class APIError(Exception):
    """Error raised when an exception occurs when trying to call the API."""


class APIQuery:
    def __init__(self, query_text: str, check_more: bool = False, **variable_types: dict[str: type]):
        self.query_text = query_text
        self.variable_types = variable_types
        self.check_more = check_more

        if check_more:
            self.variable_types['page'] = int

    def get_query(self, variables: dict[str, Any]) -> dict[str, str | dict[str, Any]]:
        return {'query': self.query_text, 'variables': variables}

    async def query(self, session: aiohttp.ClientSession, **variables) -> Iterable[dict[str, Any]] | dict[str, Any]:
        # alex put a limit of 500 entries returned per call, check_more decides if we should
        # try to get the next 500 entries
        # Set page to first page if more entries than possible in 1 call wanted
        if self.check_more:
            variables.setdefault('page', 1)

        if not set(variables.keys()) <= set(self.variable_types.keys()):
            raise APIError(f'Key mismatch! Variables: {self.variable_types}, Passed: {variables}')

        for k in variables:
            ty = self.variable_types[k]
            if isinstance(ty, list):
                variables[k] = list(map(ty[0], variables[k]))
            else:
                variables[k] = ty(variables[k])

        async with session.post(constants.api_url, json=self.get_query(variables)) as response:
            data = await response.json()

        try:
            data = data['data']
        except KeyError:
            raise APIError(f'Error in fetching data: {data["errors"]}') from None
        except TypeError:
            if isinstance(data, list):
                raise APIError(f'Error in fetching data: {data[0]["errors"][0]["message"]}') from None
            raise

        # get the only child of the dict
        data = next(iter(data.values()))

        if self.check_more and data['paginatorInfo']['hasMorePages']:
            variables['page'] += 1

            # linter does not realise that in this case, the query call will always return Iterable[dict[str, Any]]
            return chain(data, await self.query(session, **variables))

        return data
