import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models.invoice import Invoice
from backend.models.shop import Shop
from backend.schemas.invoice import InvoiceDetailOut, InvoiceOut
from backend.services.inventory_service import apply_ocr_to_inventory
from backend.services.ocr_service import OCRError, extract_receipt

router = APIRouter(tags=["invoices"])

_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic"}


@router.post("/invoices/upload", response_model=InvoiceOut, status_code=202)
async def upload_invoice(
    background_tasks: BackgroundTasks,
    shop_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # Validate shop exists
    shop = db.query(Shop).filter_by(id=shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    # Validate file type
    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type '{file.content_type}'. Upload a JPEG, PNG, WebP or HEIC image.",
        )

    # Save image to disk
    upload_dir = Path(settings.image_upload_dir) / str(shop_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4()}{Path(file.filename or 'receipt.jpg').suffix}"
    image_path = upload_dir / filename
    image_path.write_bytes(await file.read())

    # Create invoice record (status=processing)
    invoice = Invoice(
        shop_id=shop_id,
        raw_image_url=str(image_path),
        processing_status="processing",
    )
    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    # Run OCR + inventory update in the background
    background_tasks.add_task(_process_invoice, invoice.id, str(image_path))

    return invoice


@router.get("/invoices/{invoice_id}", response_model=InvoiceDetailOut)
def get_invoice(invoice_id: uuid.UUID, db: Session = Depends(get_db)):
    invoice = db.query(Invoice).filter_by(id=invoice_id).first()
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


def _process_invoice(invoice_id: uuid.UUID, image_path: str) -> None:
    """Background task: OCR → DB write → inventory update → trigger reasoning."""
    from backend.database import SessionLocal

    db = SessionLocal()
    try:
        invoice = db.query(Invoice).filter_by(id=invoice_id).first()
        if not invoice:
            return

        import asyncio
        try:
            ocr, needs_review = asyncio.run(extract_receipt(image_path))
        except OCRError as exc:
            invoice.processing_status = "failed"
            invoice.failure_reason = str(exc)
            db.commit()
            return

        # Persist OCR metadata on invoice
        invoice.supplier_name = ocr.supplier_name
        invoice.invoice_number = ocr.invoice_number
        invoice.invoice_date = ocr.invoice_date
        invoice.total_amount = ocr.total_amount
        invoice.ocr_confidence = ocr.overall_confidence
        invoice.ocr_raw_json = ocr.model_dump()

        if needs_review:
            invoice.processing_status = "needs_review"
            db.commit()
            return

        # Apply to inventory
        apply_ocr_to_inventory(db, invoice, ocr)
        invoice.processing_status = "done"
        db.commit()

        # Placeholder: reasoning engine will be wired in Step 4
        _trigger_reasoning(invoice.shop_id)

    except Exception as exc:
        db.rollback()
        invoice = db.query(Invoice).filter_by(id=invoice_id).first()
        if invoice:
            invoice.processing_status = "failed"
            invoice.failure_reason = str(exc)
            db.commit()
    finally:
        db.close()


def _trigger_reasoning(shop_id: uuid.UUID) -> None:
    """Run the reasoning engine for every product in the shop."""
    from backend.database import SessionLocal
    from backend.engine.reasoning import ExternalContext, run_for_shop

    db = SessionLocal()
    try:
        run_for_shop(db, shop_id, ExternalContext())
    except Exception:
        pass   # reasoning failures must never break the invoice pipeline
    finally:
        db.close()
