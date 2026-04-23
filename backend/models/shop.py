import uuid
from sqlalchemy import Column, Text, Boolean, DateTime, Numeric, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from backend.database import Base


class Shop(Base):
    __tablename__ = "shops"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    shop_type = Column(Text, default="mamak")
    location_lat = Column(Numeric(9, 6))
    location_lng = Column(Numeric(9, 6))
    city = Column(Text, default="Kuala Lumpur")
    is_halal = Column(Boolean, default=True)
    operating_hours = Column(JSONB)
    expo_push_token = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    owner = relationship("User", back_populates="shops")
    products = relationship("Product", back_populates="shop", cascade="all, delete-orphan")
    invoices = relationship("Invoice", back_populates="shop", cascade="all, delete-orphan")
    inventory_items = relationship("InventoryItem", back_populates="shop", cascade="all, delete-orphan")
    recommendations = relationship("AIRecommendation", back_populates="shop", cascade="all, delete-orphan")
    context_cache = relationship("ExternalContextCache", back_populates="shop", cascade="all, delete-orphan")
