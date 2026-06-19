from pydantic import BaseModel, Field


class ArchonCoreClaimRequest(BaseModel):
    system_id: int | None = Field(
        default=None,
        description="Optional Heart of the Galaxy system id. If omitted, the current player's controlled Archive V system is used.",
    )
