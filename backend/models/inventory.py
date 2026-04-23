import uuid
from sqlalchemy import Column, Text, Date, Numeric, Boolean, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from backend.database import Base


class InventoryItem(Base):
    __tablename__ = "inventory_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    batch_ref = Column(Text)
    current_qty = Column(Numeric(10, 3), nullable=False, default=0)
    unit = Column(Text, nullable=False)
    cost_price = Column(Numeric(10, 2))
    purchase_date = Column(Date)
    expiry_date = Column(Date)
    is_depleted = Column(Boolean, default=False)
    last_updated = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("shop_id", "product_id", "batch_ref", name="uq_inventory_batch"),)

    shop = relationship("Shop", back_populates="inventory_items")
    product = relationship("Product", back_populates="inventory_items")
