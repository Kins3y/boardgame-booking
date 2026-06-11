from pydantic import BaseModel


class GameMapCreate(BaseModel):
    name: str