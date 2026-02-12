from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    required_field: int
    explicit_required: int = Field(..., frozen=True)
    implicit_required: int = Field(frozen=True)
    plain_default: str | None = None
    keyword_default: str | None = Field(default=None)
    positional_default: int = Field(42)
    factory_default: list[str] = Field(default_factory=list)
