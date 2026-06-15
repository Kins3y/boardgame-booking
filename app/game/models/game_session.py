from sqlalchemy import Column, Integer, String, ForeignKey

from app.db.database import Base


class GameSession(Base):
    __tablename__ = "game_sessions"

    id = Column(Integer, primary_key=True, index=True)

    map_id = Column(Integer, ForeignKey("game_maps.id"), nullable=False)

    name = Column(String, nullable=False)

    status = Column(String, default="created")
    current_round = Column(Integer, default=1)

    play_mode = Column(
        String,
        nullable=False,
        default="hotseat"
    )

    current_player_id = Column(
        Integer,
        nullable=True
    )

    current_turn_index = Column(
        Integer,
        nullable=False,
        default=0
    )

    round_phase = Column(
        String,
        nullable=False,
        default="setup"
    )