from pydantic_settings import BaseSettings


class ParentSettings(BaseSettings):
    parent_field: str
