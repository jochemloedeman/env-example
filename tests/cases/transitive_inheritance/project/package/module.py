from pydantic_settings import BaseSettings


class ParentSettings(BaseSettings):
    field: int


class ChildSettings(ParentSettings):
    other_field: str
