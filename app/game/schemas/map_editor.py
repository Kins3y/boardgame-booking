from pydantic import BaseModel, Field


class MapEditorSystemInput(BaseModel):
    client_id: str = Field(min_length=1)

    name: str = Field(min_length=1, max_length=100)

    x: int = Field(ge=0)
    y: int = Field(ge=0)

    system_type: str = Field(pattern="^(normal|start|archive)$")
    archive_level: int | None = Field(default=None, ge=1, le=5)

    mineral_slots: int = Field(default=1, ge=0, le=9)
    energy_slots: int = Field(default=1, ge=0, le=9)
    storage_slots: int = Field(default=1, ge=0, le=9)
    research_center_slots: int = Field(default=0, ge=0, le=9)


class MapEditorConnectionInput(BaseModel):
    from_client_id: str = Field(min_length=1)
    to_client_id: str = Field(min_length=1)

    is_dangerous: bool = False
    is_wraparound: bool = False


class MapEditorSaveRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    players_count: int = Field(ge=2, le=6)

    grid_width: int = Field(default=20, ge=5, le=99)
    grid_height: int = Field(default=20, ge=5, le=99)

    systems: list[MapEditorSystemInput] = Field(default_factory=list)
    connections: list[MapEditorConnectionInput] = Field(default_factory=list)