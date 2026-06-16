from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.game.models.civilization import Civilization
from app.game.models.game_map import GameMap
from app.game.models.game_session import GameSession
from app.game.models.session_building import SessionBuilding
from app.game.models.session_player import SessionPlayer
from app.game.models.session_system import SessionSystem
from app.game.models.session_unit import SessionUnit
from app.game.models.session_fleet import SessionFleet
from app.game.models.star_system import StarSystem
from app.game.models.system_connection import SystemConnection
from app.game.schemas.game_session import GameSessionCreate
from app.game.schemas.game_session import GameSessionUpdateName
from app.game.schemas.session_player import SessionPlayerCreate
from app.game.schemas.start_system import StartSystemOptionResponse
from app.game.services.map_validator import validate_map
from app.models.user import User



COMMAND_POINTS_PER_ROUND = 3

DEPLOYED_COLONY_INCOME = {
    "matter": 2,
    "energy": 2,
    "data": 0,
    "food": 0,
}

UNIT_ACTION_ENERGY_COST = 3
COLONY_BUILDING_TYPE = "colony"

FLEETS_PER_PLAYER = 4
UNITS_PER_FLEET = 5

UNIT_FORMATION_WEIGHTS = {
    "scout": 10,
    "marine": 20,
    "frigate": 40,
    "colony": 80,
    "ark": 90,
    "cruiser": 100,
}


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


BUILDING_DISPLAY_NAMES = {
    "mine": "Mine",
    "power_plant": "Power Plant",
    "energy_plant": "Energy Plant",
    "storage": "Supply Depot",
    "research_center": "Research Center",
    "barracks": "Barracks",
    "spaceport": "Spaceport",
    "orbital_defense": "Orbital Defense",
    "colony": "Colony"
}


BUILDING_INCOME = {
    "mine": {
        "matter": 2,
        "energy": 0,
        "data": 0,
        "food": 0
    },
    "power_plant": {
        "matter": 0,
        "energy": 2,
        "data": 0,
        "food": 0
    },
    "energy_plant": {
        "matter": 0,
        "energy": 2,
        "data": 0,
        "food": 0
    },
    "research_center": {
        "matter": 0,
        "energy": 0,
        "data": 1,
        "food": 0
    },
    "storage": {
        "matter": 0,
        "energy": 0,
        "data": 0,
        "food": 1
    },
    "barracks": {
        "matter": 0,
        "energy": 0,
        "data": 0,
        "food": 0
    },
    "spaceport": {
        "matter": 0,
        "energy": 0,
        "data": 0,
        "food": 0
    },
    "orbital_defense": {
        "matter": 0,
        "energy": 0,
        "data": 0,
        "food": 0
    }
}


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


def get_unit_formation_weight(unit_type: str) -> int:
    return UNIT_FORMATION_WEIGHTS.get(unit_type, 50)


def reset_fleets_for_new_round(
    db: Session,
    session_id: int
):
    fleets = db.query(SessionFleet).filter(
        SessionFleet.session_id == session_id
    ).all()

    for fleet in fleets:
        fleet.has_acted_this_round = False
        fleet.is_defensive = False

def count_fleet_units(
    db: Session,
    session_id: int,
    fleet_id: int
) -> int:
    return db.query(SessionUnit).filter(
        SessionUnit.session_id == session_id,
        SessionUnit.fleet_id == fleet_id
    ).count()


def get_next_available_unit_slot(
    db: Session,
    session_id: int,
    fleet_id: int
) -> int:
    units = db.query(SessionUnit).filter(
        SessionUnit.session_id == session_id,
        SessionUnit.fleet_id == fleet_id
    ).all()

    used_slots = {
        unit.slot_index
        for unit in units
        if unit.slot_index is not None
    }

    for slot_index in range(1, UNITS_PER_FLEET + 1):
        if slot_index not in used_slots:
            return slot_index

    raise HTTPException(
        status_code=400,
        detail="Fleet has no available unit slots"
    )


def get_next_fleet_number(
    db: Session,
    session_id: int,
    owner_player_id: int
) -> int:
    active_fleets = db.query(SessionFleet).filter(
        SessionFleet.session_id == session_id,
        SessionFleet.owner_player_id == owner_player_id
    ).all()

    used_numbers = {fleet.fleet_number for fleet in active_fleets}

    for fleet_number in range(1, FLEETS_PER_PLAYER + 1):
        if fleet_number not in used_numbers:
            return fleet_number

    raise HTTPException(
        status_code=400,
        detail="Player has no available fleet slots"
    )


def get_next_built_order(
    db: Session,
    session_id: int,
    owner_player_id: int
) -> int:
    last_unit = db.query(SessionUnit).filter(
        SessionUnit.session_id == session_id,
        SessionUnit.owner_player_id == owner_player_id
    ).order_by(SessionUnit.built_order.desc()).first()

    if not last_unit:
        return 1

    return last_unit.built_order + 1


def find_or_create_fleet_for_new_unit(
    db: Session,
    session_id: int,
    owner_player_id: int,
    system_id: int
) -> SessionFleet:
    fleets_in_system = db.query(SessionFleet).filter(
        SessionFleet.session_id == session_id,
        SessionFleet.owner_player_id == owner_player_id,
        SessionFleet.system_id == system_id
    ).order_by(SessionFleet.fleet_number.asc()).all()

    for fleet in fleets_in_system:
        if count_fleet_units(db, session_id, fleet.id) < UNITS_PER_FLEET:
            return fleet

    active_fleets_count = db.query(SessionFleet).filter(
        SessionFleet.session_id == session_id,
        SessionFleet.owner_player_id == owner_player_id
    ).count()

    if active_fleets_count >= FLEETS_PER_PLAYER:
        raise HTTPException(
            status_code=400,
            detail=(
                "No available fleet capacity in this system. "
                "Move an existing fleet here or free a fleet slot first."
            )
        )

    fleet_number = get_next_fleet_number(
        db=db,
        session_id=session_id,
        owner_player_id=owner_player_id
    )

    fleet = SessionFleet(
        session_id=session_id,
        owner_player_id=owner_player_id,
        system_id=system_id,
        fleet_number=fleet_number,
        name=f"Fleet {fleet_number}"
    )

    db.add(fleet)
    db.flush()

    return fleet


def delete_fleet_if_empty(
    db: Session,
    session_id: int,
    fleet_id: int | None
):
    if fleet_id is None:
        return

    units_count = count_fleet_units(
        db=db,
        session_id=session_id,
        fleet_id=fleet_id
    )

    if units_count > 0:
        return

    fleet = db.query(SessionFleet).filter(
        SessionFleet.id == fleet_id,
        SessionFleet.session_id == session_id
    ).first()

    if fleet:
        db.delete(fleet)


def start_action_phase(
    session: GameSession,
    players: list[SessionPlayer],
    db: Session | None = None
):
    reset_players_for_new_round(players)

    if db is not None:
        reset_fleets_for_new_round(db, session.id)

    session.round_phase = "action"
    session.current_turn_index = 0

    if players:
        session.current_player_id = players[0].id
    else:
        session.current_player_id = None


def advance_turn_or_start_next_round(
    session: GameSession,
    players: list[SessionPlayer],
    db: Session | None = None
):
    next_player_index = find_next_active_player_index(
        players=players,
        current_turn_index=session.current_turn_index
    )

    if next_player_index is not None:
        session.current_turn_index = next_player_index
        session.current_player_id = players[next_player_index].id
        return

    if db is not None:
        build_income_report_and_apply_income(
            session_id=session.id,
            players=players,
            db=db
        )

    session.current_round += 1
    start_action_phase(session, players, db)


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
    acting_player: SessionPlayer,
    db: Session | None = None
):
    for index, player in enumerate(players):
        if player.id == acting_player.id:
            session.current_turn_index = index
            break

    acting_player.command_points_left -= 1

    if acting_player.command_points_left <= 0:
        acting_player.has_passed = True

    advance_turn_or_start_next_round(session, players, db)


def get_building_display_name(building_type: str):
    return BUILDING_DISPLAY_NAMES.get(
        building_type,
        building_type.replace("_", " ").title()
    )


def calculate_buildings_income(buildings: list[SessionBuilding]):
    income = {
        "matter": 0,
        "energy": 0,
        "data": 0,
        "food": 0
    }

    for building in buildings:
        building_income = BUILDING_INCOME.get(
            building.building_type,
            {
                "matter": 0,
                "energy": 0,
                "data": 0,
                "food": 0
            }
        )

        income["matter"] += building_income["matter"]
        income["energy"] += building_income["energy"]
        income["data"] += building_income["data"]
        income["food"] += building_income["food"]

    return income


def calculate_colony_buildings_income(buildings: list[SessionBuilding]):
    income = {
        "matter": 0,
        "energy": 0,
        "data": 0,
        "food": 0
    }

    for building in buildings:
        if building.building_type == COLONY_BUILDING_TYPE:
            income["matter"] += DEPLOYED_COLONY_INCOME["matter"]
            income["energy"] += DEPLOYED_COLONY_INCOME["energy"]
            income["data"] += DEPLOYED_COLONY_INCOME["data"]
            income["food"] += DEPLOYED_COLONY_INCOME["food"]

    return income


def get_owned_system_ids(
    session_id: int,
    owner_player_id: int,
    db: Session
):
    session_systems = db.query(SessionSystem).filter(
        SessionSystem.session_id == session_id,
        SessionSystem.owner_player_id == owner_player_id
    ).all()

    return [session_system.system_id for session_system in session_systems]


def build_income_report_and_apply_income(
    session_id: int,
    players: list[SessionPlayer],
    db: Session
):
    income_report = []

    for player in players:
        owned_system_ids = get_owned_system_ids(session_id, player.id, db)

        if owned_system_ids:
            buildings = db.query(SessionBuilding).filter(
                SessionBuilding.session_id == session_id,
                SessionBuilding.owner_player_id == player.id,
                SessionBuilding.system_id.in_(owned_system_ids)
            ).all()
        else:
            buildings = []

        units = db.query(SessionUnit).filter(
            SessionUnit.session_id == session_id,
            SessionUnit.owner_player_id == player.id
        ).all()

        food_required = 0

        for unit in units:
            food_required += unit.food_upkeep

        is_supplied = player.food >= food_required

        food_spent = min(player.food, food_required)
        player.food -= food_spent

        non_colony_buildings = [
            building
            for building in buildings
            if building.building_type != COLONY_BUILDING_TYPE
        ]

        colony_buildings = [
            building
            for building in buildings
            if building.building_type == COLONY_BUILDING_TYPE
        ]

        buildings_income = calculate_buildings_income(non_colony_buildings)

        if is_supplied:
            colonies_income = calculate_colony_buildings_income(colony_buildings)
        else:
            colonies_income = {
                "matter": 0,
                "energy": 0,
                "data": 0,
                "food": 0
            }

        total_income = {
            "matter": buildings_income["matter"] + colonies_income["matter"],
            "energy": buildings_income["energy"] + colonies_income["energy"],
            "data": buildings_income["data"] + colonies_income["data"],
            "food": buildings_income["food"] + colonies_income["food"]
        }

        player.matter += total_income["matter"]
        player.energy += total_income["energy"]
        player.data += total_income["data"]
        player.food += total_income["food"]

        income_report.append({
            "session_player_id": player.id,
            "faction_name": player.faction_name,
            "is_supplied": is_supplied,
            "food_required": food_required,
            "food_spent": food_spent,
            "buildings_income": buildings_income,
            "colonies_income": colonies_income,
            "total_income": total_income,
            "units_count": len(units),
            "buildings_count": len(buildings),
            "colonies_count": len(colony_buildings)
        })

    return income_report


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
                "start_system_id": player.start_system_id,
                "command_points_left": player.command_points_left,
                "has_passed": player.has_passed
            })

        response.append({
            "id": game_session.id,
            "map_id": game_session.map_id,
            "name": game_session.name,
            "status": game_session.status,
            "current_round": game_session.current_round,
            "play_mode": game_session.play_mode,
            "round_phase": game_session.round_phase,
            "current_player_id": game_session.current_player_id,
            "current_turn_index": game_session.current_turn_index,
            "players_count": len(players_response),
            "players": players_response
        })

    return response


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
        name=session.name,
        play_mode="hotseat",
        round_phase="setup",
        current_turn_index=0
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


@router.patch("/{session_id}/name")
def update_session_name(
    session_id: int,
    data: GameSessionUpdateName,
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
            detail="Only created sessions can be renamed"
        )

    session_name = data.name.strip()

    if len(session_name) < 3:
        raise HTTPException(
            status_code=400,
            detail="Session name must be at least 3 characters long"
        )

    if len(session_name) > 60:
        raise HTTPException(
            status_code=400,
            detail="Session name must be 60 characters or less"
        )

    game_session.name = session_name

    db.commit()
    db.refresh(game_session)

    return game_session


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
            GameSession.status == "started"
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
        food=civilization.starting_food,
        start_system_id=player.start_system_id,
        command_points_left=COMMAND_POINTS_PER_ROUND,
        has_passed=False
    )

    db.add(new_player)
    db.commit()
    db.refresh(new_player)

    return new_player


@router.delete("/{session_id}/players/{session_player_id}")
def remove_player_from_session(
    session_id: int,
    session_player_id: int,
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
            detail="Players can be removed only from created sessions"
        )

    session_player = db.query(SessionPlayer).filter(
        SessionPlayer.id == session_player_id,
        SessionPlayer.session_id == session_id
    ).first()

    if not session_player:
        raise HTTPException(
            status_code=404,
            detail="Session player not found"
        )

    db.delete(session_player)
    db.commit()

    return {
        "message": "Player removed from session",
        "session_id": session_id,
        "session_player_id": session_player_id
    }


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

    players = get_ordered_session_players(db, session_id)

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

        fleets = db.query(SessionFleet).filter(
            SessionFleet.session_id == session_id,
            SessionFleet.owner_player_id == player.id
        ).order_by(SessionFleet.fleet_number.asc()).all()

        fleets_response = []

        for fleet in fleets:
            fleet_system = db.query(StarSystem).filter(
                StarSystem.id == fleet.system_id
            ).first()

            fleet_units = db.query(SessionUnit).filter(
                SessionUnit.session_id == session_id,
                SessionUnit.fleet_id == fleet.id
            ).order_by(
                SessionUnit.formation_weight.asc(),
                SessionUnit.built_order.asc(),
                SessionUnit.id.asc()
            ).all()

            units_response = []

            for unit in fleet_units:
                units_response.append({
                    "id": unit.id,
                    "unit_type": unit.unit_type,
                    "state": unit.state,
                    "system_id": unit.system_id,
                    "fleet_id": unit.fleet_id,
                    "slot_index": unit.slot_index,
                    "owner_player_id": unit.owner_player_id,
                    "attack": unit.attack,
                    "defense": unit.defense,
                    "current_hp": unit.current_hp,
                    "max_hp": unit.max_hp,
                    "food_upkeep": unit.food_upkeep,
                    "is_foundation": unit.is_foundation,
                    "is_combat": unit.is_combat,
                    "formation_weight": unit.formation_weight,
                    "built_order": unit.built_order
                })

            fleets_response.append({
                "id": fleet.id,
                "session_id": fleet.session_id,
                "owner_player_id": fleet.owner_player_id,
                "system_id": fleet.system_id,
                "system_name": fleet_system.name if fleet_system else None,
                "fleet_number": fleet.fleet_number,
                "name": fleet.name,
                "is_defensive": fleet.is_defensive,
                "has_acted_this_round": fleet.has_acted_this_round,
                "units": units_response
            })

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
            "food": player.food,
            "start_system_id": player.start_system_id,
            "start_system_name": start_system.name if start_system else None,
            "command_points_left": player.command_points_left,
            "has_passed": player.has_passed,
            "fleets": fleets_response
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
                "building_name": get_building_display_name(building.building_type),
                "system_id": session_system.system_id,
                "system_name": star_system.name if star_system else None,
                "owner_player_id": building.owner_player_id
            })

        units = db.query(SessionUnit).filter(
            SessionUnit.session_id == session_id,
            SessionUnit.system_id == session_system.system_id
        ).order_by(
            SessionUnit.formation_weight.asc(),
            SessionUnit.built_order.asc(),
            SessionUnit.id.asc()
        ).all()

        units_response = []

        for unit in units:
            units_response.append({
                "id": unit.id,
                "unit_type": unit.unit_type,
                "state": unit.state,
                "system_id": unit.system_id,
                "fleet_id": unit.fleet_id,
                "slot_index": unit.slot_index,
                "owner_player_id": unit.owner_player_id,
                "attack": unit.attack,
                "defense": unit.defense,
                "current_hp": unit.current_hp,
                "max_hp": unit.max_hp,
                "food_upkeep": unit.food_upkeep,
                "is_foundation": unit.is_foundation,
                "is_combat": unit.is_combat,
                "formation_weight": unit.formation_weight,
                "built_order": unit.built_order
            })

        systems_response.append({
            "system_id": session_system.system_id,
            "system_name": star_system.name if star_system else None,
            "x": star_system.x if star_system else 0,
            "y": star_system.y if star_system else 0,
            "owner_player_id": session_system.owner_player_id,
            "owner_faction": owner_faction,
            "buildings": buildings_response,
            "units": units_response
        })

    return {
        "id": game_session.id,
        "map_id": game_session.map_id,
        "name": game_session.name,
        "status": game_session.status,
        "current_round": game_session.current_round,
        "play_mode": game_session.play_mode,
        "round_phase": game_session.round_phase,
        "current_player_id": game_session.current_player_id,
        "current_turn_index": game_session.current_turn_index,
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

    players = get_ordered_session_players(db, session_id)

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

    for player in players:
        starting_colony = SessionBuilding(
            session_id=session_id,
            owner_player_id=player.id,
            system_id=player.start_system_id,
            building_type=COLONY_BUILDING_TYPE
        )

        db.add(starting_colony)

    game_session.status = "started"
    game_session.current_round = 1
    game_session.play_mode = "hotseat"

    start_action_phase(game_session, players, db)

    db.commit()
    db.refresh(game_session)

    return {
        "message": "Game session started",
        "session": get_full_session(session_id, db)
    }


@router.post("/{session_id}/next-round")
def next_round(
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

    if game_session.status != "started":
        raise HTTPException(
            status_code=400,
            detail="Only started sessions can advance to the next round"
        )

    players = get_ordered_session_players(db, session_id)

    if len(players) == 0:
        raise HTTPException(
            status_code=400,
            detail="Session has no players"
        )

    income_report = build_income_report_and_apply_income(
        session_id=session_id,
        players=players,
        db=db
    )

    game_session.current_round += 1
    start_action_phase(game_session, players, db)

    db.commit()

    return {
        "message": "Next round started",
        "session": get_full_session(session_id, db),
        "income_report": income_report
    }


@router.post("/{session_id}/end-turn")
def end_current_turn(
    session_id: int,
    db: Session = Depends(get_db)
):
    game_session = db.query(GameSession).filter(
        GameSession.id == session_id
    ).first()

    if not game_session:
        raise HTTPException(
            status_code=404,
            detail="Game session not found"
        )

    if game_session.status != "started":
        raise HTTPException(
            status_code=400,
            detail="Only started sessions can use turn actions"
        )

    players = get_ordered_session_players(db, session_id)

    if not players:
        raise HTTPException(
            status_code=400,
            detail="Session has no players"
        )

    current_player = get_current_player(
        players,
        game_session.current_player_id
    )

    if not current_player:
        game_session.current_turn_index = 0
        game_session.current_player_id = players[0].id

        db.commit()
        db.refresh(game_session)

        return {
            "message": "Current player was restored",
            "session": get_full_session(session_id, db)
        }

    if current_player.has_passed:
        raise HTTPException(
            status_code=400,
            detail="Current player has already passed"
        )

    if current_player.command_points_left <= 0:
        current_player.has_passed = True
        advance_turn_or_start_next_round(game_session, players, db)

        db.commit()
        db.refresh(game_session)

        return {
            "message": "Current player had no command points left",
            "session": get_full_session(session_id, db)
        }

    current_player.command_points_left -= 1

    if current_player.command_points_left <= 0:
        current_player.has_passed = True

    advance_turn_or_start_next_round(game_session, players, db)

    db.commit()
    db.refresh(game_session)

    return {
        "message": "Turn ended",
        "session": get_full_session(session_id, db)
    }


@router.post("/{session_id}/pass")
def pass_current_player(
    session_id: int,
    db: Session = Depends(get_db)
):
    game_session = db.query(GameSession).filter(
        GameSession.id == session_id
    ).first()

    if not game_session:
        raise HTTPException(
            status_code=404,
            detail="Game session not found"
        )

    if game_session.status != "started":
        raise HTTPException(
            status_code=400,
            detail="Only started sessions can use turn actions"
        )

    players = get_ordered_session_players(db, session_id)

    if not players:
        raise HTTPException(
            status_code=400,
            detail="Session has no players"
        )

    current_player = get_current_player(
        players,
        game_session.current_player_id
    )

    if not current_player:
        game_session.current_turn_index = 0
        game_session.current_player_id = players[0].id
    else:
        current_player.has_passed = True
        advance_turn_or_start_next_round(game_session, players, db)

    db.commit()
    db.refresh(game_session)

    return {
        "message": "Player passed",
        "session": get_full_session(session_id, db)
    }


@router.post("/{session_id}/buildings/{building_id}/pack-into-ark")
def pack_colony_building_into_ark(
    session_id: int,
    building_id: int,
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
            detail="Only started sessions can use colony actions"
        )

    colony = db.query(SessionBuilding).filter(
        SessionBuilding.id == building_id,
        SessionBuilding.session_id == session_id
    ).first()

    if not colony:
        raise HTTPException(
            status_code=404,
            detail="Colony building not found"
        )

    if colony.building_type != COLONY_BUILDING_TYPE:
        raise HTTPException(
            status_code=400,
            detail="Only Colony building can be packed into Ark"
        )

    owner_player = db.query(SessionPlayer).filter(
        SessionPlayer.id == colony.owner_player_id,
        SessionPlayer.session_id == session_id
    ).first()

    if not owner_player:
        raise HTTPException(
            status_code=404,
            detail="Colony owner not found"
        )

    players = get_ordered_session_players(db, session_id)
    acting_player = require_current_player_for_action(
        session=game_session,
        players=players,
        player_id=owner_player.id
    )

    player_colonies_count = db.query(SessionBuilding).filter(
        SessionBuilding.session_id == session_id,
        SessionBuilding.owner_player_id == owner_player.id,
        SessionBuilding.building_type == COLONY_BUILDING_TYPE
    ).count()

    if player_colonies_count <= 1:
        raise HTTPException(
            status_code=400,
            detail="Player cannot pack the last Colony into Ark"
        )

    if acting_player.energy < UNIT_ACTION_ENERGY_COST:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough energy. Pack into Ark costs {UNIT_ACTION_ENERGY_COST} energy"
        )

    fleet = find_or_create_fleet_for_new_unit(
        db=db,
        session_id=session_id,
        owner_player_id=owner_player.id,
        system_id=colony.system_id
    )

    slot_index = get_next_available_unit_slot(
        db=db,
        session_id=session_id,
        fleet_id=fleet.id
    )

    built_order = get_next_built_order(
        db=db,
        session_id=session_id,
        owner_player_id=owner_player.id
    )

    acting_player.energy -= UNIT_ACTION_ENERGY_COST

    ark = SessionUnit(
        session_id=session_id,
        owner_player_id=owner_player.id,
        system_id=colony.system_id,
        fleet_id=fleet.id,
        slot_index=slot_index,
        unit_type="ark",
        state="ark",
        attack=0,
        defense=1,
        current_hp=10,
        max_hp=10,
        food_upkeep=1,
        is_foundation=False,
        formation_weight=get_unit_formation_weight("ark"),
        built_order=built_order,
        is_combat=False
    )

    colony_system_id = colony.system_id

    db.add(ark)
    db.delete(colony)
    db.flush()

    remaining_colony_in_system = db.query(SessionBuilding).filter(
        SessionBuilding.session_id == session_id,
        SessionBuilding.owner_player_id == owner_player.id,
        SessionBuilding.system_id == colony_system_id,
        SessionBuilding.building_type == COLONY_BUILDING_TYPE
    ).first()

    if not remaining_colony_in_system:
        session_system = db.query(SessionSystem).filter(
            SessionSystem.session_id == session_id,
            SessionSystem.system_id == colony_system_id
        ).first()

        if (
            session_system
            and session_system.owner_player_id == owner_player.id
        ):
            session_system.owner_player_id = None

    consume_command_point_and_advance_turn(
        session=game_session,
        players=players,
        acting_player=acting_player,
        db=db
    )

    db.commit()

    return {
        "message": "Colony packed into Ark",
        "action_cost": {
            "energy": UNIT_ACTION_ENERGY_COST
        },
        "session": get_full_session(session_id, db)
    }


@router.post("/{session_id}/units/{unit_id}/pack-into-ark")
def pack_colony_unit_into_ark_legacy(
    session_id: int,
    unit_id: int,
    db: Session = Depends(get_db)
):
    raise HTTPException(
        status_code=400,
        detail=(
            "Deployed Colonies are buildings now. "
            "Use /game/sessions/{session_id}/buildings/{building_id}/pack-into-ark."
        )
    )


@router.post("/{session_id}/units/{unit_id}/colonize")
def colonize_system_with_ark(
    session_id: int,
    unit_id: int,
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
            detail="Only started sessions can use unit actions"
        )

    unit = db.query(SessionUnit).filter(
        SessionUnit.id == unit_id,
        SessionUnit.session_id == session_id
    ).first()

    if not unit:
        raise HTTPException(
            status_code=404,
            detail="Unit not found"
        )

    if unit.unit_type not in ["ark", "colony"]:
        raise HTTPException(
            status_code=400,
            detail="Only Ark can colonize systems"
        )

    if unit.state != "ark":
        raise HTTPException(
            status_code=400,
            detail="Only Ark can colonize systems"
        )

    session_system = db.query(SessionSystem).filter(
        SessionSystem.session_id == session_id,
        SessionSystem.system_id == unit.system_id
    ).first()

    if not session_system:
        raise HTTPException(
            status_code=404,
            detail="Session system not found"
        )

    if (
        session_system.owner_player_id is not None
        and session_system.owner_player_id != unit.owner_player_id
    ):
        raise HTTPException(
            status_code=400,
            detail="System is already colonized by another player"
        )

    existing_colony = db.query(SessionBuilding).filter(
        SessionBuilding.session_id == session_id,
        SessionBuilding.system_id == unit.system_id,
        SessionBuilding.owner_player_id == unit.owner_player_id,
        SessionBuilding.building_type == COLONY_BUILDING_TYPE
    ).first()

    if existing_colony:
        raise HTTPException(
            status_code=400,
            detail="This player already has a Colony in this system"
        )

    owner_player = db.query(SessionPlayer).filter(
        SessionPlayer.id == unit.owner_player_id,
        SessionPlayer.session_id == session_id
    ).first()

    if not owner_player:
        raise HTTPException(
            status_code=404,
            detail="Unit owner not found"
        )

    players = get_ordered_session_players(db, session_id)
    acting_player = require_current_player_for_action(
        session=game_session,
        players=players,
        player_id=owner_player.id
    )

    if acting_player.energy < UNIT_ACTION_ENERGY_COST:
        raise HTTPException(
            status_code=400,
            detail=f"Not enough energy. Colonize System costs {UNIT_ACTION_ENERGY_COST} energy"
        )

    acting_player.energy -= UNIT_ACTION_ENERGY_COST

    colony = SessionBuilding(
        session_id=session_id,
        owner_player_id=unit.owner_player_id,
        system_id=unit.system_id,
        building_type=COLONY_BUILDING_TYPE
    )

    fleet_id = unit.fleet_id

    db.add(colony)
    db.delete(unit)
    db.flush()

    session_system.owner_player_id = owner_player.id

    delete_fleet_if_empty(
        db=db,
        session_id=session_id,
        fleet_id=fleet_id
    )

    consume_command_point_and_advance_turn(
        session=game_session,
        players=players,
        acting_player=acting_player,
        db=db
    )

    db.commit()

    return {
        "message": "System colonized",
        "action_cost": {
            "energy": UNIT_ACTION_ENERGY_COST
        },
        "session": get_full_session(session_id, db)
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
    game_session.round_phase = "finished"
    game_session.current_player_id = None

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
            "current_round": game_session.current_round,
            "play_mode": game_session.play_mode,
            "round_phase": game_session.round_phase,
            "current_player_id": game_session.current_player_id,
            "current_turn_index": game_session.current_turn_index
        },
        "players_count": len(players)
    }


@router.delete("/{session_id}")
def delete_created_session(
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
            detail="Only created sessions can be deleted"
        )

    db.query(SessionUnit).filter(
        SessionUnit.session_id == session_id
    ).delete(synchronize_session=False)

    db.flush()

    db.query(SessionBuilding).filter(
        SessionBuilding.session_id == session_id
    ).delete(synchronize_session=False)

    db.flush()

    db.query(SessionFleet).filter(
        SessionFleet.session_id == session_id
    ).delete(synchronize_session=False)

    db.flush()

    db.query(SessionSystem).filter(
        SessionSystem.session_id == session_id
    ).delete(synchronize_session=False)

    db.flush()

    db.query(SessionPlayer).filter(
        SessionPlayer.session_id == session_id
    ).delete(synchronize_session=False)

    db.flush()

    db.delete(game_session)
    db.commit()

    return {
        "message": "Created session deleted",
        "session_id": session_id
    }


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
            GameSession.status == "started"
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
                occupied_by_player_id=(
                    occupying_player.id if occupying_player else None
                ),
                occupied_by_faction=(
                    occupying_player.faction_name if occupying_player else None
                )
            )
        )

    return response