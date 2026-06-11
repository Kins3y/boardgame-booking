from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.game.models.civilization import Civilization
from app.game.schemas.civilization import CivilizationResponse


router = APIRouter(
    prefix="/game/civilizations",
    tags=["Civilizations"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/", response_model=list[CivilizationResponse])
def get_civilizations(db: Session = Depends(get_db)):
    return (
        db.query(Civilization)
        .filter(Civilization.is_active == True)
        .order_by(Civilization.id.asc())
        .all()
    )


@router.get("/{civilization_id}", response_model=CivilizationResponse)
def get_civilization(
        civilization_id: int,
        db: Session = Depends(get_db)
):
    civilization = db.query(Civilization).filter(
        Civilization.id == civilization_id
    ).first()

    if not civilization:
        raise HTTPException(
            status_code=404,
            detail="Civilization not found"
        )

    return civilization