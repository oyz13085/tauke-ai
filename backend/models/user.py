import uuid
from sqlalchemy import Column, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(Text, unique=True, nullable=False)
    name = Column(Text, nullable=False)
    phone = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    shops = relationship("Shop", back_populates="owner", cascade="all, delete-orphan")
