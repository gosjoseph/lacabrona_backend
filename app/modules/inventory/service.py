from fastapi import HTTPException

from app.core.utils import strip_mongo_id, utcnow
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schema import (
    InventoryItemCreate,
    InventoryRestock,
    InventoryUpdate,
)


class InventoryService:
    def __init__(self, repository: InventoryRepository):
        self.repository = repository

    @staticmethod
    def _normalize(doc: dict) -> dict:
        """Backfill the dual-stock + providers shape on every read path.

        Legacy documents predate `stock_real`/`stock_estimated`/`providers`
        (they carried a single `stock` and a scalar `supplier`). We never write
        during a read; we just return a normalized copy and drop legacy keys.
        """
        doc = strip_mongo_id(dict(doc))

        if doc.get("stock_real") is None:
            doc["stock_real"] = doc.get("stock", 0.0)
        if doc.get("stock_estimated") is None:
            doc["stock_estimated"] = doc.get("stock_real", doc.get("stock", 0.0))

        if not doc.get("providers"):
            supplier = doc.get("supplier")
            doc["providers"] = (
                [{"name": supplier, "price": 0.0}] if supplier else []
            )

        doc.pop("stock", None)
        doc.pop("supplier", None)
        return doc

    def list_inventory(self) -> dict:
        return {"items": [self._normalize(d) for d in self.repository.list()]}

    def get_item(self, item_id: str) -> dict:
        doc = self.repository.find_raw(item_id)
        if not doc:
            raise HTTPException(404, "Inventory item not found")
        return self._normalize(doc)

    def create_item(self, body: InventoryItemCreate) -> dict:
        if self.repository.exists(body.id):
            raise HTTPException(409, "Inventory item already exists")
        data = body.model_dump()
        if data.get("stock_estimated") is None:
            data["stock_estimated"] = data["stock_real"]
        data["updated"] = utcnow()
        self.repository.insert(data)
        return self._normalize(data)

    def update_item(self, item_id: str, body: InventoryUpdate) -> dict:
        updates = body.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(400, "No fields to update")
        updates["updated"] = utcnow()
        if not self.repository.update(item_id, updates):
            raise HTTPException(404, "Inventory item not found")
        return self.get_item(item_id)

    def restock(self, item_id: str, body: InventoryRestock) -> dict:
        doc = self.repository.find_raw(item_id)
        if not doc:
            raise HTTPException(404, "Inventory item not found")
        norm = self._normalize(doc)
        real = norm["stock_real"]
        est = norm["stock_estimated"]
        if body.mode == "add":
            new_real = max(0, real + body.amount)
            new_est = max(0, est + body.amount)
        else:  # "set" — recount / final tally: both become the absolute amount
            new_real = max(0, body.amount)
            new_est = max(0, body.amount)
        self.repository.update(
            item_id,
            {
                "stock_real": new_real,
                "stock_estimated": new_est,
                "updated": utcnow(),
            },
        )
        return self.get_item(item_id)

    def delete_item(self, item_id: str) -> None:
        if not self.repository.delete(item_id):
            raise HTTPException(404, "Inventory item not found")
