from pydantic import BaseModel


class StarSystemCreate(BaseModel):
    map_id: int
    name: str

    x: int
    y: int

    is_start: bool = False
    is_archive: bool = False

    mineral_slots: int = 1
    energy_slots: int = 1
    storage_slots: int = 1