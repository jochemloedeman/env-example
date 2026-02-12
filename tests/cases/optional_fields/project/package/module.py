from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    required_field: int
    still_required: int = Field(..., frozen=True)
    optional_field: str | None = None
    another_optional_field: str | None = Field(default=None)
