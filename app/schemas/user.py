from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    nickname: str | None = None

class UserResponse(BaseModel):
    id: int
    email: EmailStr
    nickname: str

    class Config:
        from_attributes = True