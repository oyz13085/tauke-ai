"""
Push Notification Service — sends Expo push notifications for high-confidence
recommendations (confidence_score >= 0.80).

Uses the Expo push notification HTTP API (no SDK needed).
Failures are silently swallowed so they never break the recommendation pipeline.
"""
from __future__ import annotations

import json
import urllib.request
from typing import Optional

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
_CONFIDENCE_THRESHOLD = 0.80


def send_recommendation_push(
    expo_push_token: Optional[str],
    headline: str,
    confidence: float,
    recommendation_type: str,
) -> None:
    """Send a push notification if token exists and confidence is high enough."""
    if not expo_push_token:
        return
    if confidence < _CONFIDENCE_THRESHOLD:
        return
    if not expo_push_token.startswith("ExponentPushToken["):
        return

    emoji = _type_emoji(recommendation_type)
    body = {
        "to":    expo_push_token,
        "title": f"{emoji} Tauke.AI — Cadangan Baru",
        "body":  headline,
        "data":  {"recommendation_type": recommendation_type},
        "sound": "default",
        "priority": "high",
    }

    try:
        req = urllib.request.Request(
            _EXPO_PUSH_URL,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5):
            pass
    except Exception:
        pass  # Notification failure must never crash the pipeline


def _type_emoji(rec_type: str) -> str:
    return {
        "reorder":          "📦",
        "stockout_warning": "🚨",
        "spoilage_warning": "⏰",
        "price_increase":   "📈",
        "price_decrease":   "📉",
    }.get(rec_type, "💡")
