import uuid
from sqlalchemy import Column, Text, Integer, Numeric, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from backend.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    sku = Column(Text)
    category = Column(Text)  # beverage | bread | protein | veg | dry_goods
    unit = Column(Text, default="unit")
    avg_cost_price = Column(Numeric(10, 2))
    avg_selling_price = Column(Numeric(10, 2))
    spoilage_days = Column(Integer, default=3)
    min_stock_threshold = Column(Numeric(10, 2), default=0)
    reorder_quantity = Column(Numeric(10, 2))
    demand_elasticity = Column(Numeric(4, 2), default=-1.2)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("shop_id", "name", name="uq_shop_product_name"),)

    shop = relationship("Shop", back_populates="products")
    inventory_items = relationship("InventoryItem", back_populates="product")
    recommendations = relationship("AIRecommendation", back_populates="product")
