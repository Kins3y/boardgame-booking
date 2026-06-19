from sqlalchemy import Column, ForeignKey, Integer, UniqueConstraint

from app.db.database import Base


class SessionArchonCoreClaim(Base):
    __tablename__ = "session_archon_core_claims"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(
        Integer,
        ForeignKey("game_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    player_id = Column(
        Integer,
        ForeignKey("session_players.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    core_system_id = Column(
        Integer,
        ForeignKey("star_systems.id", ondelete="SET NULL"),
        nullable=True,
    )
    claimed_round = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            name="uq_session_archon_core_claim",
        ),
    )
