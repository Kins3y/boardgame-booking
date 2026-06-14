from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.game.models.game_map import GameMap
from app.game.models.game_session import GameSession
from app.game.models.star_system import StarSystem
from app.game.models.system_connection import SystemConnection
from app.game.schemas.map_editor import MapEditorSaveRequest


router = APIRouter(
    prefix="/game/maps/editor",
    tags=["Map Editor"]
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def serialize_map(
    game_map: GameMap,
    systems: list[StarSystem],
    connections: list[SystemConnection]
):
    return {
        "id": game_map.id,
        "name": game_map.name,
        "players_count": game_map.players_count,
        "grid_width": game_map.grid_width,
        "grid_height": game_map.grid_height,
        "is_active": game_map.is_active,
        "systems": [
            {
                "id": system.id,
                "client_id": str(system.id),
                "name": system.name,
                "x": system.x,
                "y": system.y,
                "system_type": system.system_type,
                "archive_level": system.archive_level,
                "is_start": system.is_start,
                "is_archive": system.is_archive,
                "mineral_slots": system.mineral_slots,
                "energy_slots": system.energy_slots,
                "storage_slots": system.storage_slots,
                "research_center_slots": system.research_center_slots,
            }
            for system in systems
        ],
        "connections": [
            {
                "id": connection.id,
                "from_system_id": connection.from_system_id,
                "to_system_id": connection.to_system_id,
                "is_dangerous": connection.is_dangerous,
                "is_wraparound": connection.is_wraparound,
            }
            for connection in connections
        ],
    }


def validate_editor_payload(payload: MapEditorSaveRequest):
    systems = payload.systems
    connections = payload.connections

    if len(systems) == 0:
        raise HTTPException(
            status_code=400,
            detail="Map must contain at least one system"
        )

    if len(systems) > 99:
        raise HTTPException(
            status_code=400,
            detail="Map cannot contain more than 99 systems"
        )

    client_ids = set()
    positions = set()
    start_systems_count = 0

    for system in systems:
        if system.client_id in client_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate system client_id: {system.client_id}"
            )

        client_ids.add(system.client_id)

        position = (system.x, system.y)

        if position in positions:
            raise HTTPException(
                status_code=400,
                detail=f"Two systems cannot occupy the same grid position: {position}"
            )

        positions.add(position)

        if system.x >= payload.grid_width or system.y >= payload.grid_height:
            raise HTTPException(
                status_code=400,
                detail=f"System {system.name} is outside the grid"
            )

        if system.system_type == "start":
            start_systems_count += 1

        if system.system_type == "archive":
            if system.archive_level is None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Archive system {system.name} must have archive_level"
                )
        else:
            if system.archive_level is not None:
                raise HTTPException(
                    status_code=400,
                    detail=f"Only archive systems can have archive_level"
                )

    if start_systems_count != payload.players_count:
        raise HTTPException(
            status_code=400,
            detail=(
                "Number of start systems must be equal to players_count. "
                f"Expected {payload.players_count}, got {start_systems_count}"
            )
        )

    connection_pairs = set()

    for connection in connections:
        if connection.from_client_id == connection.to_client_id:
            raise HTTPException(
                status_code=400,
                detail="System cannot be connected to itself"
            )

        if connection.from_client_id not in client_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown from_client_id: {connection.from_client_id}"
            )

        if connection.to_client_id not in client_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown to_client_id: {connection.to_client_id}"
            )

        pair = tuple(
            sorted([
                connection.from_client_id,
                connection.to_client_id
            ])
        )

        if pair in connection_pairs:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate connection: {pair[0]} - {pair[1]}"
            )

        connection_pairs.add(pair)

    if len(systems) > 1:
        validate_map_is_connected(client_ids, connections)


def validate_map_is_connected(
    client_ids: set[str],
    connections: list
):
    graph = {
        client_id: set()
        for client_id in client_ids
    }

    for connection in connections:
        graph[connection.from_client_id].add(connection.to_client_id)
        graph[connection.to_client_id].add(connection.from_client_id)

    first_system_id = next(iter(client_ids))
    visited = set()
    stack = [first_system_id]

    while stack:
        current_id = stack.pop()

        if current_id in visited:
            continue

        visited.add(current_id)

        for neighbor_id in graph[current_id]:
            if neighbor_id not in visited:
                stack.append(neighbor_id)

    if visited != client_ids:
        isolated = sorted(client_ids - visited)

        raise HTTPException(
            status_code=400,
            detail=f"Map is not connected. Isolated systems: {isolated}"
        )


def create_systems_and_connections(
    db: Session,
    map_id: int,
    payload: MapEditorSaveRequest
):
    client_id_to_system_id: dict[str, int] = {}

    for system_data in payload.systems:
        is_start = system_data.system_type == "start"
        is_archive = system_data.system_type == "archive"

        new_system = StarSystem(
            map_id=map_id,
            name=system_data.name.strip(),
            x=system_data.x,
            y=system_data.y,
            is_start=is_start,
            is_archive=is_archive,
            system_type=system_data.system_type,
            archive_level=system_data.archive_level,
            mineral_slots=system_data.mineral_slots,
            energy_slots=system_data.energy_slots,
            storage_slots=system_data.storage_slots,
            research_center_slots=system_data.research_center_slots,
        )

        db.add(new_system)
        db.flush()

        client_id_to_system_id[system_data.client_id] = new_system.id

    for connection_data in payload.connections:
        new_connection = SystemConnection(
            map_id=map_id,
            from_system_id=client_id_to_system_id[
                connection_data.from_client_id
            ],
            to_system_id=client_id_to_system_id[
                connection_data.to_client_id
            ],
            is_dangerous=connection_data.is_dangerous,
            is_wraparound=connection_data.is_wraparound,
        )

        db.add(new_connection)


@router.get("/")
def get_editor_maps(
    db: Session = Depends(get_db)
):
    maps = db.query(GameMap).order_by(GameMap.id.desc()).all()

    return [
        {
            "id": game_map.id,
            "name": game_map.name,
            "players_count": game_map.players_count,
            "grid_width": game_map.grid_width,
            "grid_height": game_map.grid_height,
            "is_active": game_map.is_active,
        }
        for game_map in maps
    ]


@router.post("/")
def create_editor_map(
    payload: MapEditorSaveRequest,
    db: Session = Depends(get_db)
):
    validate_editor_payload(payload)

    new_map = GameMap(
        name=payload.name.strip(),
        players_count=payload.players_count,
        grid_width=payload.grid_width,
        grid_height=payload.grid_height,
        is_active=True,
    )

    db.add(new_map)
    db.flush()

    create_systems_and_connections(
        db=db,
        map_id=new_map.id,
        payload=payload
    )

    db.commit()
    db.refresh(new_map)

    systems = db.query(StarSystem).filter(
        StarSystem.map_id == new_map.id
    ).all()

    connections = db.query(SystemConnection).filter(
        SystemConnection.map_id == new_map.id
    ).all()

    return serialize_map(new_map, systems, connections)


@router.get("/{map_id}")
def get_editor_map(
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

    return serialize_map(game_map, systems, connections)


@router.put("/{map_id}")
def update_editor_map(
    map_id: int,
    payload: MapEditorSaveRequest,
    db: Session = Depends(get_db)
):
    validate_editor_payload(payload)

    game_map = db.query(GameMap).filter(
        GameMap.id == map_id
    ).first()

    if not game_map:
        raise HTTPException(
            status_code=404,
            detail="Map not found"
        )

    existing_session = db.query(GameSession).filter(
        GameSession.map_id == map_id
    ).first()

    if existing_session:
        raise HTTPException(
            status_code=409,
            detail="Map cannot be edited because it is already used by a game session"
        )

    game_map.name = payload.name.strip()
    game_map.players_count = payload.players_count
    game_map.grid_width = payload.grid_width
    game_map.grid_height = payload.grid_height

    db.query(SystemConnection).filter(
        SystemConnection.map_id == map_id
    ).delete(synchronize_session=False)

    db.query(StarSystem).filter(
        StarSystem.map_id == map_id
    ).delete(synchronize_session=False)

    db.flush()

    create_systems_and_connections(
        db=db,
        map_id=map_id,
        payload=payload
    )

    db.commit()
    db.refresh(game_map)

    systems = db.query(StarSystem).filter(
        StarSystem.map_id == map_id
    ).all()

    connections = db.query(SystemConnection).filter(
        SystemConnection.map_id == map_id
    ).all()

    return serialize_map(game_map, systems, connections)