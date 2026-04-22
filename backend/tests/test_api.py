"""
Invoice API tests — database and GLM are both mocked.
Run: pytest backend/tests/test_api.py -v
"""
import io
import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.database import get_db
from backend.schemas.invoice import OCRResponse, OCRLineItem

_SHOP_ID = uuid.uuid4()


# ── Helpers ────────────────────────────────────────────────────────────────

def _fake_shop():
    shop = MagicMock()
    shop.id = _SHOP_ID
    return shop


def _fake_invoice(status="processing"):
    inv = MagicMock()
    inv.id = uuid.uuid4()
    inv.shop_id = _SHOP_ID
    inv.raw_image_url = "/uploads/test.jpg"
    inv.processing_status = status
    inv.supplier_name = None
    inv.invoice_number = None
    inv.invoice_date = None
    inv.total_amount = None
    inv.currency = "MYR"
    inv.ocr_confidence = None
    inv.failure_reason = None
    inv.created_at = "2026-04-23T00:00:00+00:00"
    inv.line_items = []
    return inv


def _tiny_jpeg() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (600, 800), color="white").save(buf, format="JPEG")
    return buf.getvalue()


def _make_db(shop=None, invoice=None):
    """Return a mock Session pre-configured with shop/invoice lookups."""
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.side_effect = [
        shop,    # first call: shop lookup
        invoice, # second call: invoice lookup (if needed)
    ]
    return db


# ── Upload tests ───────────────────────────────────────────────────────────

def test_upload_invoice_returns_202(tmp_path):
    """Valid JPEG upload → 202 Accepted."""
    inv = _fake_invoice()
    db = _make_db(shop=_fake_shop())

    app.dependency_overrides[get_db] = lambda: db

    with patch("backend.routers.invoices._process_invoice"), \
         patch("backend.routers.invoices.Invoice", return_value=inv), \
         patch("backend.routers.invoices.settings") as mock_settings:

        mock_settings.image_upload_dir = str(tmp_path)

        response = TestClient(app).post(
            "/api/invoices/upload",
            data={"shop_id": str(_SHOP_ID)},
            files={"file": ("receipt.jpg", _tiny_jpeg(), "image/jpeg")},
        )

    app.dependency_overrides.clear()
    assert response.status_code == 202


def test_upload_invoice_wrong_file_type_returns_422():
    """Uploading a PDF → 422 Unprocessable."""
    db = _make_db(shop=_fake_shop())
    app.dependency_overrides[get_db] = lambda: db

    response = TestClient(app).post(
        "/api/invoices/upload",
        data={"shop_id": str(_SHOP_ID)},
        files={"file": ("doc.pdf", b"%PDF-1.4", "application/pdf")},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 422


def test_upload_invoice_shop_not_found_returns_404():
    """Unknown shop_id → 404."""
    db = _make_db(shop=None)
    app.dependency_overrides[get_db] = lambda: db

    response = TestClient(app).post(
        "/api/invoices/upload",
        data={"shop_id": str(uuid.uuid4())},
        files={"file": ("receipt.jpg", _tiny_jpeg(), "image/jpeg")},
    )

    app.dependency_overrides.clear()
    assert response.status_code == 404


def test_get_invoice_not_found_returns_404():
    """Unknown invoice id → 404."""
    db = _make_db(shop=None, invoice=None)
    app.dependency_overrides[get_db] = lambda: db

    response = TestClient(app).get(f"/api/invoices/{uuid.uuid4()}")

    app.dependency_overrides.clear()
    assert response.status_code == 404


# ── Inventory service unit tests ───────────────────────────────────────────

def test_apply_ocr_creates_product_stub_when_no_match():
    """Unmatched product name → stub Product created, inventory row inserted."""
    from backend.services.inventory_service import apply_ocr_to_inventory

    db = MagicMock()
    db.query.return_value.filter_by.return_value.all.return_value = []
    db.query.return_value.filter_by.return_value.first.return_value = None

    invoice = MagicMock()
    invoice.id = uuid.uuid4()
    invoice.shop_id = _SHOP_ID

    ocr = OCRResponse(
        overall_confidence=0.9,
        line_items=[
            OCRLineItem(
                product_name_raw="Teh Tarik 1kg",
                quantity=5,
                unit="kg",
                unit_price=8.0,
                total_price=40.0,
                confidence=0.95,
            )
        ],
    )

    apply_ocr_to_inventory(db, invoice, ocr)
    assert db.add.call_count >= 2
    db.flush.assert_called()


def test_apply_ocr_matches_existing_product():
    """Existing product name match → no new stub, rolling avg cost updated."""
    from backend.services.inventory_service import apply_ocr_to_inventory

    existing_product = MagicMock()
    existing_product.id = uuid.uuid4()
    existing_product.name = "Teh Tarik"
    existing_product.unit = "kg"
    existing_product.spoilage_days = 3
    existing_product.avg_cost_price = 7.5

    db = MagicMock()
    db.query.return_value.filter_by.return_value.all.return_value = [existing_product]
    db.query.return_value.filter_by.return_value.first.return_value = None

    invoice = MagicMock()
    invoice.id = uuid.uuid4()
    invoice.shop_id = _SHOP_ID

    ocr = OCRResponse(
        overall_confidence=0.9,
        line_items=[
            OCRLineItem(
                product_name_raw="Teh Tarik 1kg",
                quantity=5,
                unit="kg",
                unit_price=8.0,
                total_price=40.0,
                confidence=0.95,
            )
        ],
    )

    apply_ocr_to_inventory(db, invoice, ocr)
    assert existing_product.avg_cost_price != 7.5
