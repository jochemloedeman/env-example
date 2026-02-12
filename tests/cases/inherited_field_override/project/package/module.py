from pydantic_settings import BaseSettings


class ParentSettings(BaseSettings):
    required_field: int
    shared_field: str


class ChildSettings(ParentSettings):
    shared_field: str = "default_value"
    child_field: bool
