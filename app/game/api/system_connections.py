from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import SessionLocal

from app.game.models.star_system import StarSystem
from app.game.models.system_connection import SystemConnection
from app.game.schemas.system_connection import SystemConnectionCreate


router = APIRouter(
    prefix="/game/connections",
    tags=["Game Connections"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/")
def create_connection(
        connection: SystemConnectionCreate,
        db: Session = Depends(get_db)
):
    from_system = db.query(StarSystem).filter(
        StarSystem.id == connection.from_system_id
    ).first()

    to_system = db.query(StarSystem).filter(
        StarSystem.id == connection.to_system_id
    ).first()

    if not from_system or not to_system:
        raise HTTPException(
            status_code=404,
            detail="One or both systems not found"
        )

    existing_connection = db.query(SystemConnection).filter(
        SystemConnection.map_id == connection.map_id,
        (
                (
                        (SystemConnection.from_system_id == connection.from_system_id) &
                        (SystemConnection.to_system_id == connection.to_system_id)
                )
                |
                (
                        (SystemConnection.from_system_id == connection.to_system_id) &
                        (SystemConnection.to_system_id == connection.from_system_id)
                )
        )
    ).first()

    if existing_connection:
        raise HTTPException(
            status_code=409,
            detail="Connection already exists"
        )

    if connection.from_system_id == connection.to_system_id:
        raise HTTPException(
            status_code=400,
            detail="System cannot be connected to itself"
        )

    new_connection = SystemConnection(
        map_id=connection.map_id,
        from_system_id=connection.from_system_id,
        to_system_id=connection.to_system_id
    )

    db.add(new_connection)
    db.commit()
    db.refresh(new_connection)

    return new_connection


@router.get("/")
def get_connections(
        db: Session = Depends(get_db)
):
    return db.query(SystemConnection).all()