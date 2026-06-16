from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, func

from app.db.database import Base


class SessionFleet(Base):
    __tablename__ = "session_fleets"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(Integer, ForeignKey("game_sessions.id"), nullable=False)
    owner_player_id = Column(Integer, ForeignKey("session_players.id"), nullable=False)
    system_id = Column(Integer, ForeignKey("star_systems.id"), nullable=False)

    fleet_number = Column(Integer, nullable=False)
    name = Column(String, nullable=False)

    is_defensive = Column(Boolean, default=False, nullable=False)
    has_acted_this_round = Column(Boolean, default=False, nullable=False)

    created_at = Column(DateTime(timezone=False), server_default=func.now())
