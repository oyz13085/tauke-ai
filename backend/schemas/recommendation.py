from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel


class RecommendationOut(BaseModel):
    id:                  uuid.UUID
    shop_id:             uuid.UUID
    product_id:          Optional[uuid.UUID]
    recommendation_type: str
    status:              str
    recommended_action:  str
    target_quantity:     Optional[float]
    target_price:        Optional[float]
    confidence_score:    float
    risk_of_inaction:    Optional[float]
    expected_gain:       Optional[float]
    reasoning_trace:     dict[str, Any]
    external_factors:    Optional[dict[str, Any]]
    glm_explanation:     Optional[str]
    feedback_rating:     Optional[int]
    feedback_note:       Optional[str]
    created_at:          datetime
    expires_at:          Optional[datetime]

    model_config = {"from_attributes": True}


class FeedbackIn(BaseModel):
    rating: int
    note:   Optional[str] = None
