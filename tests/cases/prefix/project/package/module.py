from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="my_prefix__")
    field: int


class DictSettings(BaseSettings):
    model_config = {"env_prefix": "dict_prefix__"}
    other_field: str
