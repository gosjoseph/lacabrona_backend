from fastapi import HTTPException

from app.core.utils import strip_mongo_id, utcnow
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schema import (
    InventoryAdjust,
    InventoryItemCreate,
    InventoryUpdate,
)


class InventoryService:
    def __init__(self, repository: InventoryRepository):
        self.repository = repository

    def list_inventory(self) -> dict:
        return {"items": self.repository.list()}

    def get_item(self, item_id: str) -> dict:
        doc = self.repository.find_by_id(item_id)
        if not doc:
            raise HTTPException(404, "Inventory item not found")
        return doc

    def create_item(self, body: InventoryItemCreate) -> dict:
        if self.repository.exists(body.id):
            raise HTTPException(409, "Inventory item already exists")
        data = body.model_dump()
        self.repository.insert(data)
        return strip_mongo_id(data)

    def update_item(self, item_id: str, body: InventoryUpdate) -> dict:
        updates = body.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(400, "No fields to update")
        updates["updated"] = utcnow()
        if not self.repository.update(item_id, updates):
            raise HTTPException(404, "Inventory item not found")
        return self.get_item(item_id)

    def adjust_stock(self, item_id: str, body: InventoryAdjust) -> dict:
        doc = self.repository.find_raw(item_id)
        if not doc:
            raise HTTPException(404, "Inventory item not found")
        new_stock = max(0, doc.get("stock", 0) + body.delta)
        self.repository.update(item_id, {"stock": new_stock, "updated": utcnow()})
        return self.get_item(item_id)

    def delete_item(self, item_id: str) -> None:
        if not self.repository.delete(item_id):
            raise HTTPException(404, "Inventory item not found")
