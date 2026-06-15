import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.db.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate
from app.schemas.user import UserResponse
from app.services.auth import hash_password


router = APIRouter(prefix="/user", tags=["user"])


EMAIL_REGEX = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)

NICKNAME_REGEX = re.compile(
    r"^[A-Za-zА-Яа-яЁё0-9_]{3,30}$"
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/create/", response_model=UserResponse)
def create_user(user: UserCreate, db: Session = Depends(get_db)):
    email = user.email.strip().lower()
    nickname = user.nickname.strip()

    if not EMAIL_REGEX.fullmatch(email):
        raise HTTPException(
            status_code=400,
            detail="Invalid email format"
        )

    if not NICKNAME_REGEX.fullmatch(nickname):
        raise HTTPException(
            status_code=400,
            detail="Nickname may contain only letters, numbers and underscore. Length: 3-30 characters"
        )

    if len(user.password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must be at least 8 characters long"
        )

    existing_email = db.query(User).filter(
        func.lower(User.email) == email
    ).first()

    if existing_email:
        raise HTTPException(
            status_code=409,
            detail="Email already registered"
        )

    existing_nickname = db.query(User).filter(
        func.lower(User.nickname) == nickname.lower()
    ).first()

    if existing_nickname:
        raise HTTPException(
            status_code=409,
            detail="Nickname already registered"
        )

    new_user = User(
        email=user.email,
        nickname=user.nickname,
        password_hash=hash_password(user.password),
        role="registered_user"
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user