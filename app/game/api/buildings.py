from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import SessionLocal

from app.game.models.game_session import GameSession
from app.game.models.session_player import SessionPlayer
from app.game.models.session_system import SessionSystem
from app.game.models.session_building import SessionBuilding
from app.game.models.star_system import StarSystem

from app.game.schemas.building import BuildBuildingCreate


router = APIRouter(
    prefix="/game/sessions",
    tags=["Game Buildings"]
)


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

BUILDING_DISPLAY_NAMES = {
    "mine": "Mine",
    "power_plant": "Power Plant",
    "energy_plant": "Energy Plant",
    "storage": "Supply Depot",
    "research_center": "Research Center",
    "barracks": "Barracks",
    "spaceport": "Spaceport",
    "orbital_defense": "Orbital Defense"
}


def get_building_display_name(building_type: str):
    return BUILDING_DISPLAY_NAMES.get(
        building_type,
        building_type.replace("_", " ").title()
    )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


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

    session_system = db.query(SessionSystem).filter(
        SessionSystem.session_id == session_id,
        SessionSystem.system_id == build_request.system_id
    ).first()

    if not session_system:
        raise HTTPException(
            status_code=404,
            detail="System not found in this session"
        )

    if session_system.owner_player_id != player.id:
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
    cost = BUILDING_COSTS[building_type]

    if player.matter < cost["matter"]:
        raise HTTPException(
            status_code=400,
            detail="Not enough matter"
        )

    if player.energy < cost["energy"]:
        raise HTTPException(
            status_code=400,
            detail="Not enough energy"
        )

    if player.data < cost["data"]:
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

    player.matter -= cost["matter"]
    player.energy -= cost["energy"]
    player.data -= cost["data"]

    BUILDING_LIMITS_PER_SYSTEM = {
        "mine": 1,
        "power_plant": 1,
        "energy_plant": 1,
        "storage": 2,
        "research_center": 1,
        "barracks": 1,
        "spaceport": 1,
        "orbital_defense": 1
    }

    new_building = SessionBuilding(
        session_id=session_id,
        system_id=build_request.system_id,
        owner_player_id=player.id,
        building_type=building_type
    )

    db.add(new_building)
    db.commit()
    db.refresh(new_building)
    db.refresh(player)

    return {
        "message": "Building constructed",
        "building": {
    "id": new_building.id,
    "session_id": new_building.session_id,
    "system_id": new_building.system_id,
    "system_name": star_system.name,
    "owner_player_id": new_building.owner_player_id,
    "building_type": new_building.building_type,
    "building_name": get_building_display_name(new_building.building_type)
},
        "player_resources": {
            "matter": player.matter,
            "energy": player.energy,
            "data": player.data
        }
    }