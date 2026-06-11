from sqlalchemy import Column, Integer, ForeignKey

from app.db.database import Base


class SystemConnection(Base):
    __tablename__ = "system_connections"

    id = Column(Integer, primary_key=True, index=True)

    map_id = Column(Integer, ForeignKey("game_maps.id"), nullable=False)

    from_system_id = Column(Integer, ForeignKey("star_systems.id"), nullable=False)
    to_system_id = Column(Integer, ForeignKey("star_systems.id"), nullable=False)