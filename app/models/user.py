from sqlalchemy import Column, Integer, String

from app.db.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)

    email = Column(String, nullable=False, unique=True, index=True)
    nickname = Column(String, nullable=False, unique=True, index=True)

    password_hash = Column(String, nullable=False)