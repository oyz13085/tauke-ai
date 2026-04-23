"""
GLM client — wraps ILMU-GLM-5.1 via the Anthropic SDK.

The hackathon provides ILMU-GLM-5.1 (Z.ai × YTL AI Lab) which exposes an
Anthropic-compatible Messages API at https://api.ilmu.ai/anthropic.
We point the Anthropic SDK at that base URL so we get type-safe requests
and automatic retries for free.

API key: https://console.ilmu.ai/dashboard → API Keys
"""
import base64
import json
from pathlib import Path

import anthropic

from backend.config import settings


def _client() -> anthropic.Anthropic:
    return anthropic.Anthropic(
        api_key=settings.glm_api_key,
        base_url=settings.glm_base_url,
    )


async def glm_ocr(image_path: str) -> dict:
    """
    Send an image to ILMU-GLM-5.1 for receipt OCR.
    Returns the raw Anthropic response as a dict (content[0].text holds the JSON).
    """
    image_bytes = Path(image_path).read_bytes()
    image_b64 = base64.standard_b64encode(image_bytes).decode()
    ext = Path(image_path).suffix.lstrip(".").lower()
    media_type = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"

    client = _client()
    response = client.messages.create(
        model=settings.glm_model,
        max_tokens=2048,
        system=_OCR_SYSTEM_PROMPT,
        temperature=0.1,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": image_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Please extract the receipt data from this supplier invoice.",
                    },
                ],
            }
        ],
    )
    # Return in a normalised shape so ocr_service.py can parse it identically
    return {"choices": [{"message": {"content": response.content[0].text}}]}


async def glm_explain(reasoning_trace: dict, product_context: dict) -> dict:
    """
    Ask ILMU-GLM-5.1 to write a Manglish explanation of a pre-computed recommendation.
    Returns normalised dict with choices[0].message.content.
    """
    user_content = json.dumps(
        {"reasoning_trace": reasoning_trace, "product": product_context},
        ensure_ascii=False,
    )

    client = _client()
    response = client.messages.create(
        model=settings.glm_model,
        max_tokens=512,
        system=_EXPLAIN_SYSTEM_PROMPT,
        temperature=0.5,
        messages=[{"role": "user", "content": user_content}],
    )
    return {"choices": [{"message": {"content": response.content[0].text}}]}


_OCR_SYSTEM_PROMPT = """\
You are a Malaysian receipt digitisation specialist for small F&B businesses.
Your task is to extract structured data from photos of supplier invoices or
purchase receipts. Receipts may be:
  - Handwritten in Malay, English, Chinese, or a mix of all three
  - Poorly lit, slightly blurry, or crumpled
  - Using common Malaysian abbreviations: "kg", "pkt", "btl", "ktn", "dos"
  - Missing total lines or dates (fill with null, do not guess)

Return ONLY valid JSON matching this exact schema:
{
  "supplier_name": string | null,
  "invoice_number": string | null,
  "invoice_date": "YYYY-MM-DD" | null,
  "currency": "MYR",
  "total_amount": number | null,
  "line_items": [
    {
      "product_name_raw": string,
      "quantity": number,
      "unit": string,
      "unit_price": number | null,
      "total_price": number | null,
      "confidence": number
    }
  ],
  "overall_confidence": number,
  "warnings": [string]
}

CRITICAL RULES:
1. Never hallucinate numbers. If a value is unclear, set it to null and add a warning.
2. Do not correct or fix product names — preserve the raw OCR text exactly.
3. If overall_confidence < 0.5, set the first warning to "LOW_CONFIDENCE_NEEDS_REVIEW".
4. If sum(line_items.total_price) differs from total_amount by more than 5%, add warning "TOTAL_MISMATCH".
5. Standardise unit to one of: kg | litre | unit | pack | bottle | carton | gram | box\
"""

_EXPLAIN_SYSTEM_PROMPT = """\
You are Tauke.AI, a trusted business advisor for Malaysian F&B micro-SMEs.
You speak like a knowledgeable friend — mix Malay and English naturally (Manglish is fine).
Your job is to EXPLAIN a pre-computed recommendation in plain language that a mamak
stall owner can understand WITHOUT a finance degree.

You will receive a JSON object with the recommendation's mathematical trace.
Your explanation must:
1. State what to do in ONE clear sentence (the "headline")
2. Explain WHY in 2-3 sentences using the context signals (weather, events, stock level)
3. Show the money impact: "If you do nothing, you risk losing ~RMXX. If you act, you could gain ~RMXX."
4. Give a confidence statement: "Saya yakin XX% sebab..." (I am XX% confident because...)
5. End with a concrete next step: "Recommended: Order XX unit dari supplier sebelum hari Jumaat."

TONE RULES:
- Never be alarmist. Frame as opportunity, not threat.
- If confidence < 0.65, add: "Nota: Data terhad, semak semula sebelum buat keputusan."
- Keep total explanation under 120 words.
- Use MYR for all currency references.

Return ONLY valid JSON:
{
  "headline": string,
  "explanation": string,
  "money_impact": string,
  "confidence_statement": string,
  "next_step": string
}\
"""
