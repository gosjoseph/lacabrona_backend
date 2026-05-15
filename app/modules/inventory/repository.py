from pymongo.database import Database

from app.core.utils import strip_mongo_id


class InventoryRepository:
    def __init__(self, db: Database):
        self.collection = db.inventory

    def list(self) -> list[dict]:
        return [strip_mongo_id(d) for d in self.collection.find({})]

    def find_by_id(self, item_id: str) -> dict | None:
        doc = self.collection.find_one({"id": item_id})
        return strip_mongo_id(doc) if doc else None

    def find_raw(self, item_id: str) -> dict | None:
        return self.collection.find_one({"id": item_id})

    def exists(self, item_id: str) -> bool:
        return self.collection.find_one({"id": item_id}) is not None

    def insert(self, data: dict) -> None:
        self.collection.insert_one(data)

    def update(self, item_id: str, data: dict) -> bool:
        res = self.collection.update_one({"id": item_id}, {"$set": data})
        return res.matched_count > 0

    def delete(self, item_id: str) -> bool:
        res = self.collection.delete_one({"id": item_id})
        return res.deleted_count > 0
