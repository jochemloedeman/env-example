from pydantic_settings import BaseSettings as bs


class OtherSettings(bs):
    other_field: int
