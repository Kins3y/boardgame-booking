from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.database import SessionLocal

from app.game.models.star_system import StarSystem
from app.game.schemas.star_system import StarSystemCreate


router = APIRouter(
    prefix="/game/systems",
    tags=["Game Systems"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/")
def create_system(
        system: StarSystemCreate,
        db: Session = Depends(get_db)
):

    new_system = StarSystem(
        map_id=system.map_id,
        name=system.name,
        x=system.x,
        y=system.y,
        is_start=system.is_start,
        is_archive=system.is_archive,
        mineral_slots=system.mineral_slots,
        energy_slots=system.energy_slots,
        storage_slots=system.storage_slots
    )

    db.add(new_system)
    db.commit()
    db.refresh(new_system)

    return new_system


@router.get("/")
def get_systems(
        db: Session = Depends(get_db)
):
    return db.query(StarSystem).all()