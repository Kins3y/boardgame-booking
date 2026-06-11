from sqlalchemy import Column, Integer, String, ForeignKey

from app.db.database import Base


class SessionBuilding(Base):
    __tablename__ = "session_buildings"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(Integer, ForeignKey("game_sessions.id"), nullable=False)
    system_id = Column(Integer, ForeignKey("star_systems.id"), nullable=False)
    owner_player_id = Column(Integer, ForeignKey("session_players.id"), nullable=False)

    building_type = Column(String, nullable=False)