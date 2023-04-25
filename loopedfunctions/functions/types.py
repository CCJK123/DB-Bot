from typing import TypedDict


class RestrictionsDict(TypedDict):
    min_cities: int
    max_inactive: int
    exclude: list[int]


class MessageDict(TypedDict):
    subject: str
    body: str


class SettingsDict(TypedDict):
    frequency: int
    email: str
    password: str
    log_path: str
    contacted_path: str
    api_key: str
    message: MessageDict
    restrictions: RestrictionsDict
