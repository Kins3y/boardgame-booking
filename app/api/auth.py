from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from jose import jwt, JWTError

from app.db.database import SessionLocal
from app.models.user import User
from app.schemas.auth import LoginRequest
from app.schemas.token import TokenResponse, RefreshRequest
from app.services.auth import (
    verify_password,
    create_access_token,
    create_refresh_token,
    SECRET_KEY,
    ALGORITHM
)
from app.services.security import get_current_user


router = APIRouter(prefix="/auth", tags=["auth"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.post("/login", response_model=TokenResponse)
def login(
        login_data: LoginRequest,
        db: Session = Depends(get_db)
):
    login_identifier = login_data.email.strip().lower()

    user = db.query(User).filter(
        or_(
            func.lower(User.email) == login_identifier,
            func.lower(User.nickname) == login_identifier
        )
    ).first()

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    if not verify_password(login_data.password, user.password_hash):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials"
        )

    access_token = create_access_token(
        data={"sub": str(user.id)}
    )

    refresh_token = create_refresh_token(
        data={"sub": str(user.id)}
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }


@router.post("/refresh")
def refresh_token(
    data: RefreshRequest,
    db: Session = Depends(get_db)
):
    try:
        payload = jwt.decode(
            data.refresh_token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("sub")
        token_type = payload.get("type")

        if token_type != "refresh":
            raise HTTPException(
                status_code=401,
                detail="Invalid token type"
            )

        user = db.query(User).filter(User.id == int(user_id)).first()

        if not user:
            raise HTTPException(
                status_code=401,
                detail="User not found"
            )

        new_access_token = create_access_token(
            {"sub": str(user.id)}
        )

        return {
            "access_token": new_access_token,
            "token_type": "bearer"
        }

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid refresh token"
        )


@router.get("/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "nickname": current_user.nickname,
        "role": current_user.role
    }