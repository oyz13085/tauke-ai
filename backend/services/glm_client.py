import base64
import httpx
from pathlib import Path
from backend.config import settings

_HEADERS = {"Authorization": f"Bearer {settings.glm_api_key}", "Content-Type": "application/json"}
_TIMEOUT = 30.0


async def glm_ocr(image_path: str) -> dict:
    """Send an image to GLM-4V for receipt OCR. Returns raw JSON dict from the model."""
    image_data = base64.b64encode(Path(image_path).read_bytes()).decode()
    ext = Path(image_path).suffix.lstrip(".").lower()
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"

    payload = {
        "model": "glm-4v",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{image_data}"},
                    },
                    {
                        "type": "text",
                        "text": "Please extract the receipt data from this supplier invoice.",
                    },
                ],
            }
        ],
        "system": _OCR_SYSTEM_PROMPT,
        "temperature": 0.1,  # low temp for deterministic extraction
    }

    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        resp = await client.post(
            f"{settings.glm_base_url}/chat/completions",
            headers=_HEADERS,
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


async def glm_explain(reasoning_trace: dict, product_context: dict) -> dict:
    """Send a reasoning trace to GLM-4 for Manglish explanation. Returns parsed JSON dict."""
    import json

    user_content = json.dumps(
        {"reasoning_trace": reasoning_trace, "product": product_context}, ensure_ascii=False
    )

    payload = {
        "model": "glm-4",
        "messages": [{"role": "user", "content": user_content}],
        "system": _EXPLAIN_SYSTEM_PROMPT,
        "temperature": 0.5,
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{settings.glm_base_url}/chat/completions",
            headers=_HEADERS,
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()


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
