from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.game.models.game_session import GameSession
from app.game.models.session_building import SessionBuilding
from app.game.models.session_player import SessionPlayer
from app.game.models.session_system import SessionSystem
from app.game.models.star_system import StarSystem
from app.game.schemas.building import BuildBuildingCreate


router = APIRouter(
    prefix="/game/sessions",
    tags=["Game Buildings"]
)


COMMAND_POINTS_PER_ROUND = 3


BUILDING_COSTS = {
    "mine": {
        "matter": 6,
        "energy": 2,
        "data": 0
    },
    "power_plant": {
        "matter": 6,
        "energy": 3,
        "data": 0
    },
    "storage": {
        "matter": 3,
        "energy": 2,
        "data": 0
    }
}


BUILDING_SLOT_FIELD = {
    "mine": "mineral_slots",
    "power_plant": "energy_slots",
    "storage": "storage_slots"
}


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def get_ordered_session_players(
    db: Session,
    session_id: int
) -> list[SessionPlayer]:
    return db.query(SessionPlayer).filter(
        SessionPlayer.session_id == session_id
    ).order_by(SessionPlayer.id.asc()).all()


def reset_players_for_new_round(players: list[SessionPlayer]):
    for player in players:
        player.command_points_left = COMMAND_POINTS_PER_ROUND
        player.has_passed = False


def get_current_player(
    players: list[SessionPlayer],
    current_player_id: int | None
) -> SessionPlayer | None:
    if current_player_id is None:
        return None

    return next(
        (
            player
            for player in players
            if player.id == current_player_id
        ),
        None
    )


def find_next_active_player_index(
    players: list[SessionPlayer],
    current_turn_index: int
) -> int | None:
    if not players:
        return None

    players_count = len(players)

    for offset in range(1, players_count + 1):
        next_index = (current_turn_index + offset) % players_count
        next_player = players[next_index]

        if (
            not next_player.has_passed
            and next_player.command_points_left > 0
        ):
            return next_index

    return None


def start_action_phase(
    session: GameSession,
    players: list[SessionPlayer]
):
    reset_players_for_new_round(players)

    session.round_phase = "action"
    session.current_turn_index = 0

    if players:
        session.current_player_id = players[0].id
    else:
        session.current_player_id = None


def advance_turn_or_start_next_round(
    session: GameSession,
    players: list[SessionPlayer]
):
    next_player_index = find_next_active_player_index(
        players=players,
        current_turn_index=session.current_turn_index
    )

    if next_player_index is not None:
        session.current_turn_index = next_player_index
        session.current_player_id = players[next_player_index].id
        return

    session.current_round += 1
    start_action_phase(session, players)


def require_current_player_for_action(
    session: GameSession,
    players: list[SessionPlayer],
    player_id: int
) -> SessionPlayer:
    current_player = get_current_player(
        players,
        session.current_player_id
    )

    if not current_player:
        raise HTTPException(
            status_code=400,
            detail="No current player is active"
        )

    if current_player.id != player_id:
        raise HTTPException(
            status_code=403,
            detail="Only current player can perform actions"
        )

    if current_player.has_passed:
        raise HTTPException(
            status_code=400,
            detail="Current player has already passed"
        )

    if current_player.command_points_left <= 0:
        raise HTTPException(
            status_code=400,
            detail="Current player has no command points left"
        )

    return current_player


def consume_command_point_and_advance_turn(
    session: GameSession,
    players: list[SessionPlayer],
    acting_player: SessionPlayer
):
    for index, player in enumerate(players):
        if player.id == acting_player.id:
            session.current_turn_index = index
            break

    acting_player.command_points_left -= 1

    if acting_player.command_points_left <= 0:
        acting_player.has_passed = True

    advance_turn_or_start_next_round(session, players)


@router.post("/{session_id}/buildings/build")
def build_building(
    session_id: int,
    build_request: BuildBuildingCreate,
    db: Session = Depends(get_db)
):
    game_session = db.query(GameSession).filter(
        GameSession.id == session_id
    ).first()

    if not game_session:
        raise HTTPException(
            status_code=404,
            detail="Session not found"
        )

    if game_session.status != "started":
        raise HTTPException(
            status_code=400,
            detail="Buildings can be constructed only in started sessions"
        )

    player = db.query(SessionPlayer).filter(
        SessionPlayer.id == build_request.session_player_id,
        SessionPlayer.session_id == session_id
    ).first()

    if not player:
        raise HTTPException(
            status_code=404,
            detail="Player not found in this session"
        )

    players = get_ordered_session_players(db, session_id)
    acting_player = require_current_player_for_action(
        session=game_session,
        players=players,
        player_id=player.id
    )

    session_system = db.query(SessionSystem).filter(
        SessionSystem.session_id == session_id,
        SessionSystem.system_id == build_request.system_id
    ).first()

    if not session_system:
        raise HTTPException(
            status_code=404,
            detail="System not found in this session"
        )

    if session_system.owner_player_id != acting_player.id:
        raise HTTPException(
            status_code=403,
            detail="Player does not control this system"
        )

    star_system = db.query(StarSystem).filter(
        StarSystem.id == build_request.system_id
    ).first()

    if not star_system:
        raise HTTPException(
            status_code=404,
            detail="Star system not found"
        )

    building_type = build_request.building_type

    if building_type not in BUILDING_COSTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown building type: {building_type}"
        )

    cost = BUILDING_COSTS[building_type]

    if acting_player.matter < cost["matter"]:
        raise HTTPException(
            status_code=400,
            detail="Not enough matter"
        )

    if acting_player.energy < cost["energy"]:
        raise HTTPException(
            status_code=400,
            detail="Not enough energy"
        )

    if acting_player.data < cost["data"]:
        raise HTTPException(
            status_code=400,
            detail="Not enough data"
        )

    slot_field_name = BUILDING_SLOT_FIELD[building_type]
    slot_limit = getattr(star_system, slot_field_name)

    existing_buildings_count = db.query(SessionBuilding).filter(
        SessionBuilding.session_id == session_id,
        SessionBuilding.system_id == build_request.system_id,
        SessionBuilding.building_type == building_type
    ).count()

    if existing_buildings_count >= slot_limit:
        raise HTTPException(
            status_code=400,
            detail=f"No free slots for building type: {building_type}"
        )

    acting_player.matter -= cost["matter"]
    acting_player.energy -= cost["energy"]
    acting_player.data -= cost["data"]

    new_building = SessionBuilding(
        session_id=session_id,
        system_id=build_request.system_id,
        owner_player_id=acting_player.id,
        building_type=building_type
    )

    db.add(new_building)

    consume_command_point_and_advance_turn(
        session=game_session,
        players=players,
        acting_player=acting_player
    )

    db.commit()
    db.refresh(new_building)
    db.refresh(acting_player)
    db.refresh(game_session)

    return {
        "message": "Building constructed",
        "building": {
            "id": new_building.id,
            "session_id": new_building.session_id,
            "system_id": new_building.system_id,
            "owner_player_id": new_building.owner_player_id,
            "building_type": new_building.building_type
        },
        "player_resources": {
            "matter": acting_player.matter,
            "energy": acting_player.energy,
            "data": acting_player.data
        },
        "turn_state": {
            "current_round": game_session.current_round,
            "current_player_id": game_session.current_player_id,
            "current_turn_index": game_session.current_turn_index,
            "round_phase": game_session.round_phase
        }
    }