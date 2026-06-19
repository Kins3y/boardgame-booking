from pydantic import BaseModel, Field


class TechnologyResearchRequest(BaseModel):
    technology_key: str = Field(min_length=1)
