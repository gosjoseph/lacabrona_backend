from pymongo.database import Database

from app.core.utils import strip_mongo_id


class CategoryRepository:
    def __init__(self, db: Database):
        self.collection = db.categories

    def list(self) -> list[dict]:
        cursor = self.collection.find({}).sort("order", 1)
        return [strip_mongo_id(d) for d in cursor]

    def find_by_id(self, category_id: str) -> dict | None:
        doc = self.collection.find_one({"id": category_id})
        return strip_mongo_id(doc) if doc else None

    def exists(self, category_id: str) -> bool:
        return self.collection.find_one({"id": category_id}) is not None

    def insert(self, data: dict) -> None:
        self.collection.insert_one(data)

    def update(self, category_id: str, data: dict) -> bool:
        res = self.collection.update_one({"id": category_id}, {"$set": data})
        return res.matched_count > 0

    def delete(self, category_id: str) -> bool:
        res = self.collection.delete_one({"id": category_id})
        return res.deleted_count > 0
