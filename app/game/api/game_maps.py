from fastapi import APIRouter, Depends

from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.database import SessionLocal

from app.game.models.game_map import GameMap
from app.game.schemas.game_map import GameMapCreate
from app.game.models.star_system import StarSystem
from app.game.models.system_connection import SystemConnection
from app.game.services.map_validator import validate_map


router = APIRouter(
    prefix="/game/maps",
    tags=["Game Maps"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/")
def create_map(
        game_map: GameMapCreate,
        db: Session = Depends(get_db)
):
    new_map = GameMap(
        name=game_map.name
    )

    db.add(new_map)
    db.commit()
    db.refresh(new_map)

    return new_map


@router.get("/")
def get_maps(
        db: Session = Depends(get_db)
):
    return db.query(GameMap).all()

@router.get("/{map_id}/full")
def get_full_map(
        map_id: int,
        db: Session = Depends(get_db)
):
    game_map = db.query(GameMap).filter(
        GameMap.id == map_id
    ).first()

    if not game_map:
        raise HTTPException(
            status_code=404,
            detail="Map not found"
        )

    systems = db.query(StarSystem).filter(
        StarSystem.map_id == map_id
    ).all()

    connections = db.query(SystemConnection).filter(
        SystemConnection.map_id == map_id
    ).all()

    return {
        "id": game_map.id,
        "name": game_map.name,
        "systems": systems,
        "connections": connections
    }

@router.get("/{map_id}/validate")
def validate_game_map(
        map_id: int,
        db: Session = Depends(get_db)
):
    game_map = db.query(GameMap).filter(
        GameMap.id == map_id
    ).first()

    if not game_map:
        raise HTTPException(
            status_code=404,
            detail="Map not found"
        )

    systems = db.query(StarSystem).filter(
        StarSystem.map_id == map_id
    ).all()

    connections = db.query(SystemConnection).filter(
        SystemConnection.map_id == map_id
    ).all()

    return validate_map(systems, connections)