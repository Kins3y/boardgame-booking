from sqlalchemy import Column, ForeignKey, Integer, String, UniqueConstraint

from app.db.database import Base


class SessionPlayerBlueprint(Base):
    __tablename__ = "session_player_blueprints"

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
    blueprint_level = Column(Integer, nullable=False)
    blueprint_key = Column(String(64), nullable=False)
    archive_system_id = Column(
        Integer,
        ForeignKey("star_systems.id", ondelete="SET NULL"),
        nullable=True,
    )
    discovered_round = Column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "player_id",
            "blueprint_level",
            name="uq_session_player_blueprint_level",
        ),
    )
