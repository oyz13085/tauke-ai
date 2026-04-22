from __future__ import annotations
import uuid
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class InventoryItemOut(BaseModel):
    id: uuid.UUID
    shop_id: uuid.UUID
    product_id: uuid.UUID
    batch_ref: Optional[str]
    current_qty: float
    unit: str
    cost_price: Optional[float]
    purchase_date: Optional[date]
    expiry_date: Optional[date]
    is_depleted: bool
    last_updated: datetime

    model_config = {"from_attributes": True}
