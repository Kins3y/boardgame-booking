from pydantic import BaseModel


class SystemConnectionCreate(BaseModel):
    map_id: int
    from_system_id: int
    to_system_id: int