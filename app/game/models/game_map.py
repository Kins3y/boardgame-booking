from sqlalchemy import Column, Integer, String

from app.db.database import Base


class GameMap(Base):
    __tablename__ = "game_maps"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)