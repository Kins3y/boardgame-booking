from typing import Any

from sqlalchemy.orm import Session

from app.game.models.game_session import GameSession
from app.game.models.session_game_log import SessionGameLog
from app.game.models.session_player import SessionPlayer
from app.models.user import User


def get_actor_snapshot(db: Session, actor: SessionPlayer | None) -> dict[str, Any] | None:
    if actor is None:
        return None

    user = db.query(User).filter(User.id == actor.user_id).first()

    return {
        "session_player_id": actor.id,
        "user_id": actor.user_id,
        "nickname": user.nickname if user else None,
        "faction_name": actor.faction_name,
        "civilization_id": actor.civilization_id,
    }


def create_game_log(
    db: Session,
    session: GameSession,
    event_type: str,
    actor: SessionPlayer | None = None,
    payload: dict[str, Any] | None = None,
    round_number: int | None = None,
) -> SessionGameLog:
    event_payload = dict(payload or {})
    event_payload.setdefault("actor", get_actor_snapshot(db, actor))

    log_entry = SessionGameLog(
        session_id=session.id,
        round_number=round_number if round_number is not None else (session.current_round or 1),
        actor_player_id=actor.id if actor else None,
        event_type=event_type,
        payload=event_payload,
    )
    db.add(log_entry)
    return log_entry
