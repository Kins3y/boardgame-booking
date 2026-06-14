import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.database import Base, engine

from app.api.users import router as users_router
from app.api.auth import router as auth_router

from app.game.models.star_system import StarSystem
from app.game.models.system_connection import SystemConnection
from app.game.models.game_map import GameMap
from app.game.models.game_session import GameSession
from app.game.models.session_player import SessionPlayer
from app.game.models.session_system import SessionSystem
from app.game.models.session_building import SessionBuilding
from app.game.models.civilization import Civilization
from app.game.models.session_unit import SessionUnit

from app.game.api.star_systems import router as star_system_router
from app.game.api.system_connections import router as system_connection_router
from app.game.api.game_maps import router as game_map_router
from app.game.api.game_sessions import router as game_session_router
from app.game.api.buildings import router as buildings_router
from app.game.api.civilizations import router as civilizations_router
from app.game.api.map_editor import router as map_editor_router


load_dotenv()

ENVIRONMENT = os.getenv("ENVIRONMENT", "local")
IS_PRODUCTION = ENVIRONMENT == "production"

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
frontend_www_url = os.getenv("FRONTEND_WWW_URL", "")

origins = {
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    frontend_url
}

if frontend_www_url:
    origins.add(frontend_www_url)

app = FastAPI(
    title="Archont API",
    docs_url=None if IS_PRODUCTION else "/docs",
    redoc_url=None if IS_PRODUCTION else "/redoc",
    openapi_url=None if IS_PRODUCTION else "/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)

app.include_router(users_router)
app.include_router(auth_router)
app.include_router(star_system_router)
app.include_router(system_connection_router)
app.include_router(game_map_router)
app.include_router(game_session_router)
app.include_router(buildings_router)
app.include_router(civilizations_router)
app.include_router(map_editor_router)


@app.get("/")
def home():
    return {
        "message": "Archont API",
        "environment": ENVIRONMENT
    }