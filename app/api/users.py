import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import SessionLocal
from app.models.user import User
from app.schemas.user import UserCreate
from app.schemas.user import UserNicknameUpdate
from app.schemas.user import UserPasswordUpdate
from app.schemas.user import UserResponse
from app.services.auth import hash_password
from app.services.auth import verify_password
from app.services.security import get_current_user


router = APIRouter(prefix="/user", tags=["user"])


EMAIL_REGEX = re.compile(
    r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"
)

NICKNAME_REGEX = re.compile(
    r"^[A-Za-z0-9_]{3,32}$"
)


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


def validate_email(email: str) -> str:
    cleaned_email = email.strip().lower()

    if not EMAIL_REGEX.fullmatch(cleaned_email):
        raise HTTPException(
            status_code=400,
            detail="Invalid email format"
        )

    return cleaned_email


def validate_nickname(nickname: str) -> str:
    cleaned_nickname = nickname.strip()

    if not NICKNAME_REGEX.fullmatch(cleaned_nickname):
        raise HTTPException(
            status_code=400,
            detail=(
                "Nickname may contain only Latin letters, numbers and "
                "underscore. Length: 3-32 characters"
            )
        )

    return cleaned_nickname


def validate_password(password: str):
    if len(password) < 8:
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least 8 characters"
        )


def get_admin_badge(user: User) -> str | None:
    if user.role == "super_admin":
        return "SUPER ADMIN"

    return None


@router.post("/create/", response_model=UserResponse)
def create_user(
    user: UserCreate,
    db: Session = Depends(get_db)
):
    email = validate_email(user.email)
    nickname = validate_nickname(user.nickname)

    if user.password != user.password_confirm:
        raise HTTPException(
            status_code=400,
            detail="Passwords do not match"
        )

    validate_password(user.password)

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
        email=email,
        nickname=nickname,
        password_hash=hash_password(user.password),
        role="registered_user"
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    return new_user


@router.patch("/me/nickname")
def update_my_nickname(
    payload: UserNicknameUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    nickname = validate_nickname(payload.nickname)

    existing_nickname = db.query(User).filter(
        func.lower(User.nickname) == nickname.lower(),
        User.id != current_user.id
    ).first()

    if existing_nickname:
        raise HTTPException(
            status_code=409,
            detail="Nickname already registered"
        )

    current_user.nickname = nickname

    db.commit()
    db.refresh(current_user)

    return {
        "id": current_user.id,
        "email": current_user.email,
        "nickname": current_user.nickname,
        "admin_badge": get_admin_badge(current_user)
    }


@router.patch("/me/password")
def update_my_password(
    payload: UserPasswordUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if payload.new_password != payload.new_password_confirm:
        raise HTTPException(
            status_code=400,
            detail="New passwords do not match"
        )

    validate_password(payload.new_password)

    if not verify_password(payload.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=400,
            detail="Old password is incorrect"
        )

    if verify_password(payload.new_password, current_user.password_hash):
        raise HTTPException(
            status_code=400,
            detail="New password must be different from the old password"
        )

    current_user.password_hash = hash_password(payload.new_password)

    db.commit()

    return {
        "message": "Password updated successfully"
    }