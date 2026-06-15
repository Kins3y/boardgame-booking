import json
import urllib.request


LOCAL_API_URL = "http://127.0.0.1:8000"
PROD_API_URL = "https://api.archont-board-game.online"

LOCAL_MAP_ID = 4  # поменяй на id нужной локальной карты


def get_json(url: str):
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(url: str, payload: dict):
    data = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json"
        },
        method="POST"
    )

    with urllib.request.urlopen(request) as response:
        return json.loads(response.read().decode("utf-8"))


local_map = get_json(
    f"{LOCAL_API_URL}/game/maps/editor/{LOCAL_MAP_ID}"
)

payload = {
    "name": local_map["name"],
    "players_count": local_map["players_count"],
    "grid_width": local_map["grid_width"],
    "grid_height": local_map["grid_height"],
    "systems": [
        {
            "client_id": str(system["id"]),
            "name": system["name"],
            "x": system["x"],
            "y": system["y"],
            "system_type": system["system_type"],
            "archive_level": system["archive_level"],
            "mineral_slots": system["mineral_slots"],
            "energy_slots": system["energy_slots"],
            "storage_slots": system["storage_slots"],
            "research_center_slots": system["research_center_slots"]
        }
        for system in local_map["systems"]
    ],
    "connections": [
        {
            "from_client_id": str(connection["from_system_id"]),
            "to_client_id": str(connection["to_system_id"]),
            "is_dangerous": connection["is_dangerous"],
            "is_wraparound": connection["is_wraparound"]
        }
        for connection in local_map["connections"]
    ]
}

created_map = post_json(
    f"{PROD_API_URL}/game/maps/editor/",
    payload
)

print("Map migrated successfully")
print("Local map id:", LOCAL_MAP_ID)
print("Production map id:", created_map["id"])
