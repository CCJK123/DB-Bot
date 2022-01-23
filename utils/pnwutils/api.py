from itertools import chain
from typing import Any, Iterable

import aiohttp

__all__ = ('APIError', 'construct_query', 'post_query')

from . import constants


class APIError(Exception):
    """Error raised when an exception occurs when trying to call the API."""


def construct_query(q: str, var: dict[str, Any]) -> dict[str, str | dict[str, Any]]:
    return {'query': q, 'variables': var}


async def post_query(sess: aiohttp.ClientSession,
                     query_string: str,
                     query_variables: dict[str, Any],
                     query_type: str,
                     check_more: bool = False
                     ) -> Iterable[dict[str, Any]] | dict[str, Any]:

    # "alex put a limit of 500 entries returned per call, check_more decides if i should try check if i should be
    # getting the next 500 entries" - chez
    # Set page to first page if more entries than possible in 1 call wanted
    if check_more and query_variables.get('page') is None:
        query_variables['page'] = 1

    # Create query and get data
    query = construct_query(query_string, query_variables)
    async with sess.post(constants.api_url, json=query) as response:
        data = await response.json()
    if 'data' not in data.keys():
        raise APIError(f'Error in fetching data: {data["errors"]}')
    data = data['data'][query_type]
    # Get data from other pages, if they exist
    if check_more and data['paginatorInfo']['hasMorePages']:
        query_variables = query_variables.copy()
        query_variables['page'] += 1

        # linter does not realise that in this case, the post_query call will always return Iterable[dict[str, Any]]
        return chain(data, await post_query(sess, query_string, query_variables, query_type, True))

    return data
