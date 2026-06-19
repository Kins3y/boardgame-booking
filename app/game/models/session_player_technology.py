from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint

from app.db.database import Base


class SessionPlayerTechnology(Base):
    __tablename__ = "session_player_technologies"

    id = Column(Integer, primary_key=True, index=True)

    session_id = Column(Integer, ForeignKey("game_sessions.id"), nullable=False, index=True)
    player_id = Column(Integer, ForeignKey("session_players.id"), nullable=False, index=True)

    technology_key = Column(String(100), nullable=False, index=True)
    researched_round = Column(Integer, nullable=False, default=1)

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "player_id",
            "technology_key",
            name="uq_session_player_technology",
        ),
    )
