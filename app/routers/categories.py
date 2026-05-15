from fastapi import APIRouter, HTTPException

from ..db import get_db
from ..models import Category

router = APIRouter(prefix="/api/categories", tags=["categories"])


def _clean(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


@router.get("")
def list_categories() -> list[dict]:
    cursor = get_db().categories.find({}).sort("order", 1)
    return [_clean(d) for d in cursor]


@router.get("/{category_id}")
def get_category(category_id: str) -> dict:
    doc = get_db().categories.find_one({"id": category_id})
    if not doc:
        raise HTTPException(404, "Category not found")
    return _clean(doc)


@router.post("", status_code=201)
def create_category(body: Category) -> dict:
    db = get_db()
    if db.categories.find_one({"id": body.id}):
        raise HTTPException(409, "Category already exists")
    db.categories.insert_one(body.model_dump())
    return body.model_dump()


@router.put("/{category_id}")
def update_category(category_id: str, body: Category) -> dict:
    res = get_db().categories.update_one(
        {"id": category_id}, {"$set": body.model_dump()}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Category not found")
    return body.model_dump()


@router.delete("/{category_id}", status_code=204)
def delete_category(category_id: str) -> None:
    res = get_db().categories.delete_one({"id": category_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Category not found")
