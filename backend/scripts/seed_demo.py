"""
Demo seed script — creates Warung Pak Lah with realistic mamak inventory.

Usage (with DB running):
    python -m backend.scripts.seed_demo
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta

from backend.database import SessionLocal
from backend.models.user import User
from backend.models.shop import Shop
from backend.models.product import Product
from backend.models.inventory import InventoryItem
from backend.models.recommendation import AIRecommendation


PRODUCTS = [
    dict(name="Teh Tarik",    category="beverage",  unit="kg",     avg_cost_price=6.50, avg_selling_price=2.00, spoilage_days=7,  demand_elasticity=-0.9),
    dict(name="Kopi O",       category="beverage",  unit="kg",     avg_cost_price=18.0, avg_selling_price=2.00, spoilage_days=365, demand_elasticity=-0.8),
    dict(name="Roti Canai",   category="bread",     unit="kg",     avg_cost_price=2.50, avg_selling_price=1.50, spoilage_days=1,  demand_elasticity=-1.3),
    dict(name="Telur",        category="protein",   unit="tray",   avg_cost_price=14.0, avg_selling_price=18.0, spoilage_days=14, demand_elasticity=-0.7),
    dict(name="Susu Segar",   category="beverage",  unit="litre",  avg_cost_price=3.80, avg_selling_price=5.00, spoilage_days=5,  demand_elasticity=-1.0),
    dict(name="Tepung Gandum",category="dry_goods", unit="kg",     avg_cost_price=1.80, avg_selling_price=2.50, spoilage_days=0,  demand_elasticity=-0.5),
    dict(name="Minyak Masak", category="dry_goods", unit="litre",  avg_cost_price=5.50, avg_selling_price=7.00, spoilage_days=0,  demand_elasticity=-0.4),
    dict(name="Beras",        category="dry_goods", unit="kg",     avg_cost_price=2.80, avg_selling_price=3.50, spoilage_days=0,  demand_elasticity=-0.3),
]

INVENTORY = [
    # (product_index, current_qty, days_until_expiry_or_None)
    (0,  3.0,  5),   # Teh Tarik — low stock + soon to expire → generates rec
    (1,  5.0,  None),
    (2,  1.5,  1),   # Roti Canai — about to expire
    (3,  30.0, 12),
    (4,  2.0,  3),   # Susu — very low + expiring soon
    (5,  20.0, None),
    (6,  8.0,  None),
    (7,  15.0, None),
]


def seed() -> dict:
    db = SessionLocal()
    try:
        # 1. Owner + Shop
        owner = db.query(User).filter_by(email="demo@taukeai.my").first()
        if not owner:
            owner = User(email="demo@taukeai.my", name="Pak Lah")
            db.add(owner)
            db.flush()

        shop = db.query(Shop).filter_by(name="Warung Pak Lah").first()
        if not shop:
            shop = Shop(
                owner_id=owner.id,
                name="Warung Pak Lah",
                shop_type="mamak",
                city="Kuala Lumpur",
                location_lat=3.1390,
                location_lng=101.6869,
                is_halal=True,
            )
            db.add(shop)
            db.flush()

        # 2. Products
        products: list[Product] = []
        for p in PRODUCTS:
            existing = db.query(Product).filter_by(shop_id=shop.id, name=p["name"]).first()
            if existing:
                products.append(existing)
                continue
            prod = Product(shop_id=shop.id, **p)
            db.add(prod)
            db.flush()
            products.append(prod)

        # 3. Inventory
        today = date.today()
        for idx, qty, days_left in INVENTORY:
            prod = products[idx]
            batch_ref = f"seed-{prod.id}"
            exists = db.query(InventoryItem).filter_by(
                shop_id=shop.id, product_id=prod.id, batch_ref=batch_ref
            ).first()
            if exists:
                continue
            expiry = today + timedelta(days=days_left) if days_left else None
            db.add(InventoryItem(
                shop_id=shop.id,
                product_id=prod.id,
                batch_ref=batch_ref,
                current_qty=qty,
                unit=prod.unit,
                cost_price=prod.avg_cost_price,
                purchase_date=today - timedelta(days=2),
                expiry_date=expiry,
            ))

        # 4. Seed one demo recommendation for the dashboard
        existing_rec = db.query(AIRecommendation).filter_by(shop_id=shop.id).first()
        if not existing_rec:
            teh_prod = products[0]
            db.add(AIRecommendation(
                shop_id=shop.id,
                product_id=teh_prod.id,
                recommendation_type="reorder",
                recommended_action="Order 15.0 unit untuk restok sebelum kehabisan.",
                target_quantity=15.0,
                confidence_score=0.84,
                risk_of_inaction=47.50,
                expected_gain=62.00,
                reasoning_trace={
                    "base_demand_daily": 2.5,
                    "adjusted_demand_daily": 3.5,
                    "multipliers_applied": {"weather": 1.40, "event": 1.00, "dow": 1.25},
                    "safety_stock": 2.9,
                    "usable_stock": 3.0,
                    "current_stock": 3.0,
                    "spoilage_at_lead_time": 0.0,
                    "target_order_qty": 10.4,
                    "n_data_points": 18,
                    "sigma_daily": 0.42,
                    "demand_cv": 0.12,
                    "p_stockout": 0.72,
                    "confidence_components": {
                        "data_recency": 0.95, "data_volume": 0.88,
                        "ocr_quality": 0.87, "context_availability": 1.0,
                    },
                    "confidence_final": 0.84,
                    "risk_of_inaction_myr": 47.50,
                    "expected_gain_myr": 62.00,
                    "decision": "REORDER",
                    "context_signals_active": ["heavy_rain", "friday"],
                },
                external_factors={"signals": ["heavy_rain", "friday"]},
                glm_explanation='{"headline":"Masa nak order Teh Tarik — stok tinggal 3 kg je!","explanation":"Hujan lebat + hari Jumaat akan naikkan permintaan teh tarik sebanyak 75%. Stok semasa (3 kg) tak cukup untuk penghantaran berikutnya dalam 3 hari.","money_impact":"Kalau tak buat apa-apa, risiko rugi ~MYR 47.50. Kalau order sekarang, boleh untung ~MYR 62.00.","confidence_statement":"Saya yakin 84% berdasarkan 18 invois lepas dan signal cuaca + hari.","next_step":"Order 15 kg Teh Tarik dari pembekal sebelum Jumaat petang."}',
            ))

        db.commit()
        return {"shop_id": str(shop.id), "owner_id": str(owner.id), "products": len(products)}

    except Exception as e:
        db.rollback()
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    result = seed()
    print(f"✅ Demo seeded successfully!")
    print(f"   Shop ID  : {result['shop_id']}")
    print(f"   Owner ID : {result['owner_id']}")
    print(f"   Products : {result['products']}")
    print(f"\n   Use this Shop ID in the mobile app or API calls.")
