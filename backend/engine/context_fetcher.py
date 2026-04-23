"""
Context Fetcher — collects external demand signals for the Reasoning Engine.

Signals fetched:
  1. Weather   — OpenWeatherMap current conditions for KL (or shop coordinates)
  2. Holidays  — Malaysia public holidays (static JSON, authoritative for demo)
  3. UM Events — University of Malaya academic calendar (static JSON)

All results are cached in external_context_cache with a 6-hour TTL.
If any fetch fails, that signal is skipped (context_availability decremented).
"""
from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from backend.engine.reasoning import ExternalContext
from backend.models.context_cache import ExternalContextCache

_CACHE_TTL_HOURS = 6

# ── Static data paths ─────────────────────────────────────────────────────────
_DATA_DIR = Path(__file__).parent.parent / "data"

# ── OpenWeatherMap condition → our weather_condition key ──────────────────────
_OWM_CONDITION_MAP = {
    "thunderstorm": "heavy_rain",
    "drizzle":      "heavy_rain",
    "rain":         "heavy_rain",
    "snow":         "normal",       # won't happen in KL
    "clear":        "hot_sunny",
    "clouds":       "normal",
    "mist":         "normal",
    "haze":         "normal",
    "fog":          "normal",
}


def build_context(
    db: Session,
    shop_id: uuid.UUID,
    target_date: Optional[date] = None,
    location_lat: float = 3.1390,    # KL default
    location_lng: float = 101.6869,
) -> ExternalContext:
    """
    Build an ExternalContext by combining cached + fresh external signals.
    Returns a default context if all fetches fail (context_availability=0).
    """
    today = target_date or date.today()
    signals_attempted = 3   # weather + holidays + um_calendar
    signals_ok        = 0

    weather_condition = "normal"
    active_events: list[str] = []

    # 1. Weather
    try:
        weather_condition = _get_weather(db, shop_id, today, location_lat, location_lng)
        signals_ok += 1
    except Exception:
        pass

    # 2. Public holidays
    try:
        is_holiday = _get_holiday(db, shop_id, today)
        if is_holiday:
            active_events.append("public_holiday")
        signals_ok += 1
    except Exception:
        pass

    # 3. UM academic calendar
    try:
        um_events = _get_um_events(db, shop_id, today)
        active_events.extend(um_events)
        signals_ok += 1
    except Exception:
        pass

    context_availability = signals_ok / signals_attempted

    return ExternalContext(
        weather_condition=weather_condition,
        active_events=active_events,
        context_availability=context_availability,
    )


# ── Weather ───────────────────────────────────────────────────────────────────

def _get_weather(
    db: Session,
    shop_id: uuid.UUID,
    today: date,
    lat: float,
    lng: float,
) -> str:
    cached = _cache_get(db, shop_id, "weather", today)
    if cached:
        return cached.get("condition", "normal")

    condition = _fetch_owm(lat, lng)
    _cache_set(db, shop_id, "weather", today, {"condition": condition})
    return condition


def _fetch_owm(lat: float, lng: float) -> str:
    """Hit OpenWeatherMap current-weather endpoint. Returns our condition key."""
    from backend.config import settings
    import urllib.request

    if not settings.openweather_api_key:
        return "normal"

    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?lat={lat}&lon={lng}&appid={settings.openweather_api_key}&units=metric"
    )
    with urllib.request.urlopen(url, timeout=5) as resp:
        data = json.loads(resp.read())

    main_group = data["weather"][0]["main"].lower()
    return _OWM_CONDITION_MAP.get(main_group, "normal")


# ── Public holidays ───────────────────────────────────────────────────────────

def _get_holiday(db: Session, shop_id: uuid.UUID, today: date) -> bool:
    cached = _cache_get(db, shop_id, "public_holiday", today)
    if cached is not None:
        return cached.get("is_holiday", False)

    is_holiday, events = _load_holiday_data(today)
    _cache_set(
        db, shop_id, "public_holiday", today,
        {"is_holiday": is_holiday, "events": events},
    )
    return is_holiday


def _load_holiday_data(today: date) -> tuple[bool, list[str]]:
    """Load from static JSON; return (is_holiday, list_of_event_keys)."""
    path = _DATA_DIR / "malaysia_holidays.json"
    if not path.exists():
        return False, []

    holidays: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    today_str = today.isoformat()

    for h in holidays:
        if h.get("date") == today_str:
            event_key = h.get("event_key", "public_holiday")
            return True, [event_key]

    return False, []


# ── UM academic calendar ──────────────────────────────────────────────────────

def _get_um_events(db: Session, shop_id: uuid.UUID, today: date) -> list[str]:
    cached = _cache_get(db, shop_id, "um_calendar", today)
    if cached is not None:
        return cached.get("events", [])

    events = _load_um_events(today)
    _cache_set(db, shop_id, "um_calendar", today, {"events": events})
    return events


def _load_um_events(today: date) -> list[str]:
    """Load from static JSON; return list of active UM event keys for today."""
    path = _DATA_DIR / "um_calendar.json"
    if not path.exists():
        return []

    calendar: list[dict] = json.loads(path.read_text(encoding="utf-8"))
    today_str = today.isoformat()
    active = []

    for entry in calendar:
        start = entry.get("start")
        end   = entry.get("end")
        key   = entry.get("event_key")
        if start and end and key and start <= today_str <= end:
            active.append(key)

    return active


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_get(
    db: Session,
    shop_id: uuid.UUID,
    context_type: str,
    context_date: date,
) -> Optional[dict]:
    """Return cached data if it exists and hasn't expired."""
    row: Optional[ExternalContextCache] = (
        db.query(ExternalContextCache)
        .filter_by(shop_id=shop_id, context_type=context_type, context_date=context_date)
        .first()
    )
    if not row:
        return None
    if row.expires_at and row.expires_at < datetime.now(timezone.utc):
        return None
    return row.data_json


def _cache_set(
    db: Session,
    shop_id: uuid.UUID,
    context_type: str,
    context_date: date,
    data: dict,
) -> None:
    """Upsert a cache row with a 6-hour TTL."""
    expires = datetime.now(timezone.utc) + timedelta(hours=_CACHE_TTL_HOURS)
    existing = (
        db.query(ExternalContextCache)
        .filter_by(shop_id=shop_id, context_type=context_type, context_date=context_date)
        .first()
    )
    if existing:
        existing.data_json  = data
        existing.expires_at = expires
        existing.fetched_at = datetime.now(timezone.utc)
    else:
        db.add(ExternalContextCache(
            shop_id=shop_id,
            context_type=context_type,
            context_date=context_date,
            data_json=data,
            expires_at=expires,
        ))
    try:
        db.commit()
    except Exception:
        db.rollback()
