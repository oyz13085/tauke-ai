"""
OCR Service: image → GLM-4V → validated OCRResponse

Guards applied (in order):
  1. Resolution check  — reject if shortest side < 300px
  2. GLM call          — multimodal receipt extraction
  3. JSON parse        — extract content from GLM response envelope
  4. Pydantic parse    — OCRResponse validates types + total mismatch
  5. Confidence floor  — overall_confidence < 0.5 → needs_review, no DB write
"""
import json
import re
from pathlib import Path

from PIL import Image

from backend.schemas.invoice import OCRResponse
from backend.services.glm_client import glm_ocr


MIN_RESOLUTION_PX = 300
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


class OCRError(Exception):
    pass


async def extract_receipt(image_path: str) -> tuple[OCRResponse, bool]:
    """
    Returns (OCRResponse, needs_review).
    needs_review=True means confidence is too low to auto-write inventory.
    Raises OCRError on unrecoverable failures.
    """
    _check_resolution(image_path)

    raw_response = await glm_ocr(image_path)
    content = _extract_content(raw_response)
    ocr_data = _parse_json(content)
    response = OCRResponse.model_validate(ocr_data)

    needs_review = (
        response.overall_confidence < 0.5
        or "LOW_CONFIDENCE_NEEDS_REVIEW" in response.warnings
    )
    return response, needs_review


def _check_resolution(image_path: str) -> None:
    try:
        with Image.open(image_path) as img:
            shortest = min(img.size)
            if shortest < MIN_RESOLUTION_PX:
                raise OCRError(
                    f"Image resolution too low ({shortest}px). "
                    f"Minimum {MIN_RESOLUTION_PX}px on shortest side."
                )
    except OCRError:
        raise
    except Exception as exc:
        raise OCRError(f"Cannot open image: {exc}") from exc


def _extract_content(raw_response: dict) -> str:
    try:
        return raw_response["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise OCRError(f"Unexpected GLM response structure: {exc}") from exc


def _parse_json(content: str) -> dict:
    # GLM sometimes wraps JSON in markdown code fences — strip them
    match = _JSON_RE.search(content)
    if not match:
        raise OCRError(f"No JSON object found in GLM response: {content[:200]}")
    try:
        return json.loads(match.group())
    except json.JSONDecodeError as exc:
        raise OCRError(f"GLM returned malformed JSON: {exc}") from exc
