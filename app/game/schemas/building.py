from typing import Literal

from pydantic import BaseModel


class BuildBuildingCreate(BaseModel):
    session_player_id: int
    system_id: int
    building_type: str