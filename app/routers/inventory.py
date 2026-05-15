from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from ..db import get_db
from ..models import InventoryAdjust, InventoryItem, InventoryUpdate

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


def _clean(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


@router.get("")
def list_inventory() -> dict:
    items = [_clean(d) for d in get_db().inventory.find({})]
    return {"items": items}


@router.get("/{item_id}")
def get_item(item_id: str) -> dict:
    doc = get_db().inventory.find_one({"id": item_id})
    if not doc:
        raise HTTPException(404, "Inventory item not found")
    return _clean(doc)


@router.post("", status_code=201)
def create_item(body: InventoryItem) -> dict:
    db = get_db()
    if db.inventory.find_one({"id": body.id}):
        raise HTTPException(409, "Inventory item already exists")
    db.inventory.insert_one(body.model_dump())
    return body.model_dump()


@router.put("/{item_id}")
def update_item(item_id: str, body: InventoryUpdate) -> dict:
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    updates["updated"] = datetime.now(timezone.utc)
    db = get_db()
    res = db.inventory.update_one({"id": item_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Inventory item not found")
    return _clean(db.inventory.find_one({"id": item_id}))


@router.post("/{item_id}/adjust")
def adjust_stock(item_id: str, body: InventoryAdjust) -> dict:
    db = get_db()
    doc = db.inventory.find_one({"id": item_id})
    if not doc:
        raise HTTPException(404, "Inventory item not found")
    new_stock = max(0, doc.get("stock", 0) + body.delta)
    db.inventory.update_one(
        {"id": item_id},
        {"$set": {"stock": new_stock, "updated": datetime.now(timezone.utc)}},
    )
    return _clean(db.inventory.find_one({"id": item_id}))


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: str) -> None:
    res = get_db().inventory.delete_one({"id": item_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Inventory item not found")
