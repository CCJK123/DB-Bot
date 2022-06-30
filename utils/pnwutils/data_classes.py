import datetime
import enum
from dataclasses import dataclass

import aiohttp

from . import api, resources
from .. import config

__all__ = ('Transaction', 'EntityType', 'TransactionType', 'WithdrawalResult', 'Withdrawal')

from ..queries import withdrawal_query


class EntityType(enum.Enum):
    NATION = 1
    ALLIANCE = 2


class TransactionType(enum.Enum):
    DEPOSIT = 0
    WITHDRAW = 1


@dataclass()
class Transaction:
    resources: resources.Resources
    time: datetime.datetime
    transaction_type: TransactionType
    entity_type: EntityType
    entity_id: int

    @classmethod
    def from_api_dict(cls, data: dict) -> 'Transaction':
        res = resources.Resources.from_dict(data)
        t = datetime.datetime.fromisoformat(data['date'])

        if data['sender_type'] == 2 and data['sender_id'] == config.alliance_id:
            # sender is our alliance
            e_type = EntityType.NATION if data['recipient_type'] == 1 else EntityType.ALLIANCE
            return cls(res, t, TransactionType.WITHDRAW, e_type, int(data['recipient_id']))
        else:
            # receiver is our alliance
            e_type = EntityType.NATION if data['sender_type'] == 1 else EntityType.ALLIANCE
            return cls(res, t, TransactionType.DEPOSIT, e_type, int(data['sender_id']))


class WithdrawalResult(enum.Enum):
    SUCCESS = 0
    LACK_RESOURCES = 1
    BLOCKADED = 2


@dataclass()
class Withdrawal:
    resources: resources.Resources
    entity_id: int
    entity_type: EntityType = EntityType.NATION
    note: str = ''
    sent: bool = False

    async def withdraw(self, session: aiohttp.ClientSession) -> WithdrawalResult:
        if self.sent:
            raise ValueError('This withdrawal has already been sent!')
        if not self.resources:
            raise ValueError('Attempting to send nothing!')

        try:
            await withdrawal_query.query(session, receiver_id=self.entity_id, receiver_type=self.entity_type.value,
                                         note=self.note, **self.resources.to_dict())
        except api.APIError as e:
            if e.info[0]['message'] == "You don't have enough resources.":
                return WithdrawalResult.LACK_RESOURCES
            elif e.info[0]['message'] == "You can't withdraw resources to a blockaded nation.":
                return WithdrawalResult.BLOCKADED
            raise
        self.sent = True
        return WithdrawalResult.SUCCESS
