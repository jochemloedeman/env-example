from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="first_prefix_")
    model_config = SettingsConfigDict(env_prefix="second_prefix_")
    field: int
