from fastapi import APIRouter, HTTPException, Query

from ..db import get_db
from ..models import MenuItem, MenuItemUpdate

router = APIRouter(prefix="/api/menu", tags=["menu"])


def _clean(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


@router.get("")
def list_menu(category: str | None = Query(None)) -> dict:
    db = get_db()
    q: dict = {}
    if category:
        q["category"] = category
    items = [_clean(d) for d in db.menu.find(q)]
    meta = db.meta.find_one({"_id": "menu"}) or {}
    return {"currency": meta.get("currency", "UYU"), "items": items}


@router.get("/{item_id}")
def get_item(item_id: str) -> dict:
    doc = get_db().menu.find_one({"id": item_id})
    if not doc:
        raise HTTPException(404, "Menu item not found")
    return _clean(doc)


@router.post("", status_code=201)
def create_item(body: MenuItem) -> dict:
    db = get_db()
    if db.menu.find_one({"id": body.id}):
        raise HTTPException(409, "Menu item already exists")
    db.menu.insert_one(body.model_dump())
    return body.model_dump()


@router.put("/{item_id}")
def update_item(item_id: str, body: MenuItemUpdate) -> dict:
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    db = get_db()
    res = db.menu.update_one({"id": item_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Menu item not found")
    return _clean(db.menu.find_one({"id": item_id}))


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: str) -> None:
    res = get_db().menu.delete_one({"id": item_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Menu item not found")
