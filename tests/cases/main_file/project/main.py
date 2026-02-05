from package.module import Settings
from pydantic_settings import BaseSettings


class MainSettings(BaseSettings):
    main_field: int


class InheritedSettings(Settings):
    child_field: int
