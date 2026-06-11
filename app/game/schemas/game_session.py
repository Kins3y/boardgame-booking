from pydantic import BaseModel


class GameSessionCreate(BaseModel):
    map_id: int
    name: str


class GameSessionUpdateName(BaseModel):
    name: str