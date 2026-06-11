from pydantic import BaseModel


class StartSystemOptionResponse(BaseModel):
    id: int
    name: str
    x: int
    y: int
    is_occupied: bool
    occupied_by_player_id: int | None = None
    occupied_by_faction: str | None = None