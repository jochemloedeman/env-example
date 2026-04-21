import pydantic_settings
from pydantic import BaseModel
from pydantic_settings import SettingsConfigDict


class SubSettings(BaseModel):
    sub_field: str


class Settings(pydantic_settings.BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="__")
    sub_settings: SubSettings
