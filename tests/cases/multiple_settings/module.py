from pydantic_settings import BaseSettings


class SomeSettings(BaseSettings):
    some_field: int


class OtherSettings(BaseSettings):
    other_field: str
