import random

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.db.database import SessionLocal
from app.game.models.civilization import Civilization
from app.game.models.game_map import GameMap
from app.game.models.game_session import GameSession
from app.game.models.session_building import SessionBuilding
from app.game.models.session_player import SessionPlayer
from app.game.models.session_system import SessionSystem
from app.game.models.session_unit import SessionUnit
from app.game.models.session_fleet import SessionFleet
from app.game.models.session_game_log import SessionGameLog
from app.game.models.session_player_technology import SessionPlayerTechnology
from app.game.models.session_player_blueprint import SessionPlayerBlueprint
from app.game.models.session_archon_core_claim import SessionArchonCoreClaim
from app.game.models.star_system import StarSystem
from app.game.models.system_connection import SystemConnection
from app.game.schemas.game_session import GameSessionCreate
from app.game.schemas.game_session import GameSessionUpdateName
from app.game.schemas.session_player import SessionPlayerCreate
from app.game.schemas.start_system import StartSystemOptionResponse
from app.game.schemas.technology import TechnologyResearchRequest
from app.game.schemas.archive_research import ArchiveResearchRequest
from app.game.schemas.archon_core import ArchonCoreClaimRequest
from app.game.services.map_validator import validate_map
from app.game.services.game_log_service import create_game_log
from app.models.user import User



COMMAND_POINTS_PER_ROUND = 3
MAX_GAME_ROUNDS = 12

TECHNOLOGY_CATALOG = [
    {
        "key": "marine_reinforced_armor",
        "name": "Reinforced Marine Armor",
        "category": "combat",
        "building_type": "barracks",
        "building_name": "Barracks",
        "cost": {"matter": 4, "energy": 2, "data": 1},
        "effect_summary": "Marine squads gain +1 max HP in future combat calculations.",
        "description": "Standardizes heavier armor plates for boarding and ground squads.",
        "dominance_points": 1,
    },
    {
        "key": "frigate_targeting_protocol",
        "name": "Frigate Targeting Protocol",
        "category": "combat",
        "building_type": "spaceport",
        "building_name": "Spaceport",
        "cost": {"matter": 3, "energy": 3, "data": 2},
        "effect_summary": "Frigates gain +1 attack in future combat calculations.",
        "description": "Calibrates medium-ship targeting arrays for faster first-contact fire.",
        "dominance_points": 1,
    },
    {
        "key": "archive_decoding",
        "name": "Archive Decoding",
        "category": "archive",
        "building_type": "research_center",
        "building_name": "Research Center",
        "cost": {"matter": 2, "energy": 2, "data": 3},
        "effect_summary": "Archive research actions will cost -1 Energy once archive research is implemented.",
        "description": "Builds a translation layer for hostile archive languages and broken Archon diagrams.",
        "dominance_points": 1,
    },
    {
        "key": "supply_chain_stabilizers",
        "name": "Supply Chain Stabilizers",
        "category": "logistics",
        "building_type": "storage",
        "building_name": "Supply Depot",
        "cost": {"matter": 3, "energy": 2, "data": 1},
        "effect_summary": "Future logistics upgrades may reduce retreat and danger-card penalties.",
        "description": "Improves fleet reserve routing and stabilizes supply movement during crisis maneuvers.",
        "dominance_points": 1,
    },
]

TECHNOLOGY_BY_KEY = {
    technology["key"]: technology
    for technology in TECHNOLOGY_CATALOG
}

ARCHIVE_BLUEPRINT_DP = 2
ARCHIVE_RESEARCH_BASE_ENERGY_COST = 3
ARCHIVE_RESEARCH_DECODING_DISCOUNT = 1
ARCHIVE_RESEARCH_DATA_REWARD = 1
ARCHIVE_RESEARCH_REPEAT_DATA_REWARD = 3
ARCHON_BLUEPRINTS_REQUIRED = 5
ARCHON_CORE_CLAIM_COMMAND_POINT_COST = 1
ARCHON_CORE_SESSION_STATUS = "archon_activated"

ARCHON_BLUEPRINT_CATALOG = [
    {
        "level": 1,
        "key": "archon_blueprint_i",
        "name": "Blueprint I",
        "archive_label": "Archive I",
        "dominance_points": ARCHIVE_BLUEPRINT_DP,
    },
    {
        "level": 2,
        "key": "archon_blueprint_ii",
        "name": "Blueprint II",
        "archive_label": "Archive II",
        "dominance_points": ARCHIVE_BLUEPRINT_DP,
    },
    {
        "level": 3,
        "key": "archon_blueprint_iii",
        "name": "Blueprint III",
        "archive_label": "Archive III",
        "dominance_points": ARCHIVE_BLUEPRINT_DP,
    },
    {
        "level": 4,
        "key": "archon_blueprint_iv",
        "name": "Blueprint IV",
        "archive_label": "Archive IV",
        "dominance_points": ARCHIVE_BLUEPRINT_DP,
    },
    {
        "level": 5,
        "key": "archon_blueprint_v",
        "name": "Blueprint V",
        "archive_label": "Archive V",
        "dominance_points": ARCHIVE_BLUEPRINT_DP,
    },
]

ARCHON_BLUEPRINT_BY_LEVEL = {
    blueprint["level"]: blueprint
    for blueprint in ARCHON_BLUEPRINT_CATALOG
}

DEPLOYED_COLONY_INCOME = {
    "matter": 2,
    "energy": 2,
    "data": 0,
    "food": 0,
}

UNIT_ACTION_ENERGY_COST = 3
COLONY_BUILDING_TYPE = "colony"

FLEET_ORDER_MOVE_DEFEND = "move_defend"
FLEET_ORDER_MOVE_MOVE = "move_move"
FLEET_ORDER_MOVE_TRANSFER = "move_transfer"
FLEET_ORDER_TRANSFER_MOVE = "transfer_move"
FLEET_ORDER_SPLIT_MOVE = "split_move"
FLEET_ORDER_DEFEND = "defend"
FLEET_ORDER_MOVE_ATTACK = "move_attack"
FLEET_ORDER_CONTINUE_COMBAT = "continue_combat"
FLEET_ORDER_RETREAT = "retreat"

MAX_COMBAT_ROUNDS = 1

DANGER_CARD_DEFINITIONS = [
    # No gameplay effect: 33 of 60 cards (55%).
    {
        "key": "clear_passage",
        "name": "Clear Passage",
        "description": "The fleet crosses the corridor without incident.",
        "effect_type": "none",
        "amount": 0,
        "copies": 8
    },
    {
        "key": "sensor_interference",
        "name": "Sensor Interference",
        "description": "False contacts fill the sensors, but the fleet continues safely.",
        "effect_type": "none",
        "amount": 0,
        "copies": 5
    },
    {
        "key": "ghost_echoes",
        "name": "Ghost Echoes",
        "description": "Ancient signals follow the fleet through the corridor, causing no direct harm.",
        "effect_type": "none",
        "amount": 0,
        "copies": 5
    },
    {
        "key": "silent_drift",
        "name": "Silent Drift",
        "description": "The corridor falls unnaturally quiet, but the passage remains stable.",
        "effect_type": "none",
        "amount": 0,
        "copies": 5
    },
    {
        "key": "stable_current",
        "name": "Stable Current",
        "description": "A stable spatial current carries the fleet forward without incident.",
        "effect_type": "none",
        "amount": 0,
        "copies": 5
    },
    {
        "key": "distant_distress_signal",
        "name": "Distant Distress Signal",
        "description": "The fleet detects a fading distress signal but suffers no immediate effect.",
        "effect_type": "none",
        "amount": 0,
        "copies": 5
    },

    # Front unit takes 1 damage: 12 of 60 cards (20%).
    {
        "key": "hull_stress",
        "name": "Hull Stress",
        "description": "The front unit suffers 1 damage from unstable space.",
        "effect_type": "damage_front_unit",
        "amount": 1,
        "copies": 4
    },
    {
        "key": "micrometeor_swarm",
        "name": "Micrometeor Swarm",
        "description": "A cloud of fast debris deals 1 damage to the front unit.",
        "effect_type": "damage_front_unit",
        "amount": 1,
        "copies": 3
    },
    {
        "key": "gravitic_shear",
        "name": "Gravitic Shear",
        "description": "A sudden gravitational shift deals 1 damage to the front unit.",
        "effect_type": "damage_front_unit",
        "amount": 1,
        "copies": 3
    },
    {
        "key": "debris_impact",
        "name": "Debris Impact",
        "description": "Uncharted wreckage strikes the formation, dealing 1 damage to the front unit.",
        "effect_type": "damage_front_unit",
        "amount": 1,
        "copies": 2
    },

    # Lose 1 Energy: 6 of 60 cards (10%).
    {
        "key": "energy_leak",
        "name": "Energy Leak",
        "description": "Emergency stabilization consumes 1 Energy.",
        "effect_type": "lose_energy",
        "amount": 1,
        "copies": 3
    },
    {
        "key": "shield_overload",
        "name": "Shield Overload",
        "description": "Protective systems overload and consume 1 Energy.",
        "effect_type": "lose_energy",
        "amount": 1,
        "copies": 2
    },
    {
        "key": "emergency_burn",
        "name": "Emergency Burn",
        "description": "The fleet spends 1 Energy to escape a collapsing current.",
        "effect_type": "lose_energy",
        "amount": 1,
        "copies": 1
    },

    # Lose 1 Food: 6 of 60 cards (10%).
    {
        "key": "supply_loss",
        "name": "Supply Loss",
        "description": "Damaged cargo containers cost the player 1 Food.",
        "effect_type": "lose_food",
        "amount": 1,
        "copies": 3
    },
    {
        "key": "cargo_rupture",
        "name": "Cargo Rupture",
        "description": "A storage compartment ruptures and the player loses 1 Food.",
        "effect_type": "lose_food",
        "amount": 1,
        "copies": 2
    },
    {
        "key": "spoiled_rations",
        "name": "Spoiled Rations",
        "description": "Radiation exposure destroys supplies worth 1 Food.",
        "effect_type": "lose_food",
        "amount": 1,
        "copies": 1
    },

    # Front unit takes 2 damage: 3 of 60 cards (5%).
    {
        "key": "severe_turbulence",
        "name": "Severe Turbulence",
        "description": "Violent spatial turbulence deals 2 damage to the front unit.",
        "effect_type": "damage_front_unit",
        "amount": 2,
        "copies": 1
    },
    {
        "key": "spatial_fracture",
        "name": "Spatial Fracture",
        "description": "A sudden fracture in space deals 2 damage to the front unit.",
        "effect_type": "damage_front_unit",
        "amount": 2,
        "copies": 1
    },
    {
        "key": "mine_remnant",
        "name": "Mine Remnant",
        "description": "An ancient mine remnant detonates, dealing 2 damage to the front unit.",
        "effect_type": "damage_front_unit",
        "amount": 2,
        "copies": 1
    }
]

DANGER_DECK_SIZE = sum(
    card["copies"]
    for card in DANGER_CARD_DEFINITIONS
)


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


UNIT_DEFINITIONS = {
    "scout": {
        "name": "Scout Drone",
        "produced_by": "barracks",
        "matter": 4,
        "energy": 2,
        "data": 0,
        "attack": 1,
        "defense": 0,
        "hp": 2,
        "food_upkeep": 1,
        "is_combat": True,
        "state": "active"
    },
    "marine": {
        "name": "Marine Squad",
        "produced_by": "barracks",
        "matter": 5,
        "energy": 2,
        "data": 0,
        "attack": 1,
        "defense": 1,
        "hp": 3,
        "food_upkeep": 1,
        "is_combat": True,
        "state": "active"
    },
    "ark": {
        "name": "Ark",
        "produced_by": "barracks",
        "matter": 8,
        "energy": 6,
        "data": 1,
        "attack": 0,
        "defense": 1,
        "hp": 10,
        "food_upkeep": 1,
        "is_combat": False,
        "state": "ark"
    },
    "frigate": {
        "name": "Frigate",
        "produced_by": "spaceport",
        "matter": 8,
        "energy": 5,
        "data": 1,
        "attack": 2,
        "defense": 1,
        "hp": 4,
        "food_upkeep": 1,
        "is_combat": True,
        "state": "active"
    },
    "cruiser": {
        "name": "Cruiser",
        "produced_by": "spaceport",
        "matter": 14,
        "energy": 9,
        "data": 2,
        "attack": 4,
        "defense": 2,
        "hp": 8,
        "food_upkeep": 2,
        "is_combat": True,
        "state": "active"
    }
}


router = APIRouter(
    prefix="/game/sessions",
    tags=["Game Sessions"]
)


class FleetCommandOrderCreate(BaseModel):
    fleet_id: int
    order_type: str
    target_system_id: int | None = None
    second_target_system_id: int | None = None
    transfer_fleet_id: int | None = None
    transfer_fleet_target_system_id: int | None = None
    continuing_fleet_id: int | None = None
    target_fleet_id: int | None = None
    split_fleet_target_system_id: int | None = None
    split_unit_ids: list[int] = Field(default_factory=list)
    unit_ids_to_transfer_fleet: list[int] = Field(default_factory=list)
    unit_ids_to_command_fleet: list[int] = Field(default_factory=list)


class FleetCommandCreate(BaseModel):
    orders: list[FleetCommandOrderCreate]


class ProduceUnitCreate(BaseModel):
    unit_type: str


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


def get_researched_technology_keys(
    db: Session,
    session_id: int,
    player_id: int
) -> set[str]:
    researched_technologies = db.query(SessionPlayerTechnology).filter(
        SessionPlayerTechnology.session_id == session_id,
        SessionPlayerTechnology.player_id == player_id
    ).all()

    return {
        str(researched_technology.technology_key)
        for researched_technology in researched_technologies
    }


def serialize_technology(technology: dict) -> dict:
    return {
        "key": technology["key"],
        "name": technology["name"],
        "category": technology["category"],
        "building_type": technology["building_type"],
        "building_name": technology["building_name"],
        "cost": technology["cost"],
        "effect_summary": technology["effect_summary"],
        "description": technology["description"],
        "dominance_points": technology["dominance_points"],
    }


def get_player_technologies_response(
    db: Session,
    session_id: int,
    player_id: int
) -> list[dict]:
    researched_keys = get_researched_technology_keys(
        db=db,
        session_id=session_id,
        player_id=player_id
    )

    return [
        serialize_technology(TECHNOLOGY_BY_KEY[technology_key])
        for technology_key in sorted(researched_keys)
        if technology_key in TECHNOLOGY_BY_KEY
    ]


def serialize_archon_blueprint_catalog_item(blueprint: dict) -> dict:
    return {
        "level": blueprint["level"],
        "key": blueprint["key"],
        "name": blueprint["name"],
        "archive_label": blueprint["archive_label"],
        "dominance_points": blueprint["dominance_points"],
    }


def serialize_player_blueprint(blueprint: SessionPlayerBlueprint) -> dict:
    blueprint_definition = ARCHON_BLUEPRINT_BY_LEVEL.get(
        blueprint.blueprint_level,
        {
            "level": blueprint.blueprint_level,
            "key": blueprint.blueprint_key,
            "name": f"Blueprint {blueprint.blueprint_level}",
            "archive_label": f"Archive {blueprint.blueprint_level}",
            "dominance_points": ARCHIVE_BLUEPRINT_DP,
        }
    )

    return {
        "id": blueprint.id,
        "level": blueprint.blueprint_level,
        "key": blueprint.blueprint_key,
        "name": blueprint_definition["name"],
        "archive_label": blueprint_definition["archive_label"],
        "archive_system_id": blueprint.archive_system_id,
        "discovered_round": blueprint.discovered_round,
        "dominance_points": blueprint_definition["dominance_points"],
    }


def get_player_blueprints(
    db: Session,
    session_id: int,
    player_id: int
) -> list[SessionPlayerBlueprint]:
    return db.query(SessionPlayerBlueprint).filter(
        SessionPlayerBlueprint.session_id == session_id,
        SessionPlayerBlueprint.player_id == player_id
    ).order_by(
        SessionPlayerBlueprint.blueprint_level.asc(),
        SessionPlayerBlueprint.id.asc()
    ).all()


def get_player_blueprint_levels(
    db: Session,
    session_id: int,
    player_id: int
) -> set[int]:
    return {
        int(blueprint.blueprint_level)
        for blueprint in get_player_blueprints(
            db=db,
            session_id=session_id,
            player_id=player_id
        )
    }


def get_player_blueprints_response(
    db: Session,
    session_id: int,
    player_id: int
) -> list[dict]:
    return [
        serialize_player_blueprint(blueprint)
        for blueprint in get_player_blueprints(
            db=db,
            session_id=session_id,
            player_id=player_id
        )
    ]


def player_has_all_archon_blueprints(
    db: Session,
    session_id: int,
    player_id: int
) -> bool:
    return len(get_player_blueprint_levels(
        db=db,
        session_id=session_id,
        player_id=player_id
    )) >= ARCHON_BLUEPRINTS_REQUIRED


def get_archon_core_claim(
    db: Session,
    session_id: int
) -> SessionArchonCoreClaim | None:
    return db.query(SessionArchonCoreClaim).filter(
        SessionArchonCoreClaim.session_id == session_id
    ).first()


def get_heart_of_the_galaxy_systems(
    db: Session,
    session_id: int
) -> list[tuple[SessionSystem, StarSystem]]:
    rows = db.query(SessionSystem, StarSystem).join(
        StarSystem,
        StarSystem.id == SessionSystem.system_id
    ).filter(
        SessionSystem.session_id == session_id,
        StarSystem.system_type == "archive",
        StarSystem.archive_level == 5
    ).all()

    return rows


def get_controlled_heart_system(
    db: Session,
    session_id: int,
    player_id: int,
    requested_system_id: int | None = None
) -> tuple[SessionSystem, StarSystem] | None:
    rows = get_heart_of_the_galaxy_systems(
        db=db,
        session_id=session_id
    )

    for session_system, star_system in rows:
        if requested_system_id is not None and star_system.id != requested_system_id:
            continue

        if session_system.owner_player_id == player_id:
            return session_system, star_system

    return None


def serialize_archon_core_claim(
    db: Session,
    claim: SessionArchonCoreClaim | None
) -> dict | None:
    if not claim:
        return None

    player = db.query(SessionPlayer).filter(
        SessionPlayer.id == claim.player_id
    ).first()

    core_system = db.query(StarSystem).filter(
        StarSystem.id == claim.core_system_id
    ).first() if claim.core_system_id is not None else None

    return {
        "id": claim.id,
        "session_id": claim.session_id,
        "player_id": claim.player_id,
        "player_faction": player.faction_name if player else None,
        "core_system_id": claim.core_system_id,
        "core_system_name": core_system.name if core_system else None,
        "claimed_round": claim.claimed_round,
    }


def get_archon_victory_framework_response(
    db: Session,
    game_session: GameSession
) -> dict:
    core_claim = get_archon_core_claim(
        db=db,
        session_id=game_session.id
    )
    serialized_claim = serialize_archon_core_claim(
        db=db,
        claim=core_claim
    )

    archon_player_id = core_claim.player_id if core_claim else None
    archon_player_faction = serialized_claim.get("player_faction") if serialized_claim else None

    return {
        "max_rounds": MAX_GAME_ROUNDS,
        "fallback_victory": "dominance_points",
        "archon_state": "activated" if core_claim else "inactive",
        "core_state": "claimed" if core_claim else "unclaimed",
        "archon_player_id": archon_player_id,
        "archon_player_faction": archon_player_faction,
        "archon_core_claim": serialized_claim,
        "resistance_player_ids": [
            player.id
            for player in db.query(SessionPlayer).filter(
                SessionPlayer.session_id == game_session.id
            ).order_by(SessionPlayer.id.asc()).all()
            if player.id != archon_player_id
        ] if core_claim else [],
    }


def get_archive_research_energy_cost(
    db: Session,
    session_id: int,
    player_id: int
) -> int:
    researched_keys = get_researched_technology_keys(
        db=db,
        session_id=session_id,
        player_id=player_id
    )

    if "archive_decoding" in researched_keys:
        return max(1, ARCHIVE_RESEARCH_BASE_ENERGY_COST - ARCHIVE_RESEARCH_DECODING_DISCOUNT)

    return ARCHIVE_RESEARCH_BASE_ENERGY_COST


def get_archive_research_shortage_message(
    player: SessionPlayer,
    energy_cost: int
) -> str | None:
    if player.energy >= energy_cost:
        return None

    return f"Not enough resources — ENG: need {energy_cost}, have {player.energy}"


def get_player_dominance_points(
    db: Session,
    session_id: int,
    player_id: int
) -> int:
    researched_keys = get_researched_technology_keys(
        db=db,
        session_id=session_id,
        player_id=player_id
    )

    points = sum(
        int(TECHNOLOGY_BY_KEY[technology_key].get("dominance_points", 0))
        for technology_key in researched_keys
        if technology_key in TECHNOLOGY_BY_KEY
    )

    archive_control_points = 0
    controlled_archive_systems = db.query(SessionSystem).join(
        StarSystem,
        StarSystem.id == SessionSystem.system_id
    ).filter(
        SessionSystem.session_id == session_id,
        SessionSystem.owner_player_id == player_id,
        StarSystem.system_type == "archive"
    ).all()

    for session_system in controlled_archive_systems:
        archive_system = db.query(StarSystem).filter(
            StarSystem.id == session_system.system_id
        ).first()

        archive_level = archive_system.archive_level if archive_system else None
        archive_control_points += 2 if archive_level in (4, 5) else 1

    heart_points = db.query(SessionSystem).join(
        StarSystem,
        StarSystem.id == SessionSystem.system_id
    ).filter(
        SessionSystem.session_id == session_id,
        SessionSystem.owner_player_id == player_id,
        StarSystem.system_type == "archive",
        StarSystem.archive_level == 5
    ).count() * 3

    blueprint_points = len(get_player_blueprint_levels(
        db=db,
        session_id=session_id,
        player_id=player_id
    )) * ARCHIVE_BLUEPRINT_DP

    return points + archive_control_points + heart_points + blueprint_points


def player_has_required_building(
    db: Session,
    session_id: int,
    player_id: int,
    building_type: str
) -> bool:
    return db.query(SessionBuilding).filter(
        SessionBuilding.session_id == session_id,
        SessionBuilding.owner_player_id == player_id,
        SessionBuilding.building_type == building_type
    ).first() is not None


def apply_technology_cost(
    player: SessionPlayer,
    cost: dict
):
    player.matter -= int(cost.get("matter", 0) or 0)
    player.energy -= int(cost.get("energy", 0) or 0)
    player.data -= int(cost.get("data", 0) or 0)
    player.food -= int(cost.get("food", 0) or 0)


def get_technology_shortage_message(
    player: SessionPlayer,
    cost: dict
) -> str | None:
    missing_resources = []

    resource_labels = {
        "matter": "MAT",
        "energy": "ENG",
        "data": "DAT",
        "food": "SUP",
    }

    for resource, label in resource_labels.items():
        required = int(cost.get(resource, 0) or 0)
        available = int(getattr(player, resource))

        if required > available:
            missing_resources.append(
                f"{label}: need {required}, have {available}"
            )

    if not missing_resources:
        return None

    return "Not enough resources — " + ", ".join(missing_resources)


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


def get_unit_definition(unit_type: str):
    unit_definition = UNIT_DEFINITIONS.get(unit_type)

    if unit_definition is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown unit type: {unit_type}"
        )

    return unit_definition


def validate_and_pay_unit_cost(
    player: SessionPlayer,
    unit_definition: dict
):
    if player.matter < unit_definition["matter"]:
        raise HTTPException(
            status_code=400,
            detail="Not enough matter"
        )

    if player.energy < unit_definition["energy"]:
        raise HTTPException(
            status_code=400,
            detail="Not enough energy"
        )

    if player.data < unit_definition["data"]:
        raise HTTPException(
            status_code=400,
            detail="Not enough data"
        )

    player.matter -= unit_definition["matter"]
    player.energy -= unit_definition["energy"]
    player.data -= unit_definition["data"]


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


def get_fleet_units(
    db: Session,
    session_id: int,
    fleet_id: int
) -> list[SessionUnit]:
    return db.query(SessionUnit).filter(
        SessionUnit.session_id == session_id,
        SessionUnit.fleet_id == fleet_id
    ).order_by(
        SessionUnit.formation_weight.asc(),
        SessionUnit.built_order.asc(),
        SessionUnit.id.asc()
    ).all()


def normalize_fleet_unit_slots(
    db: Session,
    session_id: int,
    fleet_id: int
):
    units = get_fleet_units(
        db=db,
        session_id=session_id,
        fleet_id=fleet_id
    )

    for slot_index, unit in enumerate(units, start=1):
        unit.slot_index = slot_index


def get_transfer_unit_summary(unit: SessionUnit) -> dict:
    unit_definition = UNIT_DEFINITIONS.get(unit.unit_type, {})
    is_damaged = (
        unit.current_hp is not None
        and unit.max_hp is not None
        and unit.current_hp < unit.max_hp
    )

    return {
        "id": unit.id,
        "unit_type": unit.unit_type,
        "unit_name": unit_definition.get(
            "name",
            unit.unit_type.replace("_", " ").title()
        ),
        "current_hp": unit.current_hp,
        "max_hp": unit.max_hp,
        "is_damaged": is_damaged
    }


def get_connection_between_systems(
    db: Session,
    map_id: int,
    from_system_id: int,
    to_system_id: int
) -> SystemConnection | None:
    connections = db.query(SystemConnection).filter(
        SystemConnection.map_id == map_id
    ).all()

    for connection in connections:
        is_direct = (
            connection.from_system_id == from_system_id
            and connection.to_system_id == to_system_id
        )
        is_reverse = (
            connection.from_system_id == to_system_id
            and connection.to_system_id == from_system_id
        )

        if is_direct or is_reverse:
            return connection

    return None




def get_hostile_fleets_in_system(
    db: Session,
    session_id: int,
    system_id: int,
    owner_player_id: int
) -> list[SessionFleet]:
    return db.query(SessionFleet).filter(
        SessionFleet.session_id == session_id,
        SessionFleet.system_id == system_id,
        SessionFleet.owner_player_id != owner_player_id
    ).all()


def require_system_free_of_hostile_fleets(
    db: Session,
    session_id: int,
    system_id: int,
    owner_player_id: int,
    movement_label: str
):
    hostile_fleets = get_hostile_fleets_in_system(
        db=db,
        session_id=session_id,
        system_id=system_id,
        owner_player_id=owner_player_id
    )

    if hostile_fleets:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{movement_label} enters a system with an enemy fleet. "
                "Use Move → Attack instead."
            )
        )


def get_corridor_danger_cards(connection: SystemConnection) -> int:
    if getattr(connection, "is_wraparound", False):
        return 2

    if getattr(connection, "is_dangerous", False):
        return 1

    return 0


def get_corridor_type(connection: SystemConnection) -> str:
    if getattr(connection, "is_wraparound", False):
        return "wraparound"

    if getattr(connection, "is_dangerous", False):
        return "dangerous"

    return "safe"


def get_front_fleet_unit(
    db: Session,
    session_id: int,
    fleet_id: int
) -> SessionUnit | None:
    return db.query(SessionUnit).filter(
        SessionUnit.session_id == session_id,
        SessionUnit.fleet_id == fleet_id
    ).order_by(
        SessionUnit.formation_weight.asc(),
        SessionUnit.built_order.asc(),
        SessionUnit.id.asc()
    ).first()


def draw_danger_card() -> dict:
    return random.choices(
        DANGER_CARD_DEFINITIONS,
        weights=[card["copies"] for card in DANGER_CARD_DEFINITIONS],
        k=1
    )[0]


def resolve_danger_card(
    db: Session,
    session_id: int,
    fleet: SessionFleet,
    acting_player: SessionPlayer
) -> dict:
    card = draw_danger_card()
    effect_type = card["effect_type"]
    amount = card["amount"]

    result = {
        "card_key": card["key"],
        "name": card["name"],
        "description": card["description"],
        "effect_type": effect_type,
        "amount": amount,
        "effect_summary": "No gameplay effect.",
        "target_unit_id": None,
        "target_unit_name": None,
        "unit_hp_before": None,
        "unit_hp_after": None,
        "unit_destroyed": False,
        "resource": None,
        "resource_lost": 0
    }

    if effect_type == "none":
        return result

    if effect_type == "damage_front_unit":
        front_unit = get_front_fleet_unit(
            db=db,
            session_id=session_id,
            fleet_id=fleet.id
        )

        if not front_unit:
            result["effect_summary"] = "No unit was available to receive damage."
            return result

        hp_before = (
            front_unit.current_hp
            if front_unit.current_hp is not None
            else front_unit.max_hp
        )

        if hp_before is None:
            result["effect_summary"] = "The front unit has no damageable hull."
            return result

        hp_after = max(0, hp_before - amount)
        unit_destroyed = hp_after <= 0
        unit_name = UNIT_DEFINITIONS.get(
            front_unit.unit_type,
            {"name": front_unit.unit_type.replace("_", " ").title()}
        )["name"]

        result.update({
            "target_unit_id": front_unit.id,
            "target_unit_name": unit_name,
            "unit_hp_before": hp_before,
            "unit_hp_after": hp_after,
            "unit_destroyed": unit_destroyed
        })

        if unit_destroyed:
            db.delete(front_unit)
            db.flush()
            result["effect_summary"] = (
                f"{unit_name} took {amount} damage and was destroyed."
            )
        else:
            front_unit.current_hp = hp_after
            result["effect_summary"] = (
                f"{unit_name} took {amount} damage "
                f"({hp_before} → {hp_after} HP)."
            )

        return result

    if effect_type == "lose_energy":
        lost = min(acting_player.energy, amount)
        acting_player.energy -= lost
        result.update({
            "resource": "energy",
            "resource_lost": lost,
            "effect_summary": f"Player lost {lost} Energy."
        })
        return result

    if effect_type == "lose_food":
        lost = min(acting_player.food, amount)
        acting_player.food -= lost
        result.update({
            "resource": "food",
            "resource_lost": lost,
            "effect_summary": f"Player lost {lost} Food."
        })
        return result

    return result


def resolve_danger_cards(
    db: Session,
    session_id: int,
    fleet: SessionFleet,
    acting_player: SessionPlayer,
    cards_count: int
) -> list[dict]:
    results = []

    for _ in range(cards_count):
        results.append(
            resolve_danger_card(
                db=db,
                session_id=session_id,
                fleet=fleet,
                acting_player=acting_player
            )
        )

        if count_fleet_units(db, session_id, fleet.id) == 0:
            break

    return results


def get_fleet_attack_power(
    db: Session,
    session_id: int,
    fleet_id: int
) -> int:
    return sum(
        max(0, unit.attack)
        for unit in get_fleet_units(db, session_id, fleet_id)
        if unit.is_combat
    )


def get_fleet_defense_power(
    db: Session,
    session_id: int,
    fleet_id: int
) -> int:
    return sum(
        max(0, unit.defense)
        for unit in get_fleet_units(db, session_id, fleet_id)
    )


def select_hostile_interceptor(
    db: Session,
    session_id: int,
    system_id: int,
    moving_owner_player_id: int
) -> SessionFleet | None:
    """Choose the deterministic fleet that reacts to a hostile Move → Move arrival."""
    hostile_fleets = get_hostile_fleets_in_system(
        db=db,
        session_id=session_id,
        system_id=system_id,
        owner_player_id=moving_owner_player_id
    )

    if not hostile_fleets:
        return None

    return sorted(
        hostile_fleets,
        key=lambda candidate: (
            1 if candidate.is_defensive else 0,
            get_fleet_attack_power(db, session_id, candidate.id),
            count_fleet_units(db, session_id, candidate.id),
            -candidate.id
        ),
        reverse=True
    )[0]


def resolve_one_way_interception(
    db: Session,
    session_id: int,
    moving_fleet: SessionFleet,
    interceptor: SessionFleet
) -> dict:
    """Resolve one defender strike without return fire from the moving fleet."""
    attack_power = get_fleet_attack_power(db, session_id, interceptor.id)
    moving_defense = get_fleet_defense_power(db, session_id, moving_fleet.id)
    damage = max(1, attack_power - moving_defense) if attack_power > 0 else 0
    damage_events = apply_damage_to_fleet(
        db=db,
        session_id=session_id,
        fleet_id=moving_fleet.id,
        damage=damage
    )

    return {
        "attack_power": attack_power,
        "target_defense": moving_defense,
        "damage": damage,
        "damage_events": damage_events,
        "moving_fleet_destroyed": (
            count_fleet_units(db, session_id, moving_fleet.id) == 0
        )
    }


def apply_damage_to_fleet(
    db: Session,
    session_id: int,
    fleet_id: int,
    damage: int
) -> list[dict]:
    remaining_damage = max(0, damage)
    events: list[dict] = []

    for unit in get_fleet_units(db, session_id, fleet_id):
        if remaining_damage <= 0:
            break

        hp_before = (
            unit.current_hp
            if unit.current_hp is not None
            else unit.max_hp
        )

        if hp_before is None or hp_before <= 0:
            continue

        applied_damage = min(remaining_damage, hp_before)
        hp_after = max(0, hp_before - applied_damage)
        unit_destroyed = hp_after <= 0
        unit_name = UNIT_DEFINITIONS.get(
            unit.unit_type,
            {"name": unit.unit_type.replace("_", " ").title()}
        )["name"]

        events.append({
            "unit_id": unit.id,
            "unit_type": unit.unit_type,
            "unit_name": unit_name,
            "damage": applied_damage,
            "hp_before": hp_before,
            "hp_after": hp_after,
            "destroyed": unit_destroyed
        })

        remaining_damage -= applied_damage

        if unit_destroyed:
            db.delete(unit)
            db.flush()
        else:
            unit.current_hp = hp_after

    return events


def resolve_single_combat_exchange(
    db: Session,
    session_id: int,
    attacker: SessionFleet,
    defender: SessionFleet
) -> dict:
    """Resolve exactly one simultaneous combat exchange.

    Both sides calculate their attack and defense before any damage is applied.
    Surviving fleets remain engaged in the same system and may continue combat
    or retreat during a later action.
    """
    attacker_units_count = count_fleet_units(db, session_id, attacker.id)
    defender_units_count = count_fleet_units(db, session_id, defender.id)

    if attacker_units_count <= 0 or defender_units_count <= 0:
        exchange = None
    else:
        attacker_attack = get_fleet_attack_power(db, session_id, attacker.id)
        attacker_defense = get_fleet_defense_power(db, session_id, attacker.id)
        defender_attack = get_fleet_attack_power(db, session_id, defender.id)
        defender_defense = get_fleet_defense_power(db, session_id, defender.id)

        damage_to_defender = (
            max(1, attacker_attack - defender_defense)
            if attacker_attack > 0
            else 0
        )
        damage_to_attacker = (
            max(1, defender_attack - attacker_defense)
            if defender_attack > 0
            else 0
        )

        # Damage values are calculated before either side takes losses, so the
        # exchange is simultaneous even if one fleet is destroyed.
        defender_damage_events = apply_damage_to_fleet(
            db=db,
            session_id=session_id,
            fleet_id=defender.id,
            damage=damage_to_defender
        )
        attacker_damage_events = apply_damage_to_fleet(
            db=db,
            session_id=session_id,
            fleet_id=attacker.id,
            damage=damage_to_attacker
        )

        exchange = {
            "round": 1,
            "attacker_attack": attacker_attack,
            "attacker_defense": attacker_defense,
            "defender_attack": defender_attack,
            "defender_defense": defender_defense,
            "damage_to_defender": damage_to_defender,
            "damage_to_attacker": damage_to_attacker,
            "defender_damage_events": defender_damage_events,
            "attacker_damage_events": attacker_damage_events
        }

    attacker_destroyed = count_fleet_units(db, session_id, attacker.id) == 0
    defender_destroyed = count_fleet_units(db, session_id, defender.id) == 0

    if attacker_destroyed and defender_destroyed:
        outcome = "mutual_destruction"
    elif defender_destroyed:
        outcome = "attacker_victory"
    elif attacker_destroyed:
        outcome = "defender_victory"
    else:
        outcome = "engagement_continues"

    return {
        "rounds": [exchange] if exchange is not None else [],
        "exchange": exchange,
        "outcome": outcome,
        "attacker_destroyed": attacker_destroyed,
        "defender_destroyed": defender_destroyed,
        "engagement_continues": not attacker_destroyed and not defender_destroyed
    }


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

    if session.current_round >= MAX_GAME_ROUNDS:
        session.status = "finished"
        session.round_phase = "finished"
        session.current_player_id = None
        session.current_turn_index = 0
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


@router.get("/{session_id}/logs")
def get_session_game_logs(
    session_id: int,
    limit: int = 500,
    db: Session = Depends(get_db)
):
    game_session = db.query(GameSession).filter(
        GameSession.id == session_id
    ).first()

    if not game_session:
        raise HTTPException(status_code=404, detail="Session not found")

    safe_limit = max(1, min(limit, 1000))
    entries = db.query(SessionGameLog).filter(
        SessionGameLog.session_id == session_id
    ).order_by(SessionGameLog.id.asc()).limit(safe_limit).all()

    return {
        "session_id": session_id,
        "session_name": game_session.name,
        "logs": [
            {
                "id": entry.id,
                "session_id": entry.session_id,
                "round_number": entry.round_number,
                "actor_player_id": entry.actor_player_id,
                "event_type": entry.event_type,
                "payload": entry.payload or {},
                "created_at": (
                    entry.created_at.isoformat()
                    if entry.created_at is not None
                    else None
                )
            }
            for entry in entries
        ]
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
    archon_core_claim = get_archon_core_claim(
        db=db,
        session_id=session_id
    )
    archon_player_id = archon_core_claim.player_id if archon_core_claim else None

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
            "dominance_points": get_player_dominance_points(
                db=db,
                session_id=session_id,
                player_id=player.id
            ),
            "technologies": get_player_technologies_response(
                db=db,
                session_id=session_id,
                player_id=player.id
            ),
            "archon_blueprints": get_player_blueprints_response(
                db=db,
                session_id=session_id,
                player_id=player.id
            ),
            "blueprint_count": len(get_player_blueprint_levels(
                db=db,
                session_id=session_id,
                player_id=player.id
            )),
            "blueprints_required": ARCHON_BLUEPRINTS_REQUIRED,
            "is_archon_player": archon_player_id == player.id,
            "is_resistance_player": archon_player_id is not None and archon_player_id != player.id,
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
        "max_rounds": MAX_GAME_ROUNDS,
        "victory_framework": get_archon_victory_framework_response(
            db=db,
            game_session=game_session
        ),
        "technology_catalog": [
            serialize_technology(technology)
            for technology in TECHNOLOGY_CATALOG
        ],
        "archon_blueprint_catalog": [
            serialize_archon_blueprint_catalog_item(blueprint)
            for blueprint in ARCHON_BLUEPRINT_CATALOG
        ],
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

        starting_fleet = SessionFleet(
            session_id=session_id,
            owner_player_id=player.id,
            system_id=player.start_system_id,
            fleet_number=1,
            name="Fleet 1",
            is_defensive=False,
            has_acted_this_round=False
        )
        db.add(starting_fleet)
        db.flush()

        scout_definition = get_unit_definition("scout")
        starting_scout = SessionUnit(
            session_id=session_id,
            owner_player_id=player.id,
            system_id=player.start_system_id,
            fleet_id=starting_fleet.id,
            slot_index=1,
            unit_type="scout",
            state=scout_definition["state"],
            attack=scout_definition["attack"],
            defense=scout_definition["defense"],
            current_hp=scout_definition["hp"],
            max_hp=scout_definition["hp"],
            food_upkeep=scout_definition["food_upkeep"],
            is_foundation=False,
            formation_weight=get_unit_formation_weight("scout"),
            built_order=1,
            is_combat=scout_definition["is_combat"]
        )
        db.add(starting_scout)

    game_session.status = "started"
    game_session.current_round = 1
    game_session.play_mode = "hotseat"

    start_action_phase(game_session, players, db)

    create_game_log(
        db=db,
        session=game_session,
        event_type="game_started",
        payload={
            "players": [
                {
                    "session_player_id": player.id,
                    "faction_name": player.faction_name,
                    "start_system_id": player.start_system_id
                }
                for player in players
            ],
            "starting_units": {"scout": 1},
            "starting_colonies": 1
        }
    )

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

    create_game_log(
        db=db,
        session=game_session,
        event_type="round_started",
        payload={"income_report": income_report}
    )

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

    action_round = game_session.current_round
    current_player.command_points_left -= 1

    if current_player.command_points_left <= 0:
        current_player.has_passed = True

    advance_turn_or_start_next_round(game_session, players, db)

    create_game_log(
        db=db,
        session=game_session,
        event_type="turn_ended",
        actor=current_player,
        payload={
            "command_points_left": current_player.command_points_left,
            "next_player_id": game_session.current_player_id
        },
        round_number=action_round
    )

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
        action_round = game_session.current_round
        current_player.has_passed = True
        advance_turn_or_start_next_round(game_session, players, db)
        create_game_log(
            db=db,
            session=game_session,
            event_type="player_passed",
            actor=current_player,
            payload={"next_player_id": game_session.current_player_id},
            round_number=action_round
        )

    db.commit()
    db.refresh(game_session)

    return {
        "message": "Player passed",
        "session": get_full_session(session_id, db)
    }


@router.post("/{session_id}/buildings/{building_id}/produce-unit")
def produce_unit_from_building(
    session_id: int,
    building_id: int,
    request: ProduceUnitCreate,
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
            detail="Units can be produced only in started sessions"
        )

    building = db.query(SessionBuilding).filter(
        SessionBuilding.id == building_id,
        SessionBuilding.session_id == session_id
    ).first()

    if not building:
        raise HTTPException(
            status_code=404,
            detail="Production building not found"
        )

    unit_definition = get_unit_definition(request.unit_type)

    if building.building_type != unit_definition["produced_by"]:
        raise HTTPException(
            status_code=400,
            detail=(
                f"{unit_definition['name']} must be produced by "
                f"{unit_definition['produced_by']}"
            )
        )

    owner_player = db.query(SessionPlayer).filter(
        SessionPlayer.id == building.owner_player_id,
        SessionPlayer.session_id == session_id
    ).first()

    if not owner_player:
        raise HTTPException(
            status_code=404,
            detail="Building owner not found"
        )

    players = get_ordered_session_players(db, session_id)
    acting_player = require_current_player_for_action(
        session=game_session,
        players=players,
        player_id=owner_player.id
    )

    session_system = db.query(SessionSystem).filter(
        SessionSystem.session_id == session_id,
        SessionSystem.system_id == building.system_id
    ).first()

    if not session_system:
        raise HTTPException(
            status_code=404,
            detail="Session system not found"
        )

    if session_system.owner_player_id != acting_player.id:
        raise HTTPException(
            status_code=403,
            detail="Player does not control this production system"
        )

    validate_and_pay_unit_cost(
        player=acting_player,
        unit_definition=unit_definition
    )

    fleet = find_or_create_fleet_for_new_unit(
        db=db,
        session_id=session_id,
        owner_player_id=acting_player.id,
        system_id=building.system_id
    )

    slot_index = get_next_available_unit_slot(
        db=db,
        session_id=session_id,
        fleet_id=fleet.id
    )

    built_order = get_next_built_order(
        db=db,
        session_id=session_id,
        owner_player_id=acting_player.id
    )

    produced_unit = SessionUnit(
        session_id=session_id,
        owner_player_id=acting_player.id,
        system_id=building.system_id,
        fleet_id=fleet.id,
        slot_index=slot_index,
        unit_type=request.unit_type,
        state=unit_definition["state"],
        attack=unit_definition["attack"],
        defense=unit_definition["defense"],
        current_hp=unit_definition["hp"],
        max_hp=unit_definition["hp"],
        food_upkeep=unit_definition["food_upkeep"],
        is_foundation=False,
        formation_weight=get_unit_formation_weight(request.unit_type),
        built_order=built_order,
        is_combat=unit_definition["is_combat"]
    )

    db.add(produced_unit)
    db.flush()

    action_round = game_session.current_round

    consume_command_point_and_advance_turn(
        session=game_session,
        players=players,
        acting_player=acting_player,
        db=db
    )

    create_game_log(
        db=db,
        session=game_session,
        event_type="unit_produced",
        actor=acting_player,
        payload={
            "unit_id": produced_unit.id,
            "unit_type": produced_unit.unit_type,
            "fleet_id": produced_unit.fleet_id,
            "system_id": produced_unit.system_id,
            "cost": {
                "matter": unit_definition["matter"],
                "energy": unit_definition["energy"],
                "data": unit_definition["data"]
            }
        },
        round_number=action_round
    )

    db.commit()
    db.refresh(produced_unit)

    return {
        "message": "Unit produced",
        "produced_unit": {
            "id": produced_unit.id,
            "unit_type": produced_unit.unit_type,
            "fleet_id": produced_unit.fleet_id,
            "slot_index": produced_unit.slot_index,
            "system_id": produced_unit.system_id
        },
        "unit_cost": {
            "matter": unit_definition["matter"],
            "energy": unit_definition["energy"],
            "data": unit_definition["data"]
        },
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

    action_round = game_session.current_round

    consume_command_point_and_advance_turn(
        session=game_session,
        players=players,
        acting_player=acting_player,
        db=db
    )

    create_game_log(
        db=db,
        session=game_session,
        event_type="colony_packed",
        actor=acting_player,
        payload={
            "system_id": colony_system_id,
            "fleet_id": fleet.id,
            "ark_id": ark.id,
            "energy_cost": UNIT_ACTION_ENERGY_COST
        },
        round_number=action_round
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

    action_round = game_session.current_round

    consume_command_point_and_advance_turn(
        session=game_session,
        players=players,
        acting_player=acting_player,
        db=db
    )

    create_game_log(
        db=db,
        session=game_session,
        event_type="system_colonized",
        actor=acting_player,
        payload={
            "system_id": session_system.system_id,
            "former_fleet_id": fleet_id,
            "energy_cost": UNIT_ACTION_ENERGY_COST
        },
        round_number=action_round
    )

    db.commit()

    return {
        "message": "System colonized",
        "action_cost": {
            "energy": UNIT_ACTION_ENERGY_COST
        },
        "session": get_full_session(session_id, db)
    }


@router.post("/{session_id}/fleet-command")
def issue_fleet_command(
    session_id: int,
    command: FleetCommandCreate,
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
            detail="Only started sessions can use fleet commands"
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
        raise HTTPException(
            status_code=400,
            detail="No current player is active"
        )

    acting_player = require_current_player_for_action(
        session=game_session,
        players=players,
        player_id=current_player.id
    )

    if not command.orders:
        raise HTTPException(
            status_code=400,
            detail="Fleet command must contain at least one order"
        )

    if len(command.orders) > FLEETS_PER_PLAYER:
        raise HTTPException(
            status_code=400,
            detail=f"Fleet command can include at most {FLEETS_PER_PLAYER} fleet orders"
        )

    participating_fleet_ids: set[int] = set()
    attacked_fleet_ids: set[int] = set()
    planned_split_fleets = 0
    resolved_orders = []

    for order in command.orders:
        if order.fleet_id in participating_fleet_ids:
            raise HTTPException(
                status_code=400,
                detail=(
                    "A fleet can participate in only one order or transfer "
                    "during the same Fleet Command"
                )
            )

        if order.order_type not in {
            FLEET_ORDER_MOVE_DEFEND,
            FLEET_ORDER_MOVE_MOVE,
            FLEET_ORDER_MOVE_TRANSFER,
            FLEET_ORDER_TRANSFER_MOVE,
            FLEET_ORDER_SPLIT_MOVE,
            FLEET_ORDER_DEFEND,
            FLEET_ORDER_MOVE_ATTACK,
            FLEET_ORDER_CONTINUE_COMBAT,
            FLEET_ORDER_RETREAT
        }:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported fleet order type: {order.order_type}"
            )

        if (
            order.order_type not in {
                FLEET_ORDER_SPLIT_MOVE,
                FLEET_ORDER_DEFEND,
                FLEET_ORDER_CONTINUE_COMBAT
            }
            and order.target_system_id is None
        ):
            raise HTTPException(
                status_code=400,
                detail="Fleet movement requires target_system_id"
            )

        if (
            order.order_type == FLEET_ORDER_MOVE_MOVE
            and order.second_target_system_id is None
        ):
            raise HTTPException(
                status_code=400,
                detail="Move → Move requires second_target_system_id"
            )

        fleet = db.query(SessionFleet).filter(
            SessionFleet.id == order.fleet_id,
            SessionFleet.session_id == session_id
        ).first()

        if not fleet:
            raise HTTPException(
                status_code=404,
                detail=f"Fleet {order.fleet_id} not found"
            )

        if fleet.owner_player_id != acting_player.id:
            raise HTTPException(
                status_code=403,
                detail="Only current player's fleets can receive orders"
            )

        if fleet.has_acted_this_round:
            raise HTTPException(
                status_code=400,
                detail=f"{fleet.name} has already acted this round"
            )

        source_units = get_fleet_units(
            db=db,
            session_id=session_id,
            fleet_id=fleet.id
        )

        if not source_units:
            raise HTTPException(
                status_code=400,
                detail=f"{fleet.name} has no units and cannot move"
            )

        hostile_fleets_in_source = db.query(SessionFleet).filter(
            SessionFleet.session_id == session_id,
            SessionFleet.system_id == fleet.system_id,
            SessionFleet.owner_player_id != acting_player.id
        ).all()
        hostile_fleets_in_source = [
            hostile_fleet
            for hostile_fleet in hostile_fleets_in_source
            if count_fleet_units(db, session_id, hostile_fleet.id) > 0
        ]
        fleet_is_engaged = len(hostile_fleets_in_source) > 0

        if fleet_is_engaged and order.order_type not in {
            FLEET_ORDER_CONTINUE_COMBAT,
            FLEET_ORDER_RETREAT
        }:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{fleet.name} is engaged with an enemy fleet. "
                    "It must Continue Combat or Retreat."
                )
            )

        if (
            not fleet_is_engaged
            and order.order_type in {
                FLEET_ORDER_CONTINUE_COMBAT,
                FLEET_ORDER_RETREAT
            }
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{fleet.name} is not currently engaged with an enemy fleet"
                )
            )

        if order.order_type == FLEET_ORDER_DEFEND:
            current_system = db.query(StarSystem).filter(
                StarSystem.id == fleet.system_id
            ).first()

            participating_fleet_ids.add(fleet.id)
            resolved_orders.append({
                "fleet": fleet,
                "order_type": order.order_type,
                "steps": [],
                "final_system_id": fleet.system_id,
                "final_system_name": (
                    current_system.name if current_system else None
                ),
                "becomes_defensive": True,
                "total_danger_cards": 0,
                "transfer_fleet": None,
                "transfer_fleet_move_step": None,
                "continuing_fleet": None,
                "target_fleet": None,
                "unit_ids_to_transfer_fleet": [],
                "unit_ids_to_command_fleet": [],
                "split_unit_ids": [],
                "split_source_move_step": None,
                "split_new_fleet_move_step": None,
                "retreat": None
            })
            continue

        if order.order_type == FLEET_ORDER_CONTINUE_COMBAT:
            if order.target_fleet_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="Continue Combat requires target_fleet_id"
                )

            target_fleet = db.query(SessionFleet).filter(
                SessionFleet.id == order.target_fleet_id,
                SessionFleet.session_id == session_id
            ).first()

            if not target_fleet:
                raise HTTPException(
                    status_code=404,
                    detail="Target fleet not found"
                )

            if target_fleet.owner_player_id == acting_player.id:
                raise HTTPException(
                    status_code=400,
                    detail="A player cannot attack a friendly fleet"
                )

            if target_fleet.system_id != fleet.system_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Continue Combat target must share the acting fleet's system"
                    )
                )

            if count_fleet_units(db, session_id, target_fleet.id) == 0:
                raise HTTPException(
                    status_code=400,
                    detail="The selected target fleet has no units"
                )

            if target_fleet.id in attacked_fleet_ids:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "The same defending fleet cannot be attacked twice "
                        "during one Fleet Command"
                    )
                )

            attacked_fleet_ids.add(target_fleet.id)
            current_system = db.query(StarSystem).filter(
                StarSystem.id == fleet.system_id
            ).first()
            participating_fleet_ids.add(fleet.id)
            resolved_orders.append({
                "fleet": fleet,
                "order_type": order.order_type,
                "steps": [],
                "final_system_id": fleet.system_id,
                "final_system_name": current_system.name if current_system else None,
                "becomes_defensive": False,
                "total_danger_cards": 0,
                "transfer_fleet": None,
                "transfer_fleet_move_step": None,
                "continuing_fleet": None,
                "target_fleet": target_fleet,
                "unit_ids_to_transfer_fleet": [],
                "unit_ids_to_command_fleet": [],
                "split_unit_ids": [],
                "split_source_move_step": None,
                "split_new_fleet_move_step": None,
                "retreat": None
            })
            continue

        if order.order_type == FLEET_ORDER_SPLIT_MOVE:
            if len(source_units) < 2:
                raise HTTPException(
                    status_code=400,
                    detail="Split → Move requires a fleet with at least 2 units"
                )

            active_fleet_count = db.query(SessionFleet).filter(
                SessionFleet.session_id == session_id,
                SessionFleet.owner_player_id == acting_player.id
            ).count()

            if active_fleet_count + planned_split_fleets >= FLEETS_PER_PLAYER:
                raise HTTPException(
                    status_code=400,
                    detail="Player has no free fleet slot for Split → Move"
                )

            split_unit_ids = list(dict.fromkeys(order.split_unit_ids))

            if len(split_unit_ids) != len(order.split_unit_ids):
                raise HTTPException(
                    status_code=400,
                    detail="Split unit list cannot contain duplicates"
                )

            if not split_unit_ids:
                raise HTTPException(
                    status_code=400,
                    detail="Select at least one unit for the new fleet"
                )

            if len(split_unit_ids) >= len(source_units):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "At least one unit must remain in the source fleet "
                        "after the split"
                    )
                )

            source_unit_ids = {unit.id for unit in source_units}
            invalid_split_ids = [
                unit_id
                for unit_id in split_unit_ids
                if unit_id not in source_unit_ids
            ]

            if invalid_split_ids:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Split units must belong to the selected source fleet: "
                        f"{invalid_split_ids}"
                    )
                )

            source_system = db.query(StarSystem).filter(
                StarSystem.id == fleet.system_id
            ).first()

            def build_split_movement_step(
                target_system_id: int | None,
                movement_label: str,
                step_number: int
            ) -> dict | None:
                if target_system_id is None:
                    return None

                target_session_system = db.query(SessionSystem).filter(
                    SessionSystem.session_id == session_id,
                    SessionSystem.system_id == target_system_id
                ).first()

                if not target_session_system:
                    raise HTTPException(
                        status_code=404,
                        detail=f"{movement_label} target is not part of this session"
                    )

                require_system_free_of_hostile_fleets(
                    db=db,
                    session_id=session_id,
                    system_id=target_system_id,
                    owner_player_id=acting_player.id,
                    movement_label=movement_label
                )

                connection = get_connection_between_systems(
                    db=db,
                    map_id=game_session.map_id,
                    from_system_id=fleet.system_id,
                    to_system_id=target_system_id
                )

                if not connection:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"{movement_label} must use a directly connected "
                            "corridor from the source system"
                        )
                    )

                target_system = db.query(StarSystem).filter(
                    StarSystem.id == target_system_id
                ).first()

                return {
                    "step": step_number,
                    "from_system_id": fleet.system_id,
                    "from_system_name": (
                        source_system.name if source_system else None
                    ),
                    "to_system_id": target_system_id,
                    "to_system_name": (
                        target_system.name if target_system else None
                    ),
                    "corridor_type": get_corridor_type(connection),
                    "danger_cards": get_corridor_danger_cards(connection)
                }

            source_move_step = build_split_movement_step(
                order.target_system_id,
                "Source fleet movement",
                1
            )
            new_fleet_move_step = build_split_movement_step(
                order.split_fleet_target_system_id,
                "New fleet movement",
                2
            )

            planned_split_fleets += 1
            participating_fleet_ids.add(fleet.id)
            resolved_orders.append({
                "fleet": fleet,
                "order_type": order.order_type,
                "steps": [],
                "final_system_id": fleet.system_id,
                "final_system_name": (
                    source_system.name if source_system else None
                ),
                "becomes_defensive": False,
                "total_danger_cards": sum(
                    step["danger_cards"]
                    for step in [source_move_step, new_fleet_move_step]
                    if step is not None
                ),
                "transfer_fleet": None,
                "transfer_fleet_move_step": None,
                "continuing_fleet": None,
                "target_fleet": None,
                "unit_ids_to_transfer_fleet": [],
                "unit_ids_to_command_fleet": [],
                "split_unit_ids": split_unit_ids,
                "split_source_move_step": source_move_step,
                "split_new_fleet_move_step": new_fleet_move_step,
                "retreat": None
            })
            continue

        first_target_session_system = db.query(SessionSystem).filter(
            SessionSystem.session_id == session_id,
            SessionSystem.system_id == order.target_system_id
        ).first()

        if not first_target_session_system:
            raise HTTPException(
                status_code=404,
                detail="First target system is not part of this session"
            )

        if order.order_type not in {
            FLEET_ORDER_MOVE_ATTACK,
            FLEET_ORDER_MOVE_MOVE
        }:
            require_system_free_of_hostile_fleets(
                db=db,
                session_id=session_id,
                system_id=order.target_system_id,
                owner_player_id=acting_player.id,
                movement_label=f"{fleet.name}: movement"
            )

        first_connection = get_connection_between_systems(
            db=db,
            map_id=game_session.map_id,
            from_system_id=fleet.system_id,
            to_system_id=order.target_system_id
        )

        if not first_connection:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{fleet.name}: first movement must use a directly "
                    "connected corridor"
                )
            )

        source_system = db.query(StarSystem).filter(
            StarSystem.id == fleet.system_id
        ).first()

        first_target_system = db.query(StarSystem).filter(
            StarSystem.id == order.target_system_id
        ).first()

        steps = [
            {
                "step": 1,
                "from_system_id": fleet.system_id,
                "from_system_name": source_system.name if source_system else None,
                "to_system_id": order.target_system_id,
                "to_system_name": (
                    first_target_system.name if first_target_system else None
                ),
                "corridor_type": get_corridor_type(first_connection),
                "danger_cards": get_corridor_danger_cards(first_connection)
            }
        ]

        final_system_id = order.target_system_id
        final_system_name = (
            first_target_system.name if first_target_system else None
        )
        becomes_defensive = order.order_type == FLEET_ORDER_MOVE_DEFEND
        transfer_fleet = None
        transfer_fleet_move_step = None
        continuing_fleet = None
        target_fleet = None
        retreat_report = None
        hostile_entry = None
        unit_ids_to_transfer_fleet: list[int] = []
        unit_ids_to_command_fleet: list[int] = []

        if order.order_type == FLEET_ORDER_RETREAT:
            own_unit_count = len(source_units)
            pursuing_fleet = max(
                hostile_fleets_in_source,
                key=lambda hostile: (
                    count_fleet_units(db, session_id, hostile.id),
                    -hostile.id
                )
            )
            pursuing_unit_count = count_fleet_units(
                db, session_id, pursuing_fleet.id
            )
            pursuit_danger_cards = max(
                0,
                pursuing_unit_count - own_unit_count
            )
            corridor_danger_cards = steps[0]["danger_cards"]
            steps[0]["corridor_danger_cards"] = corridor_danger_cards
            steps[0]["pursuit_danger_cards"] = pursuit_danger_cards
            steps[0]["danger_cards"] = (
                corridor_danger_cards + pursuit_danger_cards
            )
            retreat_report = {
                "pursuing_fleet_id": pursuing_fleet.id,
                "pursuing_fleet_name": pursuing_fleet.name,
                "retreating_unit_count": own_unit_count,
                "pursuing_unit_count": pursuing_unit_count,
                "pursuit_danger_cards": pursuit_danger_cards,
                "corridor_danger_cards": corridor_danger_cards,
                "total_danger_cards": steps[0]["danger_cards"]
            }

        if order.order_type == FLEET_ORDER_MOVE_MOVE:
            # Move → Move may now be intercepted after either movement step.
            # If the first destination contains an enemy fleet, interception is
            # resolved there and the second movement is cancelled.
            first_destination_owner_id = (
                first_target_session_system.owner_player_id
            )
            first_destination_is_hostile_controlled = (
                first_destination_owner_id is not None
                and first_destination_owner_id != acting_player.id
            )
            first_interceptor = select_hostile_interceptor(
                db=db,
                session_id=session_id,
                system_id=order.target_system_id,
                moving_owner_player_id=acting_player.id
            )

            if first_interceptor is not None:
                first_destination_owner = (
                    db.query(SessionPlayer).filter(
                        SessionPlayer.id == first_destination_owner_id,
                        SessionPlayer.session_id == session_id
                    ).first()
                    if first_destination_owner_id is not None
                    else None
                )
                first_interceptor_owner = db.query(SessionPlayer).filter(
                    SessionPlayer.id == first_interceptor.owner_player_id,
                    SessionPlayer.session_id == session_id
                ).first()

                hostile_entry = {
                    "step_number": 1,
                    "movement_ended_early": True,
                    "destination_owner_player_id": (
                        first_destination_owner_id
                    ),
                    "destination_owner_name": (
                        first_destination_owner.faction_name
                        if first_destination_owner
                        else None
                    ),
                    "hostile_controlled": (
                        first_destination_is_hostile_controlled
                    ),
                    "interceptor": first_interceptor,
                    "interceptor_owner_name": (
                        first_interceptor_owner.faction_name
                        if first_interceptor_owner
                        else None
                    )
                }

                # The hostile fleet pins the moving fleet in this system.
                # The unused second movement is lost.
                final_system_id = order.target_system_id
                final_system_name = (
                    first_target_system.name if first_target_system else None
                )
            else:
                second_target_system_id = order.second_target_system_id

                if second_target_system_id is None:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Move → Move requires a second target unless the "
                            "fleet is intercepted after the first movement"
                        )
                    )

                second_target_session_system = db.query(SessionSystem).filter(
                    SessionSystem.session_id == session_id,
                    SessionSystem.system_id == second_target_system_id
                ).first()

                if not second_target_session_system:
                    raise HTTPException(
                        status_code=404,
                        detail="Second target system is not part of this session"
                    )

                second_connection = get_connection_between_systems(
                    db=db,
                    map_id=game_session.map_id,
                    from_system_id=order.target_system_id,
                    to_system_id=second_target_system_id
                )

                if not second_connection:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"{fleet.name}: second movement must use a directly "
                            "connected corridor from the first selected system"
                        )
                    )

                second_target_system = db.query(StarSystem).filter(
                    StarSystem.id == second_target_system_id
                ).first()

                steps.append({
                    "step": 2,
                    "from_system_id": order.target_system_id,
                    "from_system_name": (
                        first_target_system.name if first_target_system else None
                    ),
                    "to_system_id": second_target_system_id,
                    "to_system_name": (
                        second_target_system.name if second_target_system else None
                    ),
                    "corridor_type": get_corridor_type(second_connection),
                    "danger_cards": get_corridor_danger_cards(second_connection)
                })

                final_system_id = second_target_system_id
                final_system_name = (
                    second_target_system.name if second_target_system else None
                )

                destination_owner_id = (
                    second_target_session_system.owner_player_id
                )
                destination_is_hostile_controlled = (
                    destination_owner_id is not None
                    and destination_owner_id != acting_player.id
                )
                interceptor = select_hostile_interceptor(
                    db=db,
                    session_id=session_id,
                    system_id=second_target_system_id,
                    moving_owner_player_id=acting_player.id
                )

                if destination_is_hostile_controlled or interceptor is not None:
                    destination_owner = (
                        db.query(SessionPlayer).filter(
                            SessionPlayer.id == destination_owner_id,
                            SessionPlayer.session_id == session_id
                        ).first()
                        if destination_owner_id is not None
                        else None
                    )
                    interceptor_owner = (
                        db.query(SessionPlayer).filter(
                            SessionPlayer.id == interceptor.owner_player_id,
                            SessionPlayer.session_id == session_id
                        ).first()
                        if interceptor is not None
                        else None
                    )
                    hostile_entry = {
                        "step_number": 2,
                        "movement_ended_early": False,
                        "destination_owner_player_id": destination_owner_id,
                        "destination_owner_name": (
                            destination_owner.faction_name
                            if destination_owner
                            else None
                        ),
                        "hostile_controlled": destination_is_hostile_controlled,
                        "interceptor": interceptor,
                        "interceptor_owner_name": (
                            interceptor_owner.faction_name
                            if interceptor_owner
                            else None
                        )
                    }


        if order.order_type == FLEET_ORDER_MOVE_ATTACK:
            if order.target_fleet_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="Move → Attack requires target_fleet_id"
                )

            if order.target_fleet_id in attacked_fleet_ids:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "The same defending fleet cannot be attacked twice "
                        "during one Fleet Command"
                    )
                )

            target_fleet = db.query(SessionFleet).filter(
                SessionFleet.id == order.target_fleet_id,
                SessionFleet.session_id == session_id
            ).first()

            if not target_fleet:
                raise HTTPException(
                    status_code=404,
                    detail="Target fleet not found"
                )

            if target_fleet.owner_player_id == acting_player.id:
                raise HTTPException(
                    status_code=400,
                    detail="A player cannot attack a friendly fleet"
                )

            if target_fleet.system_id != order.target_system_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "The selected target fleet is not located in the "
                        "attack destination system"
                    )
                )

            if count_fleet_units(db, session_id, target_fleet.id) == 0:
                raise HTTPException(
                    status_code=400,
                    detail="The selected target fleet has no units"
                )

            attacked_fleet_ids.add(target_fleet.id)

        if order.order_type == FLEET_ORDER_MOVE_TRANSFER:
            if order.transfer_fleet_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="Move → Transfer requires transfer_fleet_id"
                )

            if order.transfer_fleet_id == fleet.id:
                raise HTTPException(
                    status_code=400,
                    detail="A fleet cannot transfer units with itself"
                )

            if order.transfer_fleet_id in participating_fleet_ids:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "The selected transfer fleet already participates in "
                        "another order in this Fleet Command"
                    )
                )

            unit_ids_to_transfer_fleet = list(
                dict.fromkeys(order.unit_ids_to_transfer_fleet)
            )
            unit_ids_to_command_fleet = list(
                dict.fromkeys(order.unit_ids_to_command_fleet)
            )

            if (
                not unit_ids_to_transfer_fleet
                and not unit_ids_to_command_fleet
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Move → Transfer must move at least one unit"
                )

            if (
                len(unit_ids_to_transfer_fleet)
                != len(order.unit_ids_to_transfer_fleet)
                or len(unit_ids_to_command_fleet)
                != len(order.unit_ids_to_command_fleet)
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Transfer unit lists cannot contain duplicates"
                )

            transfer_fleet = db.query(SessionFleet).filter(
                SessionFleet.id == order.transfer_fleet_id,
                SessionFleet.session_id == session_id
            ).first()

            if not transfer_fleet:
                raise HTTPException(
                    status_code=404,
                    detail="Transfer fleet not found"
                )

            if transfer_fleet.owner_player_id != acting_player.id:
                raise HTTPException(
                    status_code=403,
                    detail="Units can be transferred only between friendly fleets"
                )

            if transfer_fleet.system_id != order.target_system_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "The transfer fleet must be in the system selected for "
                        "the first movement"
                    )
                )

            if transfer_fleet.has_acted_this_round:
                raise HTTPException(
                    status_code=400,
                    detail=f"{transfer_fleet.name} has already acted this round"
                )

            transfer_units = get_fleet_units(
                db=db,
                session_id=session_id,
                fleet_id=transfer_fleet.id
            )

            source_units_by_id = {unit.id: unit for unit in source_units}
            transfer_units_by_id = {unit.id: unit for unit in transfer_units}

            invalid_source_ids = [
                unit_id
                for unit_id in unit_ids_to_transfer_fleet
                if unit_id not in source_units_by_id
            ]
            invalid_transfer_ids = [
                unit_id
                for unit_id in unit_ids_to_command_fleet
                if unit_id not in transfer_units_by_id
            ]

            if invalid_source_ids:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Units {invalid_source_ids} do not belong to "
                        f"{fleet.name}"
                    )
                )

            if invalid_transfer_ids:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Units {invalid_transfer_ids} do not belong to "
                        f"{transfer_fleet.name}"
                    )
                )

            source_projected_count = (
                len(source_units)
                - len(unit_ids_to_transfer_fleet)
                + len(unit_ids_to_command_fleet)
            )
            transfer_projected_count = (
                len(transfer_units)
                - len(unit_ids_to_command_fleet)
                + len(unit_ids_to_transfer_fleet)
            )

            if source_projected_count > UNITS_PER_FLEET:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{fleet.name} would exceed the {UNITS_PER_FLEET}-unit limit"
                    )
                )

            if transfer_projected_count > UNITS_PER_FLEET:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{transfer_fleet.name} would exceed the "
                        f"{UNITS_PER_FLEET}-unit limit"
                    )
                )

            # A fleet that receives/transfers units has used only one of its
            # two fleet-order actions. It may spend its remaining action on
            # one explicit movement during the same Fleet Command.
            if order.transfer_fleet_target_system_id is not None:
                if transfer_projected_count <= 0:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"{transfer_fleet.name} cannot move after transfer "
                            "because it would contain no units"
                        )
                    )

                transfer_move_target_session_system = db.query(
                    SessionSystem
                ).filter(
                    SessionSystem.session_id == session_id,
                    SessionSystem.system_id == (
                        order.transfer_fleet_target_system_id
                    )
                ).first()

                if not transfer_move_target_session_system:
                    raise HTTPException(
                        status_code=404,
                        detail=(
                            "The receiving fleet movement target is not part "
                            "of this session"
                        )
                    )

                require_system_free_of_hostile_fleets(
                    db=db,
                    session_id=session_id,
                    system_id=order.transfer_fleet_target_system_id,
                    owner_player_id=acting_player.id,
                    movement_label=(
                        f"{transfer_fleet.name}: remaining movement"
                    )
                )

                transfer_move_connection = get_connection_between_systems(
                    db=db,
                    map_id=game_session.map_id,
                    from_system_id=order.target_system_id,
                    to_system_id=order.transfer_fleet_target_system_id
                )

                if not transfer_move_connection:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"{transfer_fleet.name}: its remaining movement "
                            "must use a directly connected corridor"
                        )
                    )

                transfer_move_target_system = db.query(StarSystem).filter(
                    StarSystem.id == order.transfer_fleet_target_system_id
                ).first()

                transfer_fleet_move_step = {
                    "step": 2,
                    "from_system_id": order.target_system_id,
                    "from_system_name": (
                        first_target_system.name
                        if first_target_system
                        else None
                    ),
                    "to_system_id": order.transfer_fleet_target_system_id,
                    "to_system_name": (
                        transfer_move_target_system.name
                        if transfer_move_target_system
                        else None
                    ),
                    "corridor_type": get_corridor_type(
                        transfer_move_connection
                    ),
                    "danger_cards": get_corridor_danger_cards(
                        transfer_move_connection
                    )
                }

            participating_fleet_ids.add(transfer_fleet.id)

        if order.order_type == FLEET_ORDER_TRANSFER_MOVE:
            if order.transfer_fleet_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="Transfer → Move requires transfer_fleet_id"
                )

            if order.continuing_fleet_id is None:
                raise HTTPException(
                    status_code=400,
                    detail="Transfer → Move requires continuing_fleet_id"
                )

            if order.transfer_fleet_id == fleet.id:
                raise HTTPException(
                    status_code=400,
                    detail="A fleet cannot transfer units with itself"
                )

            if order.transfer_fleet_id in participating_fleet_ids:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "The selected transfer fleet already participates in "
                        "another order in this Fleet Command"
                    )
                )

            unit_ids_to_transfer_fleet = list(
                dict.fromkeys(order.unit_ids_to_transfer_fleet)
            )
            unit_ids_to_command_fleet = list(
                dict.fromkeys(order.unit_ids_to_command_fleet)
            )

            if (
                not unit_ids_to_transfer_fleet
                and not unit_ids_to_command_fleet
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Transfer → Move must move at least one unit"
                )

            if (
                len(unit_ids_to_transfer_fleet)
                != len(order.unit_ids_to_transfer_fleet)
                or len(unit_ids_to_command_fleet)
                != len(order.unit_ids_to_command_fleet)
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Transfer unit lists cannot contain duplicates"
                )

            transfer_fleet = db.query(SessionFleet).filter(
                SessionFleet.id == order.transfer_fleet_id,
                SessionFleet.session_id == session_id
            ).first()

            if not transfer_fleet:
                raise HTTPException(
                    status_code=404,
                    detail="Transfer fleet not found"
                )

            if transfer_fleet.owner_player_id != acting_player.id:
                raise HTTPException(
                    status_code=403,
                    detail="Units can be transferred only between friendly fleets"
                )

            if transfer_fleet.system_id != fleet.system_id:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Transfer → Move requires both fleets to start in "
                        "the same system"
                    )
                )

            if transfer_fleet.has_acted_this_round:
                raise HTTPException(
                    status_code=400,
                    detail=f"{transfer_fleet.name} has already acted this round"
                )

            if order.continuing_fleet_id not in {fleet.id, transfer_fleet.id}:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "The continuing fleet must be one of the two fleets "
                        "participating in the transfer"
                    )
                )

            transfer_units = get_fleet_units(
                db=db,
                session_id=session_id,
                fleet_id=transfer_fleet.id
            )

            if not transfer_units:
                raise HTTPException(
                    status_code=400,
                    detail=f"{transfer_fleet.name} has no units to transfer"
                )

            source_units_by_id = {unit.id: unit for unit in source_units}
            transfer_units_by_id = {unit.id: unit for unit in transfer_units}

            invalid_source_ids = [
                unit_id
                for unit_id in unit_ids_to_transfer_fleet
                if unit_id not in source_units_by_id
            ]
            invalid_transfer_ids = [
                unit_id
                for unit_id in unit_ids_to_command_fleet
                if unit_id not in transfer_units_by_id
            ]

            if invalid_source_ids:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Units {invalid_source_ids} do not belong to "
                        f"{fleet.name}"
                    )
                )

            if invalid_transfer_ids:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Units {invalid_transfer_ids} do not belong to "
                        f"{transfer_fleet.name}"
                    )
                )

            source_projected_count = (
                len(source_units)
                - len(unit_ids_to_transfer_fleet)
                + len(unit_ids_to_command_fleet)
            )
            transfer_projected_count = (
                len(transfer_units)
                - len(unit_ids_to_command_fleet)
                + len(unit_ids_to_transfer_fleet)
            )

            if source_projected_count > UNITS_PER_FLEET:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{fleet.name} would exceed the "
                        f"{UNITS_PER_FLEET}-unit limit"
                    )
                )

            if transfer_projected_count > UNITS_PER_FLEET:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{transfer_fleet.name} would exceed the "
                        f"{UNITS_PER_FLEET}-unit limit"
                    )
                )

            continuing_projected_count = (
                source_projected_count
                if order.continuing_fleet_id == fleet.id
                else transfer_projected_count
            )

            if continuing_projected_count <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="The continuing fleet must contain at least one unit"
                )

            continuing_fleet = (
                fleet
                if order.continuing_fleet_id == fleet.id
                else transfer_fleet
            )

            participating_fleet_ids.add(transfer_fleet.id)

        participating_fleet_ids.add(fleet.id)

        resolved_orders.append({
            "fleet": fleet,
            "order_type": order.order_type,
            "steps": steps,
            "final_system_id": final_system_id,
            "final_system_name": final_system_name,
            "becomes_defensive": becomes_defensive,
            "total_danger_cards": sum(
                step["danger_cards"]
                for step in steps
            ),
            "transfer_fleet": transfer_fleet,
            "transfer_fleet_move_step": transfer_fleet_move_step,
            "continuing_fleet": continuing_fleet,
            "target_fleet": target_fleet,
            "unit_ids_to_transfer_fleet": unit_ids_to_transfer_fleet,
            "unit_ids_to_command_fleet": unit_ids_to_command_fleet,
            "retreat": retreat_report,
            "hostile_entry": hostile_entry
        })

    command_report = []

    for resolved_order in resolved_orders:
        fleet = resolved_order["fleet"]


        if resolved_order["order_type"] == FLEET_ORDER_DEFEND:
            fleet.is_defensive = True
            fleet.has_acted_this_round = True

            command_report.append({
                "fleet_id": fleet.id,
                "fleet_name": fleet.name,
                "order_type": resolved_order["order_type"],
                "steps": [],
                "final_system_id": fleet.system_id,
                "final_system_name": resolved_order["final_system_name"],
                "total_danger_cards": 0,
                "is_defensive": True,
                "fleet_destroyed": False,
                "order_completed": True,
                "transfer": None,
                "split": None,
                "retreat": None,
                "combat": None
            })
            continue

        if resolved_order["order_type"] == FLEET_ORDER_CONTINUE_COMBAT:
            target_fleet = resolved_order["target_fleet"]
            combat_result = resolve_single_combat_exchange(
                db=db,
                session_id=session_id,
                attacker=fleet,
                defender=target_fleet
            )
            attacker_destroyed = combat_result["attacker_destroyed"]
            defender_destroyed = combat_result["defender_destroyed"]

            if defender_destroyed:
                delete_fleet_if_empty(db, session_id, target_fleet.id)
            if attacker_destroyed:
                delete_fleet_if_empty(db, session_id, fleet.id)
            else:
                fleet.has_acted_this_round = True
                fleet.is_defensive = False

            hostile_fleets_remaining = 0
            if not attacker_destroyed:
                hostile_fleets_remaining = db.query(SessionFleet).filter(
                    SessionFleet.session_id == session_id,
                    SessionFleet.system_id == fleet.system_id,
                    SessionFleet.owner_player_id != acting_player.id
                ).count()

            combat_report = {
                "defender_fleet_id": target_fleet.id,
                "defender_fleet_name": target_fleet.name,
                "defender_owner_player_id": target_fleet.owner_player_id,
                "defender_was_defensive": False,
                "defensive_position_consumed": False,
                "ambush_cards": [],
                "rounds": combat_result["rounds"],
                "exchange": combat_result["exchange"],
                "outcome": combat_result["outcome"],
                "attacker_destroyed": attacker_destroyed,
                "defender_destroyed": defender_destroyed,
                "engagement_continues": combat_result["engagement_continues"],
                "attacker_retreat": False,
                "retreat_reason": None,
                "attacker_retreat_system_id": None,
                "attacker_retreat_system_name": None,
                "hostile_fleets_remaining": hostile_fleets_remaining
            }

            command_report.append({
                "fleet_id": fleet.id,
                "fleet_name": fleet.name,
                "order_type": resolved_order["order_type"],
                "steps": [],
                "final_system_id": resolved_order["final_system_id"],
                "final_system_name": resolved_order["final_system_name"],
                "total_danger_cards": 0,
                "is_defensive": False,
                "fleet_destroyed": attacker_destroyed,
                "order_completed": True,
                "transfer": None,
                "split": None,
                "retreat": None,
                "combat": combat_report
            })
            continue

        if resolved_order["order_type"] == FLEET_ORDER_SPLIT_MOVE:
            source_fleet_id = fleet.id
            source_fleet_name = fleet.name
            original_system_id = fleet.system_id
            original_system = db.query(StarSystem).filter(
                StarSystem.id == original_system_id
            ).first()

            source_units_by_id = {
                unit.id: unit
                for unit in get_fleet_units(
                    db=db,
                    session_id=session_id,
                    fleet_id=source_fleet_id
                )
            }
            moved_units = [
                source_units_by_id[unit_id]
                for unit_id in resolved_order["split_unit_ids"]
            ]

            new_fleet_number = get_next_fleet_number(
                db=db,
                session_id=session_id,
                owner_player_id=acting_player.id
            )
            new_fleet = SessionFleet(
                session_id=session_id,
                owner_player_id=acting_player.id,
                system_id=original_system_id,
                fleet_number=new_fleet_number,
                name=f"Fleet {new_fleet_number}",
                is_defensive=False,
                has_acted_this_round=False
            )
            db.add(new_fleet)
            db.flush()

            for unit in moved_units:
                unit.fleet_id = new_fleet.id
                unit.system_id = original_system_id

            fleet.is_defensive = False
            db.flush()
            normalize_fleet_unit_slots(db, session_id, source_fleet_id)
            normalize_fleet_unit_slots(db, session_id, new_fleet.id)
            db.flush()

            def resolve_split_movement(
                moving_fleet: SessionFleet,
                planned_step: dict | None
            ) -> tuple[dict | None, bool, int, str | None]:
                if planned_step is None:
                    current_system = db.query(StarSystem).filter(
                        StarSystem.id == moving_fleet.system_id
                    ).first()
                    return (
                        None,
                        False,
                        moving_fleet.system_id,
                        current_system.name if current_system else None
                    )

                target_system_id = planned_step["to_system_id"]
                moving_fleet.system_id = target_system_id
                db.query(SessionUnit).filter(
                    SessionUnit.session_id == session_id,
                    SessionUnit.fleet_id == moving_fleet.id
                ).update(
                    {SessionUnit.system_id: target_system_id},
                    synchronize_session=False
                )

                drawn_cards = resolve_danger_cards(
                    db=db,
                    session_id=session_id,
                    fleet=moving_fleet,
                    acting_player=acting_player,
                    cards_count=planned_step["danger_cards"]
                )
                movement_report = {
                    **planned_step,
                    "drawn_cards": drawn_cards
                }
                destroyed = (
                    count_fleet_units(
                        db,
                        session_id,
                        moving_fleet.id
                    ) == 0
                )
                return (
                    movement_report,
                    destroyed,
                    target_system_id,
                    planned_step["to_system_name"]
                )

            source_movement_report, source_destroyed, source_final_system_id, source_final_system_name = resolve_split_movement(
                fleet,
                resolved_order["split_source_move_step"]
            )
            new_movement_report, new_fleet_destroyed, new_final_system_id, new_final_system_name = resolve_split_movement(
                new_fleet,
                resolved_order["split_new_fleet_move_step"]
            )

            if not source_destroyed:
                fleet.has_acted_this_round = True
            if not new_fleet_destroyed:
                new_fleet.has_acted_this_round = True

            if source_destroyed:
                delete_fleet_if_empty(db, session_id, source_fleet_id)
            if new_fleet_destroyed:
                delete_fleet_if_empty(db, session_id, new_fleet.id)

            db.flush()

            movement_steps = [
                step
                for step in [source_movement_report, new_movement_report]
                if step is not None
            ]
            split_report = {
                "new_fleet_id": new_fleet.id,
                "new_fleet_number": new_fleet_number,
                "new_fleet_name": new_fleet.name,
                "moved_to_new_fleet": [
                    get_transfer_unit_summary(unit)
                    for unit in moved_units
                ],
                "source_movement_used": source_movement_report is not None,
                "source_movement_step": source_movement_report,
                "source_final_system_id": source_final_system_id,
                "source_final_system_name": source_final_system_name,
                "source_fleet_destroyed": source_destroyed,
                "new_fleet_movement_used": new_movement_report is not None,
                "new_fleet_movement_step": new_movement_report,
                "new_fleet_final_system_id": new_final_system_id,
                "new_fleet_final_system_name": new_final_system_name,
                "new_fleet_destroyed": new_fleet_destroyed,
                "completed": not source_destroyed and not new_fleet_destroyed
            }

            command_report.append({
                "fleet_id": source_fleet_id,
                "fleet_name": source_fleet_name,
                "order_type": resolved_order["order_type"],
                "steps": movement_steps,
                "final_system_id": source_final_system_id,
                "final_system_name": source_final_system_name,
                "total_danger_cards": sum(
                    len(step["drawn_cards"])
                    for step in movement_steps
                ),
                "is_defensive": False,
                "fleet_destroyed": source_destroyed,
                "order_completed": split_report["completed"],
                "transfer": None,
                "split": split_report,
                "retreat": None,
                "combat": None
            })
            continue


        if resolved_order["order_type"] == FLEET_ORDER_MOVE_ATTACK:
            target_fleet = resolved_order["target_fleet"]
            planned_step = resolved_order["steps"][0]
            target_system_id = planned_step["to_system_id"]

            fleet.system_id = target_system_id
            fleet.is_defensive = False
            db.query(SessionUnit).filter(
                SessionUnit.session_id == session_id,
                SessionUnit.fleet_id == fleet.id
            ).update(
                {SessionUnit.system_id: target_system_id},
                synchronize_session=False
            )

            movement_cards = resolve_danger_cards(
                db=db,
                session_id=session_id,
                fleet=fleet,
                acting_player=acting_player,
                cards_count=planned_step["danger_cards"]
            )
            movement_report = {
                **planned_step,
                "drawn_cards": movement_cards
            }

            attacker_destroyed_in_transit = (
                count_fleet_units(db, session_id, fleet.id) == 0
            )
            defender_was_defensive = bool(target_fleet.is_defensive)
            ambush_cards: list[dict] = []
            combat_rounds: list[dict] = []
            combat_exchange = None
            outcome = "attacker_destroyed_in_transit"
            defender_destroyed = False
            attacker_destroyed = attacker_destroyed_in_transit
            engagement_continues = False
            hostile_fleets_remaining = 0

            if attacker_destroyed_in_transit:
                delete_fleet_if_empty(db, session_id, fleet.id)
            else:
                if defender_was_defensive:
                    ambush_cards = resolve_danger_cards(
                        db=db,
                        session_id=session_id,
                        fleet=fleet,
                        acting_player=acting_player,
                        cards_count=1
                    )
                    target_fleet.is_defensive = False

                attacker_destroyed = (
                    count_fleet_units(db, session_id, fleet.id) == 0
                )

                if attacker_destroyed:
                    outcome = "attacker_destroyed_by_ambush"
                    delete_fleet_if_empty(db, session_id, fleet.id)
                else:
                    combat_result = resolve_single_combat_exchange(
                        db=db,
                        session_id=session_id,
                        attacker=fleet,
                        defender=target_fleet
                    )
                    combat_rounds = combat_result["rounds"]
                    combat_exchange = combat_result["exchange"]
                    outcome = combat_result["outcome"]
                    attacker_destroyed = combat_result["attacker_destroyed"]
                    defender_destroyed = combat_result["defender_destroyed"]
                    engagement_continues = combat_result[
                        "engagement_continues"
                    ]

                    if (
                        defender_was_defensive
                        and engagement_continues
                        and not defender_destroyed
                    ):
                        target_fleet.has_acted_this_round = False

                    if defender_destroyed:
                        delete_fleet_if_empty(db, session_id, target_fleet.id)
                    if attacker_destroyed:
                        delete_fleet_if_empty(db, session_id, fleet.id)
                    else:
                        fleet.has_acted_this_round = True
                        hostile_fleets_remaining = db.query(SessionFleet).filter(
                            SessionFleet.session_id == session_id,
                            SessionFleet.system_id == target_system_id,
                            SessionFleet.owner_player_id != acting_player.id
                        ).count()

            combat_report = {
                "defender_fleet_id": target_fleet.id,
                "defender_fleet_name": target_fleet.name,
                "defender_owner_player_id": target_fleet.owner_player_id,
                "defender_was_defensive": defender_was_defensive,
                "defensive_position_consumed": defender_was_defensive,
                "ambush_cards": ambush_cards,
                "rounds": combat_rounds,
                "exchange": combat_exchange,
                "outcome": outcome,
                "attacker_destroyed": attacker_destroyed,
                "defender_destroyed": defender_destroyed,
                "engagement_continues": engagement_continues,
                "defender_response_ready": (
                    defender_was_defensive
                    and engagement_continues
                    and not defender_destroyed
                ),
                "attacker_retreat": False,
                "retreat_reason": None,
                "attacker_retreat_system_id": None,
                "attacker_retreat_system_name": None,
                "hostile_fleets_remaining": hostile_fleets_remaining
            }

            command_report.append({
                "fleet_id": fleet.id,
                "fleet_name": fleet.name,
                "order_type": resolved_order["order_type"],
                "steps": [movement_report],
                "final_system_id": target_system_id,
                "final_system_name": planned_step["to_system_name"],
                "total_danger_cards": (
                    len(movement_cards) + len(ambush_cards)
                ),
                "is_defensive": False,
                "fleet_destroyed": attacker_destroyed,
                "order_completed": True,
                "transfer": None,
                "split": None,
                "retreat": None,
                "combat": combat_report
            })
            continue

        if resolved_order["order_type"] == FLEET_ORDER_TRANSFER_MOVE:
            transfer_fleet = resolved_order["transfer_fleet"]
            continuing_fleet = resolved_order["continuing_fleet"]
            planned_step = resolved_order["steps"][0]
            source_fleet_id = fleet.id
            source_fleet_name = fleet.name
            partner_fleet_id = transfer_fleet.id
            partner_fleet_name = transfer_fleet.name

            source_units = {
                unit.id: unit
                for unit in get_fleet_units(
                    db=db,
                    session_id=session_id,
                    fleet_id=source_fleet_id
                )
            }
            partner_units = {
                unit.id: unit
                for unit in get_fleet_units(
                    db=db,
                    session_id=session_id,
                    fleet_id=partner_fleet_id
                )
            }

            moved_to_partner = [
                source_units[unit_id]
                for unit_id in resolved_order[
                    "unit_ids_to_transfer_fleet"
                ]
            ]
            moved_to_command = [
                partner_units[unit_id]
                for unit_id in resolved_order[
                    "unit_ids_to_command_fleet"
                ]
            ]

            for unit in moved_to_partner:
                unit.fleet_id = partner_fleet_id

            for unit in moved_to_command:
                unit.fleet_id = source_fleet_id

            fleet.is_defensive = False
            transfer_fleet.is_defensive = False
            db.flush()

            normalize_fleet_unit_slots(db, session_id, source_fleet_id)
            normalize_fleet_unit_slots(db, session_id, partner_fleet_id)
            db.flush()

            source_empty_after_transfer = (
                count_fleet_units(db, session_id, source_fleet_id) == 0
            )
            partner_empty_after_transfer = (
                count_fleet_units(db, session_id, partner_fleet_id) == 0
            )

            continuing_fleet_id = continuing_fleet.id
            continuing_fleet_name = continuing_fleet.name
            movement_target_system_id = planned_step["to_system_id"]

            continuing_fleet.system_id = movement_target_system_id
            db.query(SessionUnit).filter(
                SessionUnit.session_id == session_id,
                SessionUnit.fleet_id == continuing_fleet_id
            ).update(
                {SessionUnit.system_id: movement_target_system_id},
                synchronize_session=False
            )

            drawn_cards = resolve_danger_cards(
                db=db,
                session_id=session_id,
                fleet=continuing_fleet,
                acting_player=acting_player,
                cards_count=planned_step["danger_cards"]
            )

            movement_step_report = {
                **planned_step,
                "drawn_cards": drawn_cards
            }

            continuing_destroyed = (
                count_fleet_units(
                    db, session_id, continuing_fleet_id
                ) == 0
            )

            source_deleted = source_empty_after_transfer
            partner_deleted = partner_empty_after_transfer

            if continuing_destroyed:
                if continuing_fleet_id == source_fleet_id:
                    source_deleted = True
                else:
                    partner_deleted = True

            if not source_deleted:
                fleet.has_acted_this_round = True

            if not partner_deleted:
                transfer_fleet.has_acted_this_round = True

            transfer_report = {
                "partner_fleet_id": partner_fleet_id,
                "partner_fleet_name": partner_fleet_name,
                "moved_to_partner": [
                    get_transfer_unit_summary(unit)
                    for unit in moved_to_partner
                ],
                "moved_to_command_fleet": [
                    get_transfer_unit_summary(unit)
                    for unit in moved_to_command
                ],
                "missing_unit_ids": [],
                "source_fleet_deleted": source_deleted,
                "partner_fleet_deleted": partner_deleted,
                "partner_movement_available": (
                    continuing_fleet_id == partner_fleet_id
                ),
                "partner_movement_used": (
                    continuing_fleet_id == partner_fleet_id
                ),
                "partner_movement_step": (
                    movement_step_report
                    if continuing_fleet_id == partner_fleet_id
                    else None
                ),
                "partner_final_system_id": (
                    movement_target_system_id
                    if continuing_fleet_id == partner_fleet_id
                    else transfer_fleet.system_id
                ),
                "partner_final_system_name": (
                    planned_step["to_system_name"]
                    if continuing_fleet_id == partner_fleet_id
                    else (
                        db.query(StarSystem).filter(
                            StarSystem.id == transfer_fleet.system_id
                        ).first().name
                        if db.query(StarSystem).filter(
                            StarSystem.id == transfer_fleet.system_id
                        ).first()
                        else None
                    )
                ),
                "partner_fleet_destroyed": (
                    continuing_destroyed
                    and continuing_fleet_id == partner_fleet_id
                ),
                "continuing_fleet_id": continuing_fleet_id,
                "continuing_fleet_name": continuing_fleet_name,
                "continuing_movement_used": True,
                "continuing_movement_step": movement_step_report,
                "continuing_final_system_id": movement_target_system_id,
                "continuing_final_system_name": planned_step[
                    "to_system_name"
                ],
                "continuing_fleet_destroyed": continuing_destroyed,
                "completed": not continuing_destroyed
            }

            if source_deleted:
                delete_fleet_if_empty(db, session_id, source_fleet_id)

            if partner_deleted:
                delete_fleet_if_empty(db, session_id, partner_fleet_id)

            db.flush()

            command_report.append({
                "fleet_id": source_fleet_id,
                "fleet_name": source_fleet_name,
                "order_type": resolved_order["order_type"],
                "steps": [movement_step_report],
                "final_system_id": movement_target_system_id,
                "final_system_name": planned_step["to_system_name"],
                "total_danger_cards": len(drawn_cards),
                "is_defensive": False,
                "fleet_destroyed": continuing_destroyed,
                "order_completed": not continuing_destroyed,
                "transfer": transfer_report,
                "split": None,
                "retreat": None,
                "combat": None
            })
            continue
        fleet_id = fleet.id
        fleet_name = fleet.name
        completed_steps = []
        fleet_destroyed = False
        transfer_report = None

        for planned_step in resolved_order["steps"]:
            target_system_id = planned_step["to_system_id"]

            fleet.system_id = target_system_id

            db.query(SessionUnit).filter(
                SessionUnit.session_id == session_id,
                SessionUnit.fleet_id == fleet.id
            ).update(
                {SessionUnit.system_id: target_system_id},
                synchronize_session=False
            )

            drawn_cards = resolve_danger_cards(
                db=db,
                session_id=session_id,
                fleet=fleet,
                acting_player=acting_player,
                cards_count=planned_step["danger_cards"]
            )

            completed_steps.append({
                **planned_step,
                "drawn_cards": drawn_cards
            })

            if count_fleet_units(db, session_id, fleet.id) == 0:
                fleet_destroyed = True
                db.delete(fleet)
                db.flush()
                break

        interception_report = None
        hostile_entry = resolved_order.get("hostile_entry")

        if (
            not fleet_destroyed
            and len(completed_steps) == len(resolved_order["steps"])
            and resolved_order["order_type"] == FLEET_ORDER_MOVE_MOVE
            and hostile_entry is not None
        ):
            interceptor = hostile_entry.get("interceptor")
            interceptor_still_present = (
                interceptor is not None
                and db.query(SessionFleet).filter(
                    SessionFleet.id == interceptor.id,
                    SessionFleet.session_id == session_id,
                    SessionFleet.system_id == fleet.system_id
                ).first() is not None
                and count_fleet_units(db, session_id, interceptor.id) > 0
            )

            strike = None
            if interceptor_still_present:
                strike = resolve_one_way_interception(
                    db=db,
                    session_id=session_id,
                    moving_fleet=fleet,
                    interceptor=interceptor
                )
                fleet_destroyed = strike["moving_fleet_destroyed"]
                if fleet_destroyed:
                    delete_fleet_if_empty(db, session_id, fleet.id)

            interception_report = {
                "interception_step": hostile_entry.get("step_number", 2),
                "movement_ended_early": hostile_entry.get(
                    "movement_ended_early",
                    False
                ),
                "hostile_controlled": hostile_entry["hostile_controlled"],
                "destination_owner_player_id": hostile_entry[
                    "destination_owner_player_id"
                ],
                "destination_owner_name": hostile_entry[
                    "destination_owner_name"
                ],
                "interceptor_fleet_id": (
                    interceptor.id if interceptor_still_present else None
                ),
                "interceptor_fleet_name": (
                    interceptor.name if interceptor_still_present else None
                ),
                "interceptor_owner_player_id": (
                    interceptor.owner_player_id
                    if interceptor_still_present
                    else None
                ),
                "interceptor_owner_name": (
                    hostile_entry["interceptor_owner_name"]
                    if interceptor_still_present
                    else None
                ),
                "interceptor_was_defensive": (
                    bool(interceptor.is_defensive)
                    if interceptor_still_present
                    else False
                ),
                "attack_power": strike["attack_power"] if strike else 0,
                "target_defense": strike["target_defense"] if strike else 0,
                "damage": strike["damage"] if strike else 0,
                "damage_events": strike["damage_events"] if strike else [],
                "moving_fleet_destroyed": fleet_destroyed,
                "engagement_created": (
                    interceptor_still_present and not fleet_destroyed
                ),
                "no_return_fire": True
            }

        final_step = completed_steps[-1]
        final_system_id = final_step["to_system_id"]
        final_system_name = final_step["to_system_name"]
        completed_full_movement = (
            len(completed_steps) == len(resolved_order["steps"])
        )

        if not fleet_destroyed:
            fleet.is_defensive = (
                resolved_order["becomes_defensive"]
                and completed_full_movement
            )
            fleet.has_acted_this_round = True

        if (
            not fleet_destroyed
            and completed_full_movement
            and resolved_order["order_type"] == FLEET_ORDER_MOVE_TRANSFER
        ):
            transfer_fleet = resolved_order["transfer_fleet"]
            transfer_fleet_move_step = resolved_order[
                "transfer_fleet_move_step"
            ]
            requested_to_transfer = set(
                resolved_order["unit_ids_to_transfer_fleet"]
            )
            requested_to_command = set(
                resolved_order["unit_ids_to_command_fleet"]
            )

            surviving_source_units = {
                unit.id: unit
                for unit in get_fleet_units(
                    db=db,
                    session_id=session_id,
                    fleet_id=fleet_id
                )
            }
            current_transfer_units = {
                unit.id: unit
                for unit in get_fleet_units(
                    db=db,
                    session_id=session_id,
                    fleet_id=transfer_fleet.id
                )
            }

            # Current HP never blocks transfer. Any damaged unit that is
            # still alive remains a valid transfer target.
            moved_to_transfer = [
                surviving_source_units[unit_id]
                for unit_id in requested_to_transfer
                if unit_id in surviving_source_units
            ]
            moved_to_command = [
                current_transfer_units[unit_id]
                for unit_id in requested_to_command
                if unit_id in current_transfer_units
            ]
            missing_unit_ids = sorted(
                (requested_to_transfer - surviving_source_units.keys())
                | (requested_to_command - current_transfer_units.keys())
            )

            projected_source_count = (
                len(surviving_source_units)
                - len(moved_to_transfer)
                + len(moved_to_command)
            )
            projected_transfer_count = (
                len(current_transfer_units)
                - len(moved_to_command)
                + len(moved_to_transfer)
            )

            if (
                projected_source_count > UNITS_PER_FLEET
                or projected_transfer_count > UNITS_PER_FLEET
            ):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Fleet capacity changed while resolving danger cards. "
                        "Transfer could not be completed."
                    )
                )

            for unit in moved_to_transfer:
                unit.fleet_id = transfer_fleet.id
                unit.system_id = final_system_id

            for unit in moved_to_command:
                unit.fleet_id = fleet_id
                unit.system_id = final_system_id

            transfer_fleet.is_defensive = False
            db.flush()

            normalize_fleet_unit_slots(db, session_id, fleet_id)
            normalize_fleet_unit_slots(db, session_id, transfer_fleet.id)
            db.flush()

            source_fleet_empty = count_fleet_units(
                db, session_id, fleet_id
            ) == 0
            transfer_fleet_empty = count_fleet_units(
                db, session_id, transfer_fleet.id
            ) == 0

            partner_movement_step_report = None
            partner_movement_used = False
            partner_fleet_destroyed = False
            partner_final_system_id = final_system_id
            partner_final_system_name = final_system_name

            # The receiving fleet has one movement action remaining after the
            # transfer. If the player selected a destination, resolve that
            # movement now as part of the same 1-CP Fleet Command.
            if (
                not transfer_fleet_empty
                and transfer_fleet_move_step is not None
            ):
                partner_movement_used = True
                partner_target_system_id = transfer_fleet_move_step[
                    "to_system_id"
                ]

                transfer_fleet.system_id = partner_target_system_id
                db.query(SessionUnit).filter(
                    SessionUnit.session_id == session_id,
                    SessionUnit.fleet_id == transfer_fleet.id
                ).update(
                    {SessionUnit.system_id: partner_target_system_id},
                    synchronize_session=False
                )

                partner_drawn_cards = resolve_danger_cards(
                    db=db,
                    session_id=session_id,
                    fleet=transfer_fleet,
                    acting_player=acting_player,
                    cards_count=transfer_fleet_move_step["danger_cards"]
                )

                partner_movement_step_report = {
                    **transfer_fleet_move_step,
                    "drawn_cards": partner_drawn_cards
                }
                partner_final_system_id = partner_target_system_id
                partner_final_system_name = transfer_fleet_move_step[
                    "to_system_name"
                ]

                if count_fleet_units(
                    db,
                    session_id,
                    transfer_fleet.id
                ) == 0:
                    partner_fleet_destroyed = True
                    transfer_fleet_empty = True

            # Whether the player used the remaining move or deliberately held
            # position, the receiving fleet's two-action order is now resolved.
            if not transfer_fleet_empty:
                transfer_fleet.has_acted_this_round = True

            transfer_report = {
                "partner_fleet_id": transfer_fleet.id,
                "partner_fleet_name": transfer_fleet.name,
                "moved_to_partner": [
                    get_transfer_unit_summary(unit)
                    for unit in moved_to_transfer
                ],
                "moved_to_command_fleet": [
                    get_transfer_unit_summary(unit)
                    for unit in moved_to_command
                ],
                "missing_unit_ids": missing_unit_ids,
                "source_fleet_deleted": source_fleet_empty,
                "partner_fleet_deleted": transfer_fleet_empty,
                "partner_movement_available": True,
                "partner_movement_used": partner_movement_used,
                "partner_movement_step": partner_movement_step_report,
                "partner_final_system_id": partner_final_system_id,
                "partner_final_system_name": partner_final_system_name,
                "partner_fleet_destroyed": partner_fleet_destroyed,
                "completed": (
                    len(missing_unit_ids) == 0
                    and (
                        transfer_fleet_move_step is None
                        or partner_movement_used
                    )
                )
            }

            if source_fleet_empty:
                delete_fleet_if_empty(db, session_id, fleet_id)

            if transfer_fleet_empty:
                delete_fleet_if_empty(
                    db,
                    session_id,
                    transfer_fleet.id
                )

            db.flush()

        if fleet_destroyed:
            is_defensive = False
        else:
            is_defensive = fleet.is_defensive

        if resolved_order["order_type"] == FLEET_ORDER_MOVE_TRANSFER:
            order_completed = (
                not fleet_destroyed
                and completed_full_movement
                and transfer_report is not None
                and transfer_report["completed"]
            )
        else:
            order_completed = (
                not fleet_destroyed
                and completed_full_movement
            )

        command_report.append({
            "fleet_id": fleet_id,
            "fleet_name": fleet_name,
            "order_type": resolved_order["order_type"],
            "steps": completed_steps,
            "final_system_id": final_system_id,
            "final_system_name": final_system_name,
            "total_danger_cards": (
                sum(
                    len(step["drawn_cards"])
                    for step in completed_steps
                )
                + (
                    len(
                        transfer_report["partner_movement_step"][
                            "drawn_cards"
                        ]
                    )
                    if (
                        transfer_report
                        and transfer_report["partner_movement_step"]
                    )
                    else 0
                )
            ),
            "is_defensive": is_defensive,
            "fleet_destroyed": fleet_destroyed,
            "order_completed": order_completed,
            "transfer": transfer_report,
            "split": None,
            "retreat": resolved_order.get("retreat"),
            "combat": None,
            "interception": interception_report
        })

    action_round = game_session.current_round

    consume_command_point_and_advance_turn(
        session=game_session,
        players=players,
        acting_player=acting_player,
        db=db
    )

    create_game_log(
        db=db,
        session=game_session,
        event_type="fleet_command_resolved",
        actor=acting_player,
        payload={
            "command_points_spent": 1,
            "orders": command_report,
            "next_player_id": game_session.current_player_id
        },
        round_number=action_round
    )

    db.commit()

    return {
        "message": "Fleet command resolved",
        "session": get_full_session(session_id, db),
        "command_report": command_report
    }


@router.post("/{session_id}/archives/research")
def research_archive_blueprint(
    session_id: int,
    request: ArchiveResearchRequest,
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
            detail="Archive research can only be performed in a started session"
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
        raise HTTPException(
            status_code=400,
            detail="No current player is active"
        )

    acting_player = require_current_player_for_action(
        session=game_session,
        players=players,
        player_id=current_player.id
    )

    session_system = db.query(SessionSystem).filter(
        SessionSystem.session_id == session_id,
        SessionSystem.system_id == request.system_id
    ).first()

    if not session_system:
        raise HTTPException(
            status_code=404,
            detail="Session system not found"
        )

    star_system = db.query(StarSystem).filter(
        StarSystem.id == request.system_id
    ).first()

    if not star_system:
        raise HTTPException(
            status_code=404,
            detail="Star system not found"
        )

    if star_system.system_type != "archive":
        raise HTTPException(
            status_code=400,
            detail="Only archive systems can be researched"
        )

    archive_level = int(star_system.archive_level or 0)
    blueprint_definition = ARCHON_BLUEPRINT_BY_LEVEL.get(archive_level)

    if not blueprint_definition:
        raise HTTPException(
            status_code=400,
            detail="Archive system must have level 1-5"
        )

    if session_system.owner_player_id != acting_player.id:
        raise HTTPException(
            status_code=403,
            detail="Current player must control this archive system"
        )

    discovered_levels = get_player_blueprint_levels(
        db=db,
        session_id=session_id,
        player_id=acting_player.id
    )
    is_repeat_research = archive_level in discovered_levels

    energy_cost = get_archive_research_energy_cost(
        db=db,
        session_id=session_id,
        player_id=acting_player.id
    )

    shortage_message = get_archive_research_shortage_message(
        player=acting_player,
        energy_cost=energy_cost
    )

    if shortage_message:
        raise HTTPException(
            status_code=400,
            detail=shortage_message
        )

    action_round = game_session.current_round
    data_reward = (
        ARCHIVE_RESEARCH_REPEAT_DATA_REWARD
        if is_repeat_research
        else ARCHIVE_RESEARCH_DATA_REWARD
    )
    dominance_points_reward = 0 if is_repeat_research else ARCHIVE_BLUEPRINT_DP

    acting_player.energy -= energy_cost
    acting_player.data += data_reward

    if not is_repeat_research:
        discovered_blueprint = SessionPlayerBlueprint(
            session_id=session_id,
            player_id=acting_player.id,
            blueprint_level=blueprint_definition["level"],
            blueprint_key=blueprint_definition["key"],
            archive_system_id=star_system.id,
            discovered_round=action_round
        )
        db.add(discovered_blueprint)

    create_game_log(
        db=db,
        session=game_session,
        event_type=(
            "archive_data_extracted"
            if is_repeat_research
            else "archive_blueprint_discovered"
        ),
        actor=acting_player,
        payload={
            "system_id": star_system.id,
            "system_name": star_system.name,
            "archive_level": archive_level,
            "blueprint": serialize_archon_blueprint_catalog_item(blueprint_definition),
            "energy_cost": energy_cost,
            "data_reward": data_reward,
            "dominance_points": dominance_points_reward,
            "is_repeat_research": is_repeat_research,
        },
        round_number=action_round
    )

    consume_command_point_and_advance_turn(
        session=game_session,
        players=players,
        acting_player=acting_player,
        db=db
    )

    db.commit()

    return {
        "message": (
            "Archive data extracted"
            if is_repeat_research
            else "Archive blueprint discovered"
        ),
        "session": get_full_session(session_id, db),
        "blueprint": serialize_archon_blueprint_catalog_item(blueprint_definition),
        "is_repeat_research": is_repeat_research,
        "data_reward": data_reward,
        "dominance_points": dominance_points_reward,
    }


@router.post("/{session_id}/archon-core/claim")
def claim_archon_core(
    session_id: int,
    request: ArchonCoreClaimRequest,
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
            detail="Archon Core can only be claimed during a started session"
        )

    existing_claim = get_archon_core_claim(
        db=db,
        session_id=session_id
    )

    if existing_claim:
        raise HTTPException(
            status_code=400,
            detail="Archon Core has already been claimed"
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
        raise HTTPException(
            status_code=400,
            detail="No current player is active"
        )

    acting_player = require_current_player_for_action(
        session=game_session,
        players=players,
        player_id=current_player.id
    )

    if not player_has_all_archon_blueprints(
        db=db,
        session_id=session_id,
        player_id=acting_player.id
    ):
        raise HTTPException(
            status_code=400,
            detail=f"All {ARCHON_BLUEPRINTS_REQUIRED} Archon Blueprints are required to claim the Core"
        )

    controlled_heart = get_controlled_heart_system(
        db=db,
        session_id=session_id,
        player_id=acting_player.id,
        requested_system_id=request.system_id
    )

    if not controlled_heart:
        raise HTTPException(
            status_code=400,
            detail="Current player must control the Heart of the Galaxy / Archive V system"
        )

    _, heart_system = controlled_heart

    if acting_player.command_points_left < ARCHON_CORE_CLAIM_COMMAND_POINT_COST:
        raise HTTPException(
            status_code=400,
            detail="Current player has no command points left"
        )

    action_round = game_session.current_round

    core_claim = SessionArchonCoreClaim(
        session_id=session_id,
        player_id=acting_player.id,
        core_system_id=heart_system.id,
        claimed_round=action_round
    )
    db.add(core_claim)

    acting_player.command_points_left -= ARCHON_CORE_CLAIM_COMMAND_POINT_COST
    if acting_player.command_points_left <= 0:
        acting_player.has_passed = True

    game_session.status = ARCHON_CORE_SESSION_STATUS
    game_session.round_phase = ARCHON_CORE_SESSION_STATUS
    game_session.current_player_id = acting_player.id

    for index, player in enumerate(players):
        if player.id == acting_player.id:
            game_session.current_turn_index = index
            break

    create_game_log(
        db=db,
        session=game_session,
        event_type="archon_core_claimed",
        actor=acting_player,
        payload={
            "system_id": heart_system.id,
            "system_name": heart_system.name,
            "blueprints_required": ARCHON_BLUEPRINTS_REQUIRED,
            "command_points_cost": ARCHON_CORE_CLAIM_COMMAND_POINT_COST,
            "archon_player_id": acting_player.id,
            "archon_player_faction": acting_player.faction_name,
            "resistance_player_ids": [
                player.id
                for player in players
                if player.id != acting_player.id
            ],
        },
        round_number=action_round
    )

    db.commit()

    return {
        "message": "Archon Core claimed",
        "session": get_full_session(session_id, db),
        "archon_core_claim": serialize_archon_core_claim(
            db=db,
            claim=get_archon_core_claim(
                db=db,
                session_id=session_id
            )
        )
    }


@router.get("/{session_id}/technologies")
def get_session_technologies(
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

    return {
        "session_id": session_id,
        "catalog": [
            serialize_technology(technology)
            for technology in TECHNOLOGY_CATALOG
        ],
        "players": [
            {
                "session_player_id": player.id,
                "technologies": get_player_technologies_response(
                    db=db,
                    session_id=session_id,
                    player_id=player.id
                ),
                "dominance_points": get_player_dominance_points(
                    db=db,
                    session_id=session_id,
                    player_id=player.id
                ),
            }
            for player in players
        ],
    }


@router.post("/{session_id}/technologies/research")
def research_technology(
    session_id: int,
    request: TechnologyResearchRequest,
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
            detail="Technology can only be researched in a started session"
        )

    technology = TECHNOLOGY_BY_KEY.get(request.technology_key)

    if not technology:
        raise HTTPException(
            status_code=404,
            detail="Technology not found"
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
        raise HTTPException(
            status_code=400,
            detail="No current player is active"
        )

    acting_player = require_current_player_for_action(
        session=game_session,
        players=players,
        player_id=current_player.id
    )

    researched_keys = get_researched_technology_keys(
        db=db,
        session_id=session_id,
        player_id=acting_player.id
    )

    if request.technology_key in researched_keys:
        raise HTTPException(
            status_code=409,
            detail="Technology already researched"
        )

    if not player_has_required_building(
        db=db,
        session_id=session_id,
        player_id=acting_player.id,
        building_type=technology["building_type"]
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                f"Requires {technology['building_name']} controlled by "
                "the current player"
            )
        )

    shortage_message = get_technology_shortage_message(
        player=acting_player,
        cost=technology["cost"]
    )

    if shortage_message:
        raise HTTPException(
            status_code=400,
            detail=shortage_message
        )

    apply_technology_cost(acting_player, technology["cost"])

    action_round = game_session.current_round

    researched_technology = SessionPlayerTechnology(
        session_id=session_id,
        player_id=acting_player.id,
        technology_key=technology["key"],
        researched_round=action_round
    )
    db.add(researched_technology)

    create_game_log(
        db=db,
        session=game_session,
        event_type="technology_researched",
        actor=acting_player,
        payload={
            "technology": serialize_technology(technology),
            "cost": technology["cost"],
            "dominance_points": technology["dominance_points"],
        },
        round_number=action_round
    )

    consume_command_point_and_advance_turn(
        session=game_session,
        players=players,
        acting_player=acting_player,
        db=db
    )

    db.commit()

    return {
        "message": "Technology researched",
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

    create_game_log(
        db=db,
        session=game_session,
        event_type="game_finished",
        payload={}
    )

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