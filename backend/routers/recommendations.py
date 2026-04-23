import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.recommendation import AIRecommendation
from backend.models.shop import Shop
from backend.schemas.recommendation import FeedbackIn, RecommendationOut

router = APIRouter(tags=["recommendations"])


@router.get("/recommendations", response_model=list[RecommendationOut])
def list_recommendations(
    shop_id: uuid.UUID = Query(..., description="Shop UUID"),
    status:  str       = Query("active", description="Filter by status"),
    limit:   int       = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    shop = db.query(Shop).filter_by(id=shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    recs = (
        db.query(AIRecommendation)
        .filter_by(shop_id=shop_id, status=status)
        .order_by(AIRecommendation.created_at.desc())
        .limit(limit)
        .all()
    )
    return recs


@router.get("/recommendations/{rec_id}", response_model=RecommendationOut)
def get_recommendation(rec_id: uuid.UUID, db: Session = Depends(get_db)):
    rec = db.query(AIRecommendation).filter_by(id=rec_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return rec


@router.patch("/recommendations/{rec_id}/feedback", response_model=RecommendationOut)
def submit_feedback(
    rec_id:   uuid.UUID,
    body:     FeedbackIn,
    db: Session = Depends(get_db),
):
    rec = db.query(AIRecommendation).filter_by(id=rec_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if not (1 <= body.rating <= 5):
        raise HTTPException(status_code=422, detail="Rating must be 1–5")

    rec.feedback_rating = body.rating
    rec.feedback_note   = body.note
    rec.status          = "acted_on"
    db.commit()
    db.refresh(rec)
    return rec


@router.patch("/recommendations/{rec_id}/dismiss", response_model=RecommendationOut)
def dismiss_recommendation(rec_id: uuid.UUID, db: Session = Depends(get_db)):
    rec = db.query(AIRecommendation).filter_by(id=rec_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    rec.status = "dismissed"
    db.commit()
    db.refresh(rec)
    return rec
