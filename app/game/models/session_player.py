from sqlalchemy import Column, Integer, String, ForeignKey, Boolean

from app.db.database import Base


class SessionPlayer(Base):
    __tablename__ = "session_players"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(Integer, ForeignKey("game_sessions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    civilization_id = Column(Integer, ForeignKey("civilizations.id"), nullable=True)

    faction_name = Column(String, nullable=False)

    matter = Column(Integer, default=10)
    energy = Column(Integer, default=5)
    data = Column(Integer, default=1)
    food = Column(Integer, default=10)

    start_system_id = Column(Integer, ForeignKey("star_systems.id"), nullable=True)

    command_points_left = Column(
        Integer,
        nullable=False,
        default=3
    )

    has_passed = Column(
        Boolean,
        nullable=False,
        default=False
    )