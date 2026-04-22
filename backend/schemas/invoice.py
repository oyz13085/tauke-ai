from __future__ import annotations
import uuid
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, model_validator


class OCRLineItem(BaseModel):
    product_name_raw: str
    quantity: float
    unit: str = "unit"
    unit_price: Optional[float] = None
    total_price: Optional[float] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class OCRResponse(BaseModel):
    supplier_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    currency: str = "MYR"
    total_amount: Optional[float] = None
    line_items: list[OCRLineItem] = []
    overall_confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    warnings: list[str] = []

    @model_validator(mode="after")
    def check_total_mismatch(self) -> "OCRResponse":
        """Cross-validate line item sum vs declared total — guard against hallucinated numbers."""
        computable = [li.total_price for li in self.line_items if li.total_price is not None]
        if self.total_amount and computable:
            line_sum = sum(computable)
            deviation = abs(line_sum - self.total_amount) / self.total_amount
            if deviation > 0.05 and "TOTAL_MISMATCH" not in self.warnings:
                self.warnings.append("TOTAL_MISMATCH")
        if self.overall_confidence < 0.5 and "LOW_CONFIDENCE_NEEDS_REVIEW" not in self.warnings:
            self.warnings.insert(0, "LOW_CONFIDENCE_NEEDS_REVIEW")
        return self


class InvoiceOut(BaseModel):
    id: uuid.UUID
    shop_id: uuid.UUID
    supplier_name: Optional[str]
    invoice_number: Optional[str]
    invoice_date: Optional[date]
    total_amount: Optional[float]
    currency: str
    raw_image_url: str
    ocr_confidence: Optional[float]
    processing_status: str
    failure_reason: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class InvoiceDetailOut(InvoiceOut):
    line_items: list["LineItemOut"] = []


class LineItemOut(BaseModel):
    id: uuid.UUID
    product_name_raw: str
    matched_product_id: Optional[uuid.UUID]
    quantity: float
    unit_raw: Optional[str]
    unit_price: Optional[float]
    total_price: Optional[float]
    ocr_confidence: Optional[float]

    model_config = {"from_attributes": True}
