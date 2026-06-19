from pydantic import BaseModel, Field


class ArchiveResearchRequest(BaseModel):
    system_id: int = Field(gt=0)
