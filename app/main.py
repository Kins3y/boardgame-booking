from fastapi import FastAPI

from app.db.database import Base, engine

from app.api.users import router as users_router
from app.api.auth import router as auth_router

from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Board Game Booking")

Base.metadata.create_all(bind=engine)

app.include_router(users_router)
app.include_router(auth_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # фронт
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "Board Game Booking API"}