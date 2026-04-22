"""
OCR service tests — all GLM calls are mocked so no API key needed.
Run: pytest backend/tests/test_ocr.py -v
"""
import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from backend.schemas.invoice import OCRResponse, OCRLineItem
from backend.services.ocr_service import extract_receipt, OCRError, _parse_json, _extract_content


# ── Schema / validation tests (no I/O) ──────────────────────────────────────

def test_ocr_response_total_mismatch_flag():
    """Line items sum deviates >5% from declared total → TOTAL_MISMATCH warning added."""
    data = OCRResponse(
        total_amount=100.0,
        overall_confidence=0.9,
        line_items=[
            OCRLineItem(product_name_raw="Teh", quantity=1, unit_price=50.0, total_price=50.0, confidence=0.9),
            OCRLineItem(product_name_raw="Roti", quantity=1, unit_price=40.0, total_price=40.0, confidence=0.9),
        ],
    )
    assert "TOTAL_MISMATCH" in data.warnings


def test_ocr_response_no_mismatch_within_tolerance():
    """Line items within 5% tolerance → no TOTAL_MISMATCH."""
    data = OCRResponse(
        total_amount=100.0,
        overall_confidence=0.9,
        line_items=[
            OCRLineItem(product_name_raw="Teh", quantity=1, unit_price=100.0, total_price=100.0, confidence=0.9),
        ],
    )
    assert "TOTAL_MISMATCH" not in data.warnings


def test_low_confidence_flag():
    """overall_confidence < 0.5 → LOW_CONFIDENCE_NEEDS_REVIEW as first warning."""
    data = OCRResponse(overall_confidence=0.3)
    assert data.warnings[0] == "LOW_CONFIDENCE_NEEDS_REVIEW"


def test_parse_json_strips_markdown_fences():
    content = '```json\n{"supplier_name": "Ali Sdn Bhd", "overall_confidence": 0.9, "line_items": [], "warnings": []}\n```'
    result = _parse_json(content)
    assert result["supplier_name"] == "Ali Sdn Bhd"


def test_parse_json_no_json_raises():
    with pytest.raises(OCRError, match="No JSON object found"):
        _parse_json("Sorry, I cannot read this image.")


def test_extract_content_bad_structure_raises():
    with pytest.raises(OCRError, match="Unexpected GLM response structure"):
        _extract_content({"error": "quota exceeded"})


# ── Integration-style tests (GLM mocked) ────────────────────────────────────

_GOOD_OCR_PAYLOAD = {
    "supplier_name": "Pembekal Sdn Bhd",
    "invoice_number": "INV-001",
    "invoice_date": "2026-04-23",
    "currency": "MYR",
    "total_amount": 55.0,
    "line_items": [
        {"product_name_raw": "Teh Tarik 1kg", "quantity": 5, "unit": "kg",
         "unit_price": 8.0, "total_price": 40.0, "confidence": 0.95},
        {"product_name_raw": "Gula 1kg", "quantity": 3, "unit": "kg",
         "unit_price": 5.0, "total_price": 15.0, "confidence": 0.92},
    ],
    "overall_confidence": 0.93,
    "warnings": [],
}

def _mock_glm_response(payload: dict) -> dict:
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


@pytest.mark.asyncio
async def test_extract_receipt_happy_path(tmp_path):
    """Clear printed receipt → high confidence, no needs_review."""
    # Create a dummy image file (100x100 white image)
    from PIL import Image
    img_path = tmp_path / "receipt.jpg"
    Image.new("RGB", (600, 800), color="white").save(img_path)

    with patch("backend.services.ocr_service.glm_ocr", new_callable=AsyncMock) as mock_glm:
        mock_glm.return_value = _mock_glm_response(_GOOD_OCR_PAYLOAD)
        result, needs_review = await extract_receipt(str(img_path))

    assert needs_review is False
    assert result.overall_confidence == 0.93
    assert result.supplier_name == "Pembekal Sdn Bhd"
    assert len(result.line_items) == 2


@pytest.mark.asyncio
async def test_extract_receipt_low_res_raises(tmp_path):
    """Image smaller than 300px → OCRError before GLM call."""
    from PIL import Image
    img_path = tmp_path / "tiny.jpg"
    Image.new("RGB", (100, 150), color="white").save(img_path)

    with pytest.raises(OCRError, match="resolution too low"):
        await extract_receipt(str(img_path))


@pytest.mark.asyncio
async def test_extract_receipt_low_confidence_needs_review(tmp_path):
    """overall_confidence < 0.5 → needs_review=True."""
    from PIL import Image
    img_path = tmp_path / "blurry.jpg"
    Image.new("RGB", (600, 800), color="white").save(img_path)

    blurry_payload = {**_GOOD_OCR_PAYLOAD, "overall_confidence": 0.3, "warnings": []}

    with patch("backend.services.ocr_service.glm_ocr", new_callable=AsyncMock) as mock_glm:
        mock_glm.return_value = _mock_glm_response(blurry_payload)
        result, needs_review = await extract_receipt(str(img_path))

    assert needs_review is True
    assert "LOW_CONFIDENCE_NEEDS_REVIEW" in result.warnings


@pytest.mark.asyncio
async def test_extract_receipt_total_mismatch_warning(tmp_path):
    """Line items don't add up → TOTAL_MISMATCH in warnings."""
    from PIL import Image
    img_path = tmp_path / "receipt.jpg"
    Image.new("RGB", (600, 800), color="white").save(img_path)

    mismatch_payload = {
        **_GOOD_OCR_PAYLOAD,
        "total_amount": 200.0,  # declared total doesn't match line items (55.0)
        "warnings": [],
    }

    with patch("backend.services.ocr_service.glm_ocr", new_callable=AsyncMock) as mock_glm:
        mock_glm.return_value = _mock_glm_response(mismatch_payload)
        result, _ = await extract_receipt(str(img_path))

    assert "TOTAL_MISMATCH" in result.warnings
