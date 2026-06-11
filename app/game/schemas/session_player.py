from pydantic import BaseModel


class SessionPlayerCreate(BaseModel):
    user_id: int
    civilization_id: int | None = None
    faction_name: str
    start_system_id: int | None = None