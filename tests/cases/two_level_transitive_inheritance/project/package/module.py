from pydantic_settings import BaseSettings


class GrandparentSettings(BaseSettings):
    grandparent_field: int


class ParentSettings(GrandparentSettings):
    parent_field: str


class ChildSettings(ParentSettings):
    child_field: bool
