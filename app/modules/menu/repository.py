from pymongo.database import Database

from app.core.utils import strip_mongo_id


class MenuRepository:
    def __init__(self, db: Database):
        self.db = db
        self.collection = db.menu

    def list(self, category: str | None = None) -> list[dict]:
        q: dict = {}
        if category:
            q["category"] = category
        return [strip_mongo_id(d) for d in self.collection.find(q)]

    def find_by_id(self, item_id: str) -> dict | None:
        doc = self.collection.find_one({"id": item_id})
        return strip_mongo_id(doc) if doc else None

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

    def get_currency(self) -> str:
        meta = self.db.meta.find_one({"_id": "menu"}) or {}
        return meta.get("currency", "UYU")
