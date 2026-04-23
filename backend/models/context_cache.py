import uuid
from sqlalchemy import Column, Text, Date, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from backend.database import Base


class ExternalContextCache(Base):
    __tablename__ = "external_context_cache"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False)
    context_type = Column(Text, nullable=False)  # weather | public_holiday | um_calendar | event
    context_date = Column(Date, nullable=False)
    data_json = Column(JSONB, nullable=False)
    fetched_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("shop_id", "context_type", "context_date", name="uq_context_cache"),)

    shop = relationship("Shop", back_populates="context_cache")
