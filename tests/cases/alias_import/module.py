import pydantic_settings as ps


class Settings(ps.BaseSettings):
    field: int
