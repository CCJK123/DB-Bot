from typing import Final

from .. import config

base_url: Final[str] = 'https://politicsandwar.com/'
base_api_url: Final[str] = 'https://api.politicsandwar.com/graphql?api_key='
api_url: Final[str] = base_api_url + config.api_key
all_res: Final[tuple[str, ...]] = ('money', 'food', 'coal', 'oil', 'uranium', 'lead', 'iron', 'bauxite',
                                   'gasoline', 'munitions', 'steel', 'aluminum')
