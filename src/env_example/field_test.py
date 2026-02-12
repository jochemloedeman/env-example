from pydantic import BaseModel, Field


class Model(BaseModel):
    still_required: int = Field(1)


if __name__ == "__main__":
    m = Model()
