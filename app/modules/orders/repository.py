from pymongo.database import Database

from app.core.utils import strip_mongo_id


class OrderRepository:
    def __init__(self, db: Database):
        self.collection = db.orders

    def list(self, status: str | None = None) -> list[dict]:
        q: dict = {}
        if status:
            q["status"] = status
        return [strip_mongo_id(d) for d in self.collection.find(q).sort("created", -1)]

    def find_by_id(self, order_id: str) -> dict | None:
        doc = self.collection.find_one({"id": order_id})
        return strip_mongo_id(doc) if doc else None

    def find_latest(self) -> dict | None:
        return self.collection.find_one(sort=[("created", -1)])

    def insert(self, data: dict) -> None:
        self.collection.insert_one(data)

    def update_status(self, order_id: str, status: str) -> bool:
        res = self.collection.update_one({"id": order_id}, {"$set": {"status": status}})
        return res.matched_count > 0

    def delete(self, order_id: str) -> bool:
        res = self.collection.delete_one({"id": order_id})
        return res.deleted_count > 0
