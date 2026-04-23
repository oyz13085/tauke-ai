import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.engine.context_fetcher import build_context
from backend.models.shop import Shop

router = APIRouter(tags=["context"])


@router.get("/context/preview")
def context_preview(
    shop_id: uuid.UUID = Query(...),
    db: Session = Depends(get_db),
):
    """Return today's active external signals for a shop (weather, events)."""
    shop = db.query(Shop).filter_by(id=shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    lat = float(shop.location_lat or 3.1390)
    lng = float(shop.location_lng or 101.6869)
    ctx = build_context(db, shop_id, location_lat=lat, location_lng=lng)

    return {
        "date":                 date.today().isoformat(),
        "weather_condition":    ctx.weather_condition,
        "active_events":        ctx.active_events,
        "context_availability": ctx.context_availability,
    }
