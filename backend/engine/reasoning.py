"""
Reasoning Engine — pure-math Decision Intelligence module.

Stateless and deterministic: accepts pre-queried DB data plus an ExternalContext,
returns a ReasoningResult with a full numeric trace.

GLM is NOT called here. Step 5 overlays a Manglish explanation on the trace.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import mean, stdev
from typing import Optional

from sqlalchemy.orm import Session

from backend.engine.multipliers import (
    CAT_DRY,
    CATEGORY_MAP,
    DOW_MULTIPLIERS,
    EVENT_DRY_GOODS_OVERRIDES,
    EVENT_MULTIPLIERS,
    WEATHER_MULTIPLIERS,
)
from backend.models.inventory import InventoryItem
from backend.models.invoice import Invoice, InvoiceLineItem
from backend.models.product import Product
from backend.models.recommendation import AIRecommendation

_MYR_MIN_THRESHOLD = 5.00   # Minimum MYR impact to surface a recommendation
_LAMBDA             = 0.05  # Recency decay constant (half-life ≈ 14 days)
_Z_PERISHABLE       = 1.65  # 95% service level for fresh goods
_Z_DRY_GOODS        = 1.28  # 90% service level for shelf-stable goods


# ── Public data classes ────────────────────────────────────────────────────────

@dataclass
class ExternalContext:
    weather_condition: str       = "normal"                   # normal | heavy_rain | hot_sunny
    active_events: list[str]     = field(default_factory=list) # e.g. ["um_exam_week"]
    context_availability: float  = 1.0                        # fraction of signals fetched
    lead_time_days: int          = 3                          # order-to-delivery window
    days_to_next_restock: int    = 7                          # days until next reorder window
    target_price_premium: float  = 0.0                        # optional price change to evaluate


@dataclass
class ReasoningResult:
    product_id:           uuid.UUID
    shop_id:              uuid.UUID
    decision:             str            # REORDER | STOCKOUT_WARNING | SPOILAGE_WARNING | PRICE_INCREASE | NO_ACTION
    target_order_qty:     float
    target_price:         Optional[float]
    confidence_final:     float
    risk_of_inaction_myr: float
    expected_gain_myr:    float
    reasoning_trace:      dict
    context_signals_active: list[str]
    should_recommend:     bool


# ── Public helper functions (tested directly) ──────────────────────────────────

def weather_multiplier(condition: str, category: str) -> float:
    """Demand multiplier for a given weather condition and product category."""
    cat = CATEGORY_MAP.get(category.lower(), "beverage_hot")
    table = WEATHER_MULTIPLIERS.get(condition, WEATHER_MULTIPLIERS["normal"])
    return table[cat]


def event_multiplier(active_events: list[str], category: str) -> float:
    """Product of all active-event multipliers; dry-goods overrides applied."""
    cat = CATEGORY_MAP.get(category.lower(), "beverage_hot")
    multiplier = 1.0
    for event in active_events:
        if cat == CAT_DRY and event in EVENT_DRY_GOODS_OVERRIDES:
            multiplier *= EVENT_DRY_GOODS_OVERRIDES[event]
        elif event in EVENT_MULTIPLIERS:
            multiplier *= EVENT_MULTIPLIERS[event]
    return multiplier


def dow_multiplier(weekday: int) -> float:
    """Day-of-week demand multiplier (Monday=0, Sunday=6)."""
    return DOW_MULTIPLIERS.get(weekday, 1.00)


def compute_confidence(
    days_since_invoice: int,
    n_data_points: int,
    avg_ocr_quality: float,
    context_availability: float,
    demand_cv: float,
) -> float:
    """
    Geometric mean of four scored components; 0.85 entropy penalty when
    demand coefficient-of-variation exceeds 0.5 (high-variance = uncertain).
    """
    recency = math.exp(-_LAMBDA * days_since_invoice)
    volume  = min(1.0, math.log(1 + n_data_points) / math.log(31))
    ocr     = max(0.0, min(1.0, avg_ocr_quality))
    ctx     = max(0.0, min(1.0, context_availability))

    confidence = _geometric_mean([recency, volume, ocr, ctx])

    if demand_cv > 0.5:
        confidence *= 0.85

    return round(confidence, 4)


# ── Engine entry points ────────────────────────────────────────────────────────

def run(
    db: Session,
    shop_id: uuid.UUID,
    product_id: uuid.UUID,
    context: ExternalContext,
) -> Optional[ReasoningResult]:
    """Full reasoning pipeline for one product. Returns None if product not found."""

    # 1. Load product
    product: Optional[Product] = (
        db.query(Product).filter_by(id=product_id, shop_id=shop_id).first()
    )
    if not product:
        return None

    today    = date.today()
    category = product.category or "beverage"

    # 2. Live inventory (non-depleted batches)
    inventory: list[InventoryItem] = (
        db.query(InventoryItem)
        .filter_by(shop_id=shop_id, product_id=product_id, is_depleted=False)
        .all()
    )
    current_stock = sum(float(i.current_qty) for i in inventory)
    expiry_cutoff = today + timedelta(days=context.lead_time_days)
    spoilage_qty  = sum(
        float(i.current_qty)
        for i in inventory
        if i.expiry_date and i.expiry_date <= expiry_cutoff
    )
    usable_stock = max(0.0, current_stock - spoilage_qty)

    # 3. Purchase history (last 30 days) — proxy for consumption
    thirty_days_ago = today - timedelta(days=30)
    recent_items: list[InvoiceLineItem] = (
        db.query(InvoiceLineItem)
        .join(Invoice, Invoice.id == InvoiceLineItem.invoice_id)
        .filter(
            InvoiceLineItem.matched_product_id == product_id,
            Invoice.shop_id == shop_id,
            Invoice.invoice_date >= thirty_days_ago,
            Invoice.processing_status == "done",
        )
        .all()
    )
    quantities    = [float(item.quantity) for item in recent_items]
    n_data_points = len(quantities)
    total_30d     = sum(quantities)
    base_demand_daily = total_30d / 30.0 if quantities else 1.0

    # σ_demand (daily variability); fallback when < 7 observations
    if n_data_points >= 7:
        try:
            sigma = max(stdev(quantities) / max(context.lead_time_days, 1), 0.01)
        except Exception:
            sigma = 0.15 * base_demand_daily
    else:
        sigma = 0.15 * base_demand_daily

    demand_cv = sigma / base_demand_daily if base_demand_daily > 0 else 0.0

    # 4. Recency: days since last completed invoice
    last_invoice: Optional[Invoice] = (
        db.query(Invoice)
        .filter(Invoice.shop_id == shop_id, Invoice.processing_status == "done")
        .order_by(Invoice.invoice_date.desc())
        .first()
    )
    days_since_invoice = (
        (today - last_invoice.invoice_date).days
        if last_invoice and last_invoice.invoice_date
        else 999
    )

    # 5. OCR quality: mean confidence of last 5 invoices
    last_5: list[Invoice] = (
        db.query(Invoice)
        .filter(Invoice.shop_id == shop_id, Invoice.ocr_confidence.isnot(None))
        .order_by(Invoice.created_at.desc())
        .limit(5)
        .all()
    )
    avg_ocr_quality = (
        mean([float(i.ocr_confidence) for i in last_5]) if last_5 else 1.0
    )

    # 6. Demand adjustment
    w_mult         = weather_multiplier(context.weather_condition, category)
    e_mult         = event_multiplier(context.active_events, category)
    d_mult         = dow_multiplier(today.weekday())
    adjusted_demand = base_demand_daily * w_mult * e_mult * d_mult

    signals_active     = _build_signals(context)
    multipliers_applied = {"weather": w_mult, "event": e_mult, "dow": d_mult}

    # 7. Safety stock + target order quantity
    is_perishable = bool(product.spoilage_days and product.spoilage_days > 0)
    z_score       = _Z_PERISHABLE if is_perishable else _Z_DRY_GOODS
    safety_stock  = z_score * sigma * math.sqrt(context.lead_time_days)
    demand_lead   = adjusted_demand * context.lead_time_days
    target_order_qty = max(0.0, demand_lead + safety_stock - usable_stock)

    # 8. Confidence score
    confidence = compute_confidence(
        days_since_invoice, n_data_points, avg_ocr_quality,
        context.context_availability, demand_cv,
    )

    # 9. Risk of inaction (stockout scenario)
    avg_selling_price = float(product.avg_selling_price or 0.0)
    risk_myr, p_stockout = _risk_of_inaction(
        usable_stock, adjusted_demand, context.days_to_next_restock,
        sigma, avg_selling_price,
    )

    # 10. Expected gain from pricing opportunity
    avg_cost_price = float(product.avg_cost_price or 0.0)
    elasticity     = float(product.demand_elasticity or -1.2)
    current_price  = avg_selling_price
    target_price: Optional[float] = None
    expected_gain  = 0.0

    if context.target_price_premium != 0.0 and current_price > 0:
        target_price = current_price * (1 + context.target_price_premium)
        expected_gain = _expected_gain(
            base_demand_daily, current_price, target_price, elasticity,
            ordering_cost=2.0,
            order_qty=target_order_qty,
            unit_cost=avg_cost_price,
            lead_time_days=context.lead_time_days,
        )

    # 11. Decision
    decision = _decide(
        usable_stock, risk_myr, expected_gain, target_price,
        current_price, target_order_qty, inventory, context.lead_time_days, today,
    )

    should_recommend = (
        (expected_gain > _MYR_MIN_THRESHOLD or risk_myr > _MYR_MIN_THRESHOLD)
        and confidence >= 0.60
    )

    reasoning_trace = {
        "base_demand_daily":    round(base_demand_daily, 3),
        "adjusted_demand_daily": round(adjusted_demand, 3),
        "multipliers_applied":  multipliers_applied,
        "safety_stock":         round(safety_stock, 3),
        "usable_stock":         round(usable_stock, 3),
        "current_stock":        round(current_stock, 3),
        "spoilage_at_lead_time": round(spoilage_qty, 3),
        "target_order_qty":     round(target_order_qty, 3),
        "n_data_points":        n_data_points,
        "sigma_daily":          round(sigma, 4),
        "demand_cv":            round(demand_cv, 4),
        "p_stockout":           round(p_stockout, 4),
        "confidence_components": {
            "data_recency":       round(math.exp(-_LAMBDA * days_since_invoice), 4),
            "data_volume":        round(min(1.0, math.log(1 + n_data_points) / math.log(31)), 4),
            "ocr_quality":        round(avg_ocr_quality, 4),
            "context_availability": round(context.context_availability, 4),
        },
        "confidence_final":       round(confidence, 4),
        "risk_of_inaction_myr":   round(risk_myr, 2),
        "expected_gain_myr":      round(expected_gain, 2),
        "decision":               decision,
        "context_signals_active": signals_active,
    }

    return ReasoningResult(
        product_id=product_id,
        shop_id=shop_id,
        decision=decision,
        target_order_qty=round(target_order_qty, 2),
        target_price=round(target_price, 2) if target_price else None,
        confidence_final=round(confidence, 4),
        risk_of_inaction_myr=round(risk_myr, 2),
        expected_gain_myr=round(expected_gain, 2),
        reasoning_trace=reasoning_trace,
        context_signals_active=signals_active,
        should_recommend=should_recommend,
    )


def run_for_shop(
    db: Session,
    shop_id: uuid.UUID,
    context: Optional[ExternalContext] = None,
    with_narration: bool = True,
) -> list[ReasoningResult]:
    """Run the engine for every product in the shop; persist actionable recs."""
    ctx = context or ExternalContext()
    products: list[Product] = db.query(Product).filter_by(shop_id=shop_id).all()
    results: list[ReasoningResult] = []

    narrator = None
    if with_narration:
        try:
            from backend.services.narration_service import narrate_result
            narrator = narrate_result
        except Exception:
            pass

    for product in products:
        result = run(db, shop_id, product.id, ctx)
        if result and result.should_recommend:
            explanation: Optional[str] = None
            if narrator:
                try:
                    explanation = narrator(result, product.name)
                except Exception:
                    pass
            _persist_recommendation(db, result, glm_explanation=explanation)
            results.append(result)

    if results:
        db.commit()

    return results


# ── Private helpers ────────────────────────────────────────────────────────────

def _geometric_mean(values: list[float]) -> float:
    if not values or any(v <= 0 for v in values):
        return 0.0
    return math.exp(sum(math.log(v) for v in values) / len(values))


def _norm_cdf(x: float) -> float:
    """Standard normal CDF via math.erfc — no scipy dependency."""
    return 0.5 * math.erfc(-x / math.sqrt(2))


def _risk_of_inaction(
    usable_stock: float,
    adjusted_demand: float,
    days_to_restock: int,
    sigma: float,
    avg_selling_price: float,
) -> tuple[float, float]:
    """Returns (risk_myr, p_stockout)."""
    if avg_selling_price <= 0:
        return 0.0, 0.0
    if sigma > 0:
        z = (usable_stock - adjusted_demand * days_to_restock) / sigma
    else:
        z = float("inf") if usable_stock >= adjusted_demand * days_to_restock else float("-inf")
    p_stockout = 1.0 - _norm_cdf(z)
    lost_rev   = adjusted_demand * avg_selling_price
    churn      = lost_rev * 0.15
    risk_myr   = p_stockout * (lost_rev * days_to_restock + churn)
    return risk_myr, p_stockout


def _expected_gain(
    base_demand: float,
    current_price: float,
    target_price: float,
    elasticity: float,
    ordering_cost: float,
    order_qty: float,
    unit_cost: float,
    lead_time_days: int,
) -> float:
    """Arc-elasticity pricing model."""
    if current_price <= 0:
        return 0.0
    delta          = target_price - current_price
    demand_new     = max(0.0, base_demand * (1 + elasticity * (delta / current_price)))
    revenue_new    = demand_new * target_price
    revenue_old    = base_demand * current_price
    order_cost_amt = ordering_cost / max(order_qty, 1)
    holding_cost   = order_qty * unit_cost * 0.02 * lead_time_days
    return revenue_new - revenue_old - order_cost_amt - holding_cost


def _decide(
    usable_stock: float,
    risk_myr: float,
    expected_gain: float,
    target_price: Optional[float],
    current_price: float,
    target_order_qty: float,
    inventory: list[InventoryItem],
    lead_time_days: int,
    today: date,
) -> str:
    near_expiry = [
        i for i in inventory
        if i.expiry_date and i.expiry_date <= today + timedelta(days=lead_time_days * 2)
    ]
    if near_expiry and usable_stock > 0:
        return "SPOILAGE_WARNING"
    if usable_stock <= 0:
        return "STOCKOUT_WARNING"
    if target_price and current_price > 0 and expected_gain > _MYR_MIN_THRESHOLD:
        return "PRICE_INCREASE" if target_price > current_price else "PRICE_DECREASE"
    if target_order_qty > 0 and risk_myr > _MYR_MIN_THRESHOLD:
        return "REORDER"
    return "NO_ACTION"


def _build_signals(context: ExternalContext) -> list[str]:
    signals = [context.weather_condition] if context.weather_condition != "normal" else []
    signals.extend(context.active_events)
    return signals


def _persist_recommendation(
    db: Session,
    result: ReasoningResult,
    glm_explanation: Optional[str] = None,
) -> None:
    from datetime import datetime, timezone
    from datetime import timedelta as td
    rec = AIRecommendation(
        shop_id=result.shop_id,
        product_id=result.product_id,
        recommendation_type=result.decision.lower(),
        recommended_action=_action_text(result),
        target_quantity=(
            result.target_order_qty
            if result.decision in ("REORDER", "STOCKOUT_WARNING")
            else None
        ),
        target_price=result.target_price,
        confidence_score=result.confidence_final,
        risk_of_inaction=result.risk_of_inaction_myr,
        expected_gain=result.expected_gain_myr,
        reasoning_trace=result.reasoning_trace,
        external_factors={"signals": result.context_signals_active},
        glm_explanation=glm_explanation,
        expires_at=datetime.now(timezone.utc) + td(days=2),
    )
    db.add(rec)


def _action_text(result: ReasoningResult) -> str:
    if result.decision == "STOCKOUT_WARNING":
        return f"Stock habis! Order {result.target_order_qty:.1f} unit segera."
    if result.decision == "REORDER":
        return f"Order {result.target_order_qty:.1f} unit untuk restok sebelum kehabisan."
    if result.decision == "PRICE_INCREASE":
        return f"Naikkan harga ke MYR {result.target_price:.2f} untuk tingkatkan pendapatan."
    if result.decision == "PRICE_DECREASE":
        return f"Turunkan harga ke MYR {result.target_price:.2f} untuk tarik lebih ramai pelanggan."
    if result.decision == "SPOILAGE_WARNING":
        return "Ada stok yang akan tamat tempoh dalam masa terdekat — jual atau guna dahulu."
    return "Tiada cadangan baru buat masa ini."
