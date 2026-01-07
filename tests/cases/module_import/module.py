import pydantic_settings


class Settings(pydantic_settings.BaseSettings):
    field: int
