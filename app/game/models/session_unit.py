from sqlalchemy import Column, Integer, String, ForeignKey, Boolean

from app.db.database import Base


class SessionUnit(Base):
    __tablename__ = "session_units"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(Integer, ForeignKey("game_sessions.id"), nullable=False)
    owner_player_id = Column(Integer, ForeignKey("session_players.id"), nullable=False)
    system_id = Column(Integer, ForeignKey("star_systems.id"), nullable=False)

    unit_type = Column(String, nullable=False)
    state = Column(String, nullable=False, default="deployed")

    attack = Column(Integer, default=0)
    defense = Column(Integer, default=0)

    current_hp = Column(Integer, nullable=True)
    max_hp = Column(Integer, nullable=True)

    food_upkeep = Column(Integer, default=1)

    is_foundation = Column(Boolean, default=False, nullable=False)