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

    fleet_id = Column(Integer, ForeignKey("session_fleets.id"), nullable=True)
    slot_index = Column(Integer, nullable=True)

    formation_weight = Column(Integer, default=50, nullable=False)
    built_order = Column(Integer, default=0, nullable=False)

    is_combat = Column(Boolean, default=True, nullable=False)
