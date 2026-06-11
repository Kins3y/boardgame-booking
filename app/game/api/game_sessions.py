from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import SessionLocal

from app.game.models.game_map import GameMap
from app.game.models.game_session import GameSession
from app.game.models.session_player import SessionPlayer
from app.game.schemas.game_session import GameSessionCreate
from app.game.schemas.session_player import SessionPlayerCreate
from app.game.models.star_system import StarSystem
from app.game.models.system_connection import SystemConnection
from app.game.services.map_validator import validate_map
from app.game.models.session_system import SessionSystem
from app.game.models.session_building import SessionBuilding
from app.game.schemas.start_system import StartSystemOptionResponse
from app.game.models.civilization import Civilization

from app.models.user import User


router = APIRouter(
    prefix="/game/sessions",
    tags=["Game Sessions"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/")
def create_session(
        session: GameSessionCreate,
        db: Session = Depends(get_db)
):
    game_map = db.query(GameMap).filter(
        GameMap.id == session.map_id
    ).first()

    if not game_map:
        raise HTTPException(
            status_code=404,
            detail="Map not found"
        )

    new_session = GameSession(
        map_id=session.map_id,
        name=session.name
    )

    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return new_session


@router.get("/")
def get_sessions(
        db: Session = Depends(get_db)
):
    return db.query(GameSession).all()


@router.post("/{session_id}/players")
def add_player_to_session(
        session_id: int,
        player: SessionPlayerCreate,
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

    if game_session.status != "created":
        raise HTTPException(
            status_code=400,
            detail="Players can be added only to created sessions"
        )

    existing_player = db.query(SessionPlayer).filter(
        SessionPlayer.session_id == session_id,
        SessionPlayer.user_id == player.user_id
    ).first()

    if existing_player:
        raise HTTPException(
            status_code=409,
            detail="User already joined this session"
        )

    active_player_session = (
        db.query(SessionPlayer)
        .join(GameSession, SessionPlayer.session_id == GameSession.id)
        .filter(
            SessionPlayer.user_id == player.user_id,
            GameSession.status.in_(["created", "started"])
        )
        .first()
    )

    if active_player_session:
        raise HTTPException(
            status_code=409,
            detail="User is already in another active game session"
        )

    if player.civilization_id is None:
        raise HTTPException(
            status_code=400,
            detail="Civilization is required"
        )

    civilization = db.query(Civilization).filter(
        Civilization.id == player.civilization_id,
        Civilization.is_active == True
    ).first()

    if not civilization:
        raise HTTPException(
            status_code=404,
            detail="Civilization not found"
        )

    occupied_civilization = db.query(SessionPlayer).filter(
        SessionPlayer.session_id == session_id,
        SessionPlayer.civilization_id == player.civilization_id
    ).first()

    if occupied_civilization:
        raise HTTPException(
            status_code=409,
            detail="Civilization is already selected by another player"
        )

    if player.start_system_id is None:
        raise HTTPException(
            status_code=400,
            detail="Start system is required"
        )

    start_system = db.query(StarSystem).filter(
        StarSystem.id == player.start_system_id
    ).first()

    if not start_system:
        raise HTTPException(
            status_code=404,
            detail="Start system not found"
        )

    if start_system.map_id != game_session.map_id:
        raise HTTPException(
            status_code=400,
            detail="Start system does not belong to this session map"
        )

    if not start_system.is_start:
        raise HTTPException(
            status_code=400,
            detail="Selected system is not marked as a start system"
        )

    occupied_start_system = db.query(SessionPlayer).filter(
        SessionPlayer.session_id == session_id,
        SessionPlayer.start_system_id == player.start_system_id
    ).first()

    if occupied_start_system:
        raise HTTPException(
            status_code=409,
            detail="Start system is already occupied by another player"
        )

    new_player = SessionPlayer(
        session_id=session_id,
        user_id=player.user_id,
        civilization_id=player.civilization_id,
        faction_name=player.faction_name,
        matter=civilization.starting_matter,
        energy=civilization.starting_energy,
        data=civilization.starting_data,
        start_system_id=player.start_system_id
    )

    db.add(new_player)
    db.commit()
    db.refresh(new_player)

    return new_player


@router.get("/{session_id}/full")
def get_full_session(
        session_id: int,
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

    players = db.query(SessionPlayer).filter(
        SessionPlayer.session_id == session_id
    ).all()

    players_response = []

    for player in players:
        user = db.query(User).filter(
            User.id == player.user_id
        ).first()

        civilization = None

        if player.civilization_id is not None:
            civilization = db.query(Civilization).filter(
                Civilization.id == player.civilization_id
            ).first()

        start_system = None

        if player.start_system_id is not None:
            start_system = db.query(StarSystem).filter(
                StarSystem.id == player.start_system_id
            ).first()

        players_response.append({
            "id": player.id,
            "session_id": player.session_id,
            "user_id": player.user_id,
            "nickname": user.nickname if user else None,
            "email": user.email if user else None,
            "civilization_id": player.civilization_id,
            "civilization_name": civilization.name if civilization else None,
            "faction_name": player.faction_name,
            "matter": player.matter,
            "energy": player.energy,
            "data": player.data,
            "start_system_id": player.start_system_id,
            "start_system_name": start_system.name if start_system else None
        })

    session_systems = db.query(SessionSystem).filter(
        SessionSystem.session_id == session_id
    ).all()

    systems_response = []

    for session_system in session_systems:
        star_system = db.query(StarSystem).filter(
            StarSystem.id == session_system.system_id
        ).first()

        owner_faction = None

        if session_system.owner_player_id is not None:
            owner_player = db.query(SessionPlayer).filter(
                SessionPlayer.id == session_system.owner_player_id
            ).first()

            if owner_player:
                owner_faction = owner_player.faction_name

        buildings = db.query(SessionBuilding).filter(
            SessionBuilding.session_id == session_id,
            SessionBuilding.system_id == session_system.system_id
        ).all()

        buildings_response = []

        for building in buildings:
            buildings_response.append({
                "id": building.id,
                "building_type": building.building_type,
                "owner_player_id": building.owner_player_id
            })

        systems_response.append({
            "system_id": session_system.system_id,
            "system_name": star_system.name if star_system else None,
            "owner_player_id": session_system.owner_player_id,
            "owner_faction": owner_faction,
            "buildings": buildings_response
        })

    return {
        "id": game_session.id,
        "map_id": game_session.map_id,
        "name": game_session.name,
        "status": game_session.status,
        "current_round": game_session.current_round,
        "players_count": len(players),
        "players": players_response,
        "systems": systems_response
    }

@router.post("/{session_id}/start")
def start_session(
        session_id: int,
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

    if game_session.status != "created":
        raise HTTPException(
            status_code=400,
            detail="Only created sessions can be started"
        )

    players = db.query(SessionPlayer).filter(
        SessionPlayer.session_id == session_id
    ).all()

    if len(players) < 2:
        raise HTTPException(
            status_code=400,
            detail="Game session must contain at least 2 players"
        )

    for player in players:
        if player.start_system_id is None:
            raise HTTPException(
                status_code=400,
                detail=f"Player {player.id} has no start system"
            )

    systems = db.query(StarSystem).filter(
        StarSystem.map_id == game_session.map_id
    ).all()

    connections = db.query(SystemConnection).filter(
        SystemConnection.map_id == game_session.map_id
    ).all()

    validation_result = validate_map(systems, connections)

    if not validation_result["is_valid"]:
        raise HTTPException(
            status_code=400,
            detail=validation_result
        )

    for system in systems:
        owner_player_id = None

        for player in players:
            if player.start_system_id == system.id:
                owner_player_id = player.id
                break

        session_system = SessionSystem(
            session_id=session_id,
            system_id=system.id,
            owner_player_id=owner_player_id
        )

        db.add(session_system)

    game_session.status = "started"

    db.commit()
    db.refresh(game_session)

    return {
        "message": "Game session started",
        "session": game_session
    }

@router.post("/{session_id}/finish")
def finish_session(
        session_id: int,
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

    if game_session.status == "finished":
        raise HTTPException(
            status_code=400,
            detail="Game session is already finished"
        )

    game_session.status = "finished"

    db.commit()
    db.refresh(game_session)

    players = db.query(SessionPlayer).filter(
        SessionPlayer.session_id == session_id
    ).all()

    return {
        "message": "Game session finished",
        "session": {
            "id": game_session.id,
            "map_id": game_session.map_id,
            "name": game_session.name,
            "status": game_session.status,
            "current_round": game_session.current_round
        },
        "players_count": len(players)
    }

@router.get("/overview")
def get_sessions_overview(
        db: Session = Depends(get_db)
):
    sessions = db.query(GameSession).order_by(GameSession.id.desc()).all()

    response = []

    for game_session in sessions:
        players = db.query(SessionPlayer).filter(
            SessionPlayer.session_id == game_session.id
        ).all()

        players_response = []

        for player in players:
            user = db.query(User).filter(
                User.id == player.user_id
            ).first()

            civilization = None

            if player.civilization_id is not None:
                civilization = db.query(Civilization).filter(
                    Civilization.id == player.civilization_id
                ).first()

            players_response.append({
                "session_player_id": player.id,
                "user_id": player.user_id,
                "nickname": user.nickname if user else None,
                "email": user.email if user else None,
                "civilization_id": player.civilization_id,
                "civilization_name": civilization.name if civilization else None,
                "faction_name": player.faction_name,
                "start_system_id": player.start_system_id
            })

        response.append({
            "id": game_session.id,
            "map_id": game_session.map_id,
            "name": game_session.name,
            "status": game_session.status,
            "current_round": game_session.current_round,
            "players_count": len(players_response),
            "players": players_response
        })

    return response


@router.get("/{session_id}/available-users")
def get_available_users_for_session(
        session_id: int,
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

    active_players = (
        db.query(SessionPlayer)
        .join(GameSession, SessionPlayer.session_id == GameSession.id)
        .filter(
            GameSession.status.in_(["created", "started"])
        )
        .all()
    )

    active_user_ids = {player.user_id for player in active_players}

    users = db.query(User).all()

    available_users = []

    for user in users:
        if user.id not in active_user_ids:
            available_users.append({
                "id": user.id,
                "email": user.email,
                "nickname": user.nickname
            })

    return {
        "session_id": session_id,
        "users": available_users
    }

@router.get(
    "/{session_id}/start-systems",
    response_model=list[StartSystemOptionResponse]
)
def get_session_start_systems(
        session_id: int,
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

    start_systems = db.query(StarSystem).filter(
        StarSystem.map_id == game_session.map_id,
        StarSystem.is_start == True
    ).order_by(StarSystem.id.asc()).all()

    players = db.query(SessionPlayer).filter(
        SessionPlayer.session_id == session_id
    ).all()

    occupied_systems = {}

    for player in players:
        if player.start_system_id is not None:
            occupied_systems[player.start_system_id] = player

    response = []

    for system in start_systems:
        occupying_player = occupied_systems.get(system.id)

        response.append(
            StartSystemOptionResponse(
                id=system.id,
                name=system.name,
                x=system.x,
                y=system.y,
                is_occupied=occupying_player is not None,
                occupied_by_player_id=occupying_player.id if occupying_player else None,
                occupied_by_faction=occupying_player.faction_name if occupying_player else None
            )
        )

    return response