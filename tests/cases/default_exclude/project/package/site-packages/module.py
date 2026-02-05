from pydantic_settings import BaseSettings


class ExcludedSettings(BaseSettings):
    field: int
