from sqlalchemy import Column, DateTime, ForeignKey, Integer, JSON, String, func

from app.db.database import Base


class SessionGameLog(Base):
    __tablename__ = "session_game_logs"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer,
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    round_number = Column(Integer, nullable=False, default=1)
    actor_player_id = Column(
        Integer,
        ForeignKey("session_players.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type = Column(String(64), nullable=False, index=True)
    payload = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=False), server_default=func.now(), nullable=False)
