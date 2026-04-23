import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.shop import Shop
from backend.models.user import User

router = APIRouter(tags=["shops"])


class ShopCreate(BaseModel):
    owner_email: str
    owner_name:  str
    shop_name:   str
    shop_type:   str = "mamak"
    city:        str = "Kuala Lumpur"
    is_halal:    bool = True
    location_lat: Optional[float] = None
    location_lng: Optional[float] = None


class ShopOut(BaseModel):
    id:        uuid.UUID
    owner_id:  uuid.UUID
    name:      str
    shop_type: str
    city:      str
    is_halal:  bool

    model_config = {"from_attributes": True}


@router.post("/shops", response_model=ShopOut, status_code=201)
def create_shop(body: ShopCreate, db: Session = Depends(get_db)):
    # Upsert owner by email
    owner = db.query(User).filter_by(email=body.owner_email).first()
    if not owner:
        owner = User(email=body.owner_email, name=body.owner_name)
        db.add(owner)
        db.flush()

    shop = Shop(
        owner_id=owner.id,
        name=body.shop_name,
        shop_type=body.shop_type,
        city=body.city,
        is_halal=body.is_halal,
        location_lat=body.location_lat,
        location_lng=body.location_lng,
    )
    db.add(shop)
    db.commit()
    db.refresh(shop)
    return shop


@router.get("/shops/{shop_id}", response_model=ShopOut)
def get_shop(shop_id: uuid.UUID, db: Session = Depends(get_db)):
    shop = db.query(Shop).filter_by(id=shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    return shop


@router.patch("/shops/{shop_id}/push-token")
def update_push_token(
    shop_id: uuid.UUID,
    token: str,
    db: Session = Depends(get_db),
):
    shop = db.query(Shop).filter_by(id=shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")
    shop.expo_push_token = token
    db.commit()
    return {"ok": True}
