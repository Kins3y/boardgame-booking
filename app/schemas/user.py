from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    email: EmailStr
    nickname: str
    password: str
    password_confirm: str


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    nickname: str

    class Config:
        from_attributes = True


class UserNicknameUpdate(BaseModel):
    nickname: str


class UserPasswordUpdate(BaseModel):
    old_password: str
    new_password: str
    new_password_confirm: str