from sqlalchemy import Column, Integer, String, Boolean, ForeignKey

from app.db.database import Base


class StarSystem(Base):
    __tablename__ = "star_systems"

    id = Column(Integer, primary_key=True, index=True)

    map_id = Column(Integer, ForeignKey("game_maps.id"), nullable=False)

    name = Column(String, nullable=False)

    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)

    is_start = Column(Boolean, default=False)

    is_archive = Column(Boolean, default=False)

    mineral_slots = Column(Integer, default=1)

    energy_slots = Column(Integer, default=1)

    storage_slots = Column(Integer, default=1)