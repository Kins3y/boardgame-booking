from pydantic import BaseModel


class CivilizationResponse(BaseModel):
    id: int

    name: str
    slug: str

    short_description: str
    lore_description: str | None = None

    starting_matter: int
    starting_energy: int
    starting_data: int

    ability_name: str
    ability_description: str

    mechanic_key: str

    is_active: bool

    class Config:
        from_attributes = True