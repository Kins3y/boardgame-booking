from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.sql import func

from app.db.database import Base


class GameMap(Base):
    __tablename__ = "game_maps"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)

    players_count = Column(Integer, nullable=False, default=2)

    grid_width = Column(Integer, nullable=False, default=20)
    grid_height = Column(Integer, nullable=False, default=20)

    is_active = Column(Boolean, nullable=False, default=True)

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False
    )