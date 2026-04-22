import uuid
from sqlalchemy import Column, Text, Integer, Numeric, DateTime, ForeignKey, func, CheckConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from backend.database import Base


class AIRecommendation(Base):
    __tablename__ = "ai_recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False)
    product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    recommendation_type = Column(Text, nullable=False)  # price_increase | price_decrease | reorder | stockout_warning | spoilage_warning
    status = Column(Text, default="active")             # active | dismissed | acted_on | expired
    recommended_action = Column(Text, nullable=False)
    target_quantity = Column(Numeric(10, 2))
    target_price = Column(Numeric(10, 2))
    confidence_score = Column(Numeric(4, 3), nullable=False)
    risk_of_inaction = Column(Numeric(10, 2))
    expected_gain = Column(Numeric(10, 2))
    reasoning_trace = Column(JSONB, nullable=False)
    external_factors = Column(JSONB)
    glm_explanation = Column(Text)
    feedback_rating = Column(Integer)
    feedback_note = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True))

    __table_args__ = (CheckConstraint("feedback_rating BETWEEN 1 AND 5", name="ck_feedback_rating"),)

    shop = relationship("Shop", back_populates="recommendations")
    product = relationship("Product", back_populates="recommendations")