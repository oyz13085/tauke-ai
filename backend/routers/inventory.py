import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.inventory import InventoryItem
from backend.models.shop import Shop
from backend.schemas.inventory import InventoryItemOut

router = APIRouter(tags=["inventory"])


@router.get("/inventory", response_model=list[InventoryItemOut])
def list_inventory(
    shop_id:     uuid.UUID = Query(...),
    include_depleted: bool = Query(False),
    db: Session = Depends(get_db),
):
    shop = db.query(Shop).filter_by(id=shop_id).first()
    if not shop:
        raise HTTPException(status_code=404, detail="Shop not found")

    q = db.query(InventoryItem).filter_by(shop_id=shop_id)
    if not include_depleted:
        q = q.filter_by(is_depleted=False)

    return q.order_by(InventoryItem.expiry_date.asc().nullslast()).all()


@router.patch("/inventory/{item_id}", response_model=InventoryItemOut)
def adjust_inventory(
    item_id:    uuid.UUID,
    qty_delta:  float,
    db: Session = Depends(get_db),
):
    item = db.query(InventoryItem).filter_by(id=item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="Inventory item not found")

    new_qty = float(item.current_qty) + qty_delta
    if new_qty < 0:
        raise HTTPException(status_code=422, detail="Adjustment would make quantity negative")

    item.current_qty = new_qty
    if new_qty == 0:
        item.is_depleted = True

    db.commit()
    db.refresh(item)
    return item
