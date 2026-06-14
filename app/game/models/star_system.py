from sqlalchemy import Boolean, Column, ForeignKey, Integer, String

from app.db.database import Base


class StarSystem(Base):
    __tablename__ = "star_systems"

    id = Column(Integer, primary_key=True, index=True)

    map_id = Column(
        Integer,
        ForeignKey("game_maps.id"),
        nullable=False
    )

    name = Column(String, nullable=False)

    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)

    # Old compatibility flags
    is_start = Column(Boolean, default=False)
    is_archive = Column(Boolean, default=False)

    # New editor type:
    # normal | start | archive
    system_type = Column(String, nullable=False, default="normal")

    # Only for archive systems, 1-5.
    archive_level = Column(Integer, nullable=True)

    # Building slot limits
    mineral_slots = Column(Integer, default=1)
    energy_slots = Column(Integer, default=1)
    storage_slots = Column(Integer, default=1)
    research_center_slots = Column(Integer, default=0)