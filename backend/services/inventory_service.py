"""
Inventory Service: update inventory_items after a successful OCR pass.

For each line item in the OCRResponse:
  1. Try to match product_name_raw to an existing product in the shop catalog
     (case-insensitive substring match — good enough for MVP)
  2. If matched → upsert an inventory_items row for this batch
  3. If unmatched → create a new product stub and then insert inventory row
     so nothing is silently lost
"""
from datetime import date, timedelta

from sqlalchemy.orm import Session

from backend.models.invoice import Invoice, InvoiceLineItem
from backend.models.inventory import InventoryItem
from backend.models.product import Product
from backend.schemas.invoice import OCRResponse


def apply_ocr_to_inventory(
    db: Session,
    invoice: Invoice,
    ocr: OCRResponse,
) -> None:
    """Write line items and update inventory. Called only when needs_review=False."""
    purchase_date = ocr.invoice_date or date.today()

    for item in ocr.line_items:
        product = _match_or_create_product(db, invoice.shop_id, item.product_name_raw, item.unit)

        # Write line item
        line = InvoiceLineItem(
            invoice_id=invoice.id,
            product_name_raw=item.product_name_raw,
            matched_product_id=product.id,
            quantity=item.quantity,
            unit_raw=item.unit,
            unit_price=item.unit_price,
            total_price=item.total_price,
            ocr_confidence=item.confidence,
        )
        db.add(line)

        # Update rolling avg cost price on product
        if item.unit_price:
            product.avg_cost_price = (
                float(product.avg_cost_price or item.unit_price) * 0.8
                + item.unit_price * 0.2
            )

        # Upsert inventory batch
        expiry_date = (
            purchase_date + timedelta(days=product.spoilage_days)
            if product.spoilage_days and product.spoilage_days > 0
            else None
        )
        batch_ref = str(invoice.id)
        existing = (
            db.query(InventoryItem)
            .filter_by(shop_id=invoice.shop_id, product_id=product.id, batch_ref=batch_ref)
            .first()
        )
        if existing:
            existing.current_qty = float(existing.current_qty) + float(item.quantity)
        else:
            db.add(
                InventoryItem(
                    shop_id=invoice.shop_id,
                    product_id=product.id,
                    batch_ref=batch_ref,
                    current_qty=item.quantity,
                    unit=item.unit or product.unit,
                    cost_price=item.unit_price,
                    purchase_date=purchase_date,
                    expiry_date=expiry_date,
                )
            )

    db.flush()


def _match_or_create_product(
    db: Session, shop_id, name_raw: str, unit: str
) -> Product:
    """Case-insensitive substring match against shop product catalog."""
    search = name_raw.lower().strip()
    products = db.query(Product).filter_by(shop_id=shop_id).all()

    for p in products:
        if search in p.name.lower() or p.name.lower() in search:
            return p

    # No match — create a stub so inventory is never silently dropped
    stub = Product(
        shop_id=shop_id,
        name=name_raw.strip(),
        unit=unit or "unit",
        category="uncategorised",
    )
    db.add(stub)
    db.flush()
    return stub
