"""
Reasoning Engine unit tests.
All DB interactions are mocked — no PostgreSQL required.
Run: pytest backend/tests/test_engine.py -v
"""
import math
import uuid
from datetime import date, timedelta
from unittest.mock import MagicMock

import pytest

from backend.engine.reasoning import (
    ExternalContext,
    compute_confidence,
    dow_multiplier,
    event_multiplier,
    run,
    weather_multiplier,
)

_SHOP_ID    = uuid.uuid4()
_PRODUCT_ID = uuid.uuid4()


# ── test helpers ──────────────────────────────────────────────────────────────

def _make_product(
    category="beverage",
    spoilage_days=3,
    avg_cost_price=4.0,
    avg_selling_price=7.0,
    demand_elasticity=-1.2,
):
    p = MagicMock()
    p.id             = _PRODUCT_ID
    p.shop_id        = _SHOP_ID
    p.category       = category
    p.spoilage_days  = spoilage_days
    p.avg_cost_price = avg_cost_price
    p.avg_selling_price = avg_selling_price
    p.demand_elasticity = demand_elasticity
    return p


def _make_inv(qty: float, days_until_expiry: int | None = None):
    item = MagicMock()
    item.current_qty = qty
    item.expiry_date = (
        date.today() + timedelta(days=days_until_expiry)
        if days_until_expiry is not None
        else None
    )
    return item


def _make_line_item(qty: float):
    li = MagicMock()
    li.quantity = qty
    return li


def _make_invoice(days_ago: int = 1, ocr_confidence: float = 0.9):
    inv = MagicMock()
    inv.invoice_date   = date.today() - timedelta(days=days_ago)
    inv.ocr_confidence = ocr_confidence
    inv.created_at     = date.today() - timedelta(days=days_ago)
    return inv


def _build_db(
    product=None,
    inventory_items=None,
    line_items=None,
    last_invoice=None,
    recent_invoices=None,
):
    """Return a mock SQLAlchemy Session wired for the queries made by run()."""
    from backend.models.product import Product
    from backend.models.inventory import InventoryItem
    from backend.models.invoice import Invoice, InvoiceLineItem

    db = MagicMock()

    def _side_effect(model):
        mock = MagicMock()
        if model is Product:
            mock.filter_by.return_value.first.return_value = product
        elif model is InventoryItem:
            mock.filter_by.return_value.all.return_value = inventory_items or []
        elif model is InvoiceLineItem:
            mock.join.return_value.filter.return_value.all.return_value = line_items or []
        elif model is Invoice:
            # Both invoice queries share the same chain; differ only in terminal call.
            # Chain: .filter(...).order_by(...).first()           → last_invoice
            # Chain: .filter(...).order_by(...).limit(5).all()   → recent_invoices
            mock.filter.return_value.order_by.return_value.first.return_value = last_invoice
            mock.filter.return_value.order_by.return_value.limit.return_value.all.return_value = (
                recent_invoices or []
            )
        return mock

    db.query.side_effect = _side_effect
    return db


# ── multiplier unit tests ─────────────────────────────────────────────────────

def test_weather_multiplier_heavy_rain_beverage():
    assert weather_multiplier("heavy_rain", "beverage") == pytest.approx(1.40)


def test_weather_multiplier_heavy_rain_cold_beverage():
    assert weather_multiplier("heavy_rain", "beverage_cold") == pytest.approx(0.70)


def test_weather_multiplier_hot_sunny_cold_beverage():
    assert weather_multiplier("hot_sunny", "beverage_cold") == pytest.approx(1.55)


def test_weather_multiplier_normal_is_one():
    assert weather_multiplier("normal", "beverage") == pytest.approx(1.00)


def test_event_multiplier_exam_week():
    assert event_multiplier(["um_exam_week"], "beverage") == pytest.approx(0.65)


def test_event_multiplier_no_events_is_one():
    assert event_multiplier([], "beverage") == pytest.approx(1.00)


def test_event_multiplier_dry_goods_hari_raya_override():
    # Dry goods get 2.0 override (not the base 0.20)
    assert event_multiplier(["hari_raya_eve_day1_2"], "dry_goods") == pytest.approx(2.00)


def test_event_multiplier_hari_raya_non_dry_goods():
    # Non-dry-goods gets the regular 0.20 multiplier
    assert event_multiplier(["hari_raya_eve_day1_2"], "beverage") == pytest.approx(0.20)


def test_dow_multiplier_friday():
    assert dow_multiplier(4) == pytest.approx(1.25)


def test_dow_multiplier_monday_baseline():
    assert dow_multiplier(0) == pytest.approx(1.00)


def test_heavy_rain_friday_combined_multiplier():
    """Heavy rain × Friday DOW = 1.40 × 1.25 = 1.75 for hot beverages."""
    w = weather_multiplier("heavy_rain", "beverage")
    d = dow_multiplier(4)   # Friday
    assert w * d == pytest.approx(1.75)


# ── confidence unit tests ─────────────────────────────────────────────────────

def test_confidence_low_with_sparse_data():
    """3 data points, 14 days stale → confidence ≤ 0.65."""
    c = compute_confidence(
        days_since_invoice=14,
        n_data_points=3,
        avg_ocr_quality=0.85,
        context_availability=1.0,
        demand_cv=0.1,
    )
    assert c <= 0.65


def test_confidence_high_with_good_data():
    """20 data points, 1 day stale → confidence ≥ 0.80."""
    c = compute_confidence(
        days_since_invoice=1,
        n_data_points=20,
        avg_ocr_quality=0.90,
        context_availability=1.0,
        demand_cv=0.1,
    )
    assert c >= 0.80


def test_confidence_no_data_is_zero():
    """Zero data points → data_volume_score = 0 → geometric mean = 0."""
    c = compute_confidence(
        days_since_invoice=999,
        n_data_points=0,
        avg_ocr_quality=0.90,
        context_availability=1.0,
        demand_cv=0.0,
    )
    assert c == pytest.approx(0.0)


def test_confidence_entropy_penalty_applied():
    """High demand CV (> 0.5) reduces confidence by 0.85× multiplier."""
    c_low_cv  = compute_confidence(1, 20, 0.90, 1.0, demand_cv=0.1)
    c_high_cv = compute_confidence(1, 20, 0.90, 1.0, demand_cv=0.9)
    assert c_high_cv == pytest.approx(c_low_cv * 0.85, rel=1e-3)


# ── run() integration tests (mocked DB) ──────────────────────────────────────

def test_run_returns_none_when_product_missing():
    db = _build_db(product=None)
    result = run(db, _SHOP_ID, _PRODUCT_ID, ExternalContext())
    assert result is None


def test_run_zero_stock_stockout_warning():
    """usable_stock = 0 → STOCKOUT_WARNING, p_stockout near 1."""
    product = _make_product(avg_selling_price=8.0)
    line_items = [_make_line_item(10.0) for _ in range(10)]
    db = _build_db(
        product=product,
        inventory_items=[],
        line_items=line_items,
        last_invoice=_make_invoice(days_ago=1),
        recent_invoices=[_make_invoice() for _ in range(5)],
    )

    result = run(db, _SHOP_ID, _PRODUCT_ID, ExternalContext(days_to_next_restock=7))

    assert result is not None
    assert result.decision == "STOCKOUT_WARNING"
    assert result.reasoning_trace["p_stockout"] > 0.95
    assert result.reasoning_trace["usable_stock"] == pytest.approx(0.0)


def test_run_near_expiry_reduces_usable_stock():
    """Batch expiring within lead_time_days is excluded from usable_stock."""
    product    = _make_product(spoilage_days=3, avg_selling_price=8.0)
    inventory  = [
        _make_inv(15.0, days_until_expiry=10),   # safe batch
        _make_inv(5.0,  days_until_expiry=2),    # expires before lead-time cutoff
    ]
    line_items = [_make_line_item(10.0) for _ in range(10)]
    db = _build_db(
        product=product,
        inventory_items=inventory,
        line_items=line_items,
        last_invoice=_make_invoice(days_ago=1),
        recent_invoices=[_make_invoice() for _ in range(5)],
    )

    result = run(db, _SHOP_ID, _PRODUCT_ID, ExternalContext(lead_time_days=3))

    assert result is not None
    trace = result.reasoning_trace
    assert trace["current_stock"]        == pytest.approx(20.0)
    assert trace["spoilage_at_lead_time"] == pytest.approx(5.0)
    assert trace["usable_stock"]          == pytest.approx(15.0)


def test_run_exam_week_reduces_adjusted_demand():
    """UM exam-week event multiplier 0.65 → lower adjusted demand than baseline."""
    product    = _make_product(avg_selling_price=8.0)
    inventory  = [_make_inv(2.0)]
    line_items = [_make_line_item(10.0) for _ in range(20)]

    def _db():
        return _build_db(
            product=product,
            inventory_items=inventory,
            line_items=line_items,
            last_invoice=_make_invoice(days_ago=1),
            recent_invoices=[_make_invoice() for _ in range(5)],
        )

    result_normal = run(_db(), _SHOP_ID, _PRODUCT_ID, ExternalContext(active_events=[]))
    result_exam   = run(_db(), _SHOP_ID, _PRODUCT_ID, ExternalContext(active_events=["um_exam_week"]))

    assert result_normal is not None and result_exam is not None
    # Both runs use the same DOW and weather multipliers (same date.today())
    assert result_exam.reasoning_trace["adjusted_demand_daily"] < result_normal.reasoning_trace["adjusted_demand_daily"]
    assert result_exam.target_order_qty <= result_normal.target_order_qty


def test_run_no_history_uses_default_sigma():
    """No purchase history → n_data_points=0, σ = 0.15 × 1.0 (base demand fallback)."""
    product = _make_product(avg_selling_price=8.0)
    db = _build_db(
        product=product,
        inventory_items=[],
        line_items=[],          # no history
        last_invoice=None,
        recent_invoices=[],
    )

    result = run(db, _SHOP_ID, _PRODUCT_ID, ExternalContext())

    assert result is not None
    assert result.reasoning_trace["n_data_points"] == 0
    assert result.reasoning_trace["sigma_daily"]   == pytest.approx(0.15, abs=0.01)
    assert result.confidence_final <= 0.65          # no data → low confidence


def test_run_heavy_rain_applies_correct_weather_multiplier():
    """Heavy rain → weather multiplier 1.40 for beverage category."""
    product    = _make_product(category="beverage", avg_selling_price=8.0)
    line_items = [_make_line_item(10.0) for _ in range(20)]
    db = _build_db(
        product=product,
        inventory_items=[_make_inv(100.0)],
        line_items=line_items,
        last_invoice=_make_invoice(days_ago=1),
        recent_invoices=[_make_invoice() for _ in range(5)],
    )

    result = run(db, _SHOP_ID, _PRODUCT_ID, ExternalContext(weather_condition="heavy_rain"))

    assert result is not None
    assert result.reasoning_trace["multipliers_applied"]["weather"] == pytest.approx(1.40)
    assert result.reasoning_trace["adjusted_demand_daily"] > result.reasoning_trace["base_demand_daily"]


def test_run_spoilage_warning_when_near_expiry_with_stock():
    """Batches expiring within 2× lead_time with positive stock → SPOILAGE_WARNING."""
    product   = _make_product(avg_selling_price=8.0)
    inventory = [_make_inv(20.0, days_until_expiry=5)]   # expires in 5 days, lead_time=3 → 2×=6
    db = _build_db(
        product=product,
        inventory_items=inventory,
        line_items=[_make_line_item(10.0) for _ in range(10)],
        last_invoice=_make_invoice(days_ago=1),
        recent_invoices=[_make_invoice() for _ in range(5)],
    )

    result = run(db, _SHOP_ID, _PRODUCT_ID, ExternalContext(lead_time_days=3))

    assert result is not None
    assert result.decision == "SPOILAGE_WARNING"
