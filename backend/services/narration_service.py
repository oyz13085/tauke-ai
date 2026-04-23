"""
Narration Service — wraps GLM explanation over a ReasoningResult.

Math-first: the reasoning engine computes all numbers; this service only
asks GLM to write the Manglish explanation. If GLM fails or times out
(10 s), a template-based fallback is returned so recommendations are
never blocked by an unavailable model.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import re

from backend.engine.reasoning import ReasoningResult

_TIMEOUT_SECONDS = 10.0
_REQUIRED_FIELDS = {"headline", "explanation", "money_impact", "confidence_statement", "next_step"}


def narrate_result(result: ReasoningResult, product_name: str) -> str:
    """
    Returns a JSON string (matching the GLM explanation schema) for the given
    recommendation. Falls back to a template on any failure.
    """
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_call_glm_sync, result, product_name)
            return future.result(timeout=_TIMEOUT_SECONDS)
    except Exception:
        return _template(result, product_name)


# ── Internal helpers ───────────────────────────────────────────────────────────

def _call_glm_sync(result: ReasoningResult, product_name: str) -> str:
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_call_glm(result, product_name))
    finally:
        loop.close()


async def _call_glm(result: ReasoningResult, product_name: str) -> str:
    from backend.services.glm_client import glm_explain

    product_context = {
        "name":             product_name,
        "decision":         result.decision,
        "confidence_pct":   round(result.confidence_final * 100),
        "target_order_qty": result.target_order_qty,
        "target_price":     result.target_price,
    }

    raw  = await glm_explain(result.reasoning_trace, product_context)
    text = raw["choices"][0]["message"]["content"]
    text = _strip_fences(text)

    parsed = json.loads(text)
    if not _REQUIRED_FIELDS.issubset(parsed):
        raise ValueError(f"GLM response missing fields: {_REQUIRED_FIELDS - set(parsed)}")

    return json.dumps(parsed, ensure_ascii=False)


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _template(result: ReasoningResult, product_name: str) -> str:
    """Template fallback — always produces valid Manglish JSON."""
    trace         = result.reasoning_trace
    confidence_pct = round(result.confidence_final * 100)
    signals_raw   = trace.get("context_signals_active", [])
    signals_str   = ", ".join(signals_raw) if signals_raw else "tiada signal khas"
    adj_demand    = trace.get("adjusted_demand_daily", 0.0)

    decision = result.decision

    if decision == "STOCKOUT_WARNING":
        headline     = f"Stok {product_name} hampir habis — order segera!"
        explanation  = (
            f"Stok semasa ({trace.get('usable_stock', 0):.1f} unit) tak cukup untuk "
            f"penghantaran berikutnya. Risiko kehabisan stok adalah tinggi."
        )
        next_step = f"Order {result.target_order_qty:.1f} unit {product_name} dari supplier sekarang."

    elif decision == "REORDER":
        headline    = f"Masa nak restok {product_name}."
        explanation = (
            f"Jangkaan permintaan harian ialah {adj_demand:.1f} unit "
            f"(berdasarkan: {signals_str}). Stok semasa mungkin tak cukup "
            f"lepas lead time {trace.get('lead_time_days', 3)} hari."
        )
        next_step = f"Order {result.target_order_qty:.1f} unit sebelum stok habis."

    elif decision == "PRICE_INCREASE":
        headline    = f"Peluang naikkan harga {product_name}."
        explanation = (
            f"Permintaan tinggi sekarang ({signals_str}). "
            f"Pelanggan boleh terima kenaikan harga kecil dalam keadaan ini."
        )
        next_step = f"Cuba tetapkan harga MYR {result.target_price:.2f} untuk {product_name}."

    elif decision == "PRICE_DECREASE":
        headline    = f"Pertimbangkan turunkan harga {product_name} sikit."
        explanation = (
            f"Permintaan lebih perlahan ({signals_str}). "
            f"Harga yang lebih rendah boleh tarik lebih ramai pelanggan."
        )
        next_step = f"Cuba tetapkan harga MYR {result.target_price:.2f} untuk {product_name}."

    elif decision == "SPOILAGE_WARNING":
        headline    = f"Ada stok {product_name} yang akan tamat tempoh!"
        explanation = (
            "Beberapa batch akan expire dalam masa terdekat. "
            "Elakkan pembaziran dengan jual atau guna dahulu."
        )
        next_step = "Promosi harga atau guna dalam masakan hari ini juga."

    else:
        headline    = f"Tiada cadangan baru untuk {product_name}."
        explanation = "Stok dan harga dalam keadaan baik buat masa ini. Teruskan seperti biasa."
        next_step   = "Semak semula esok atau selepas terima invois baru."

    risk = result.risk_of_inaction_myr
    gain = result.expected_gain_myr
    money_impact = (
        f"Kalau tak buat apa-apa, risiko rugi ~MYR {risk:.2f}. "
        f"Kalau ikut cadangan, boleh untung ~MYR {gain:.2f}."
    )

    disclaimer = (
        " Nota: Data terhad, semak semula sebelum buat keputusan."
        if result.confidence_final < 0.65
        else ""
    )
    confidence_stmt = (
        f"Saya yakin {confidence_pct}% berdasarkan data stok dan signal pasaran.{disclaimer}"
    )

    return json.dumps(
        {
            "headline":             headline,
            "explanation":          explanation,
            "money_impact":         money_impact,
            "confidence_statement": confidence_stmt,
            "next_step":            next_step,
        },
        ensure_ascii=False,
    )
