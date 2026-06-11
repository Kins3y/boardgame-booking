from sqlalchemy import Column, Integer, ForeignKey

from app.db.database import Base


class SessionSystem(Base):
    __tablename__ = "session_systems"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(Integer, ForeignKey("game_sessions.id"), nullable=False)
    system_id = Column(Integer, ForeignKey("star_systems.id"), nullable=False)

    owner_player_id = Column(Integer, ForeignKey("session_players.id"), nullable=True)