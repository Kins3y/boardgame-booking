from sqlalchemy import Column, Integer, String, Boolean, Text

from app.db.database import Base


class Civilization(Base):
    __tablename__ = "civilizations"

    id = Column(Integer, primary_key=True, index=True)

    name = Column(String(100), nullable=False, unique=True, index=True)
    slug = Column(String(100), nullable=False, unique=True, index=True)

    short_description = Column(String(255), nullable=False)
    lore_description = Column(Text, nullable=True)

    starting_matter = Column(Integer, default=10)
    starting_energy = Column(Integer, default=5)
    starting_data = Column(Integer, default=1)
    starting_food = Column(Integer, default=10)

    ability_name = Column(String(100), nullable=False)
    ability_description = Column(Text, nullable=False)

    mechanic_key = Column(String(100), nullable=False)

    is_active = Column(Boolean, default=True)