import uuid
from sqlalchemy import Column, Text, Date, Numeric, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from backend.database import Base


class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    shop_id = Column(UUID(as_uuid=True), ForeignKey("shops.id", ondelete="CASCADE"), nullable=False)
    supplier_name = Column(Text)
    invoice_number = Column(Text)
    invoice_date = Column(Date)
    total_amount = Column(Numeric(10, 2))
    currency = Column(Text, default="MYR")
    raw_image_url = Column(Text, nullable=False)
    ocr_confidence = Column(Numeric(4, 3))
    ocr_raw_json = Column(JSONB)
    processing_status = Column(Text, default="pending")  # pending | processing | done | failed | needs_review
    failure_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    shop = relationship("Shop", back_populates="invoices")
    line_items = relationship("InvoiceLineItem", back_populates="invoice", cascade="all, delete-orphan")


class InvoiceLineItem(Base):
    __tablename__ = "invoice_line_items"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id = Column(UUID(as_uuid=True), ForeignKey("invoices.id", ondelete="CASCADE"), nullable=False)
    product_name_raw = Column(Text, nullable=False)
    matched_product_id = Column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    quantity = Column(Numeric(10, 3), nullable=False)
    unit_raw = Column(Text)
    unit_price = Column(Numeric(10, 2))
    total_price = Column(Numeric(10, 2))
    ocr_confidence = Column(Numeric(4, 3))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    invoice = relationship("Invoice", back_populates="line_items")
    matched_product = relationship("Product")
