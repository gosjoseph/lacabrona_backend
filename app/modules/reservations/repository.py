from datetime import datetime

from pymongo.database import Database

from app.core.utils import strip_mongo_id


class ReservationRepository:
    def __init__(self, db: Database):
        self.collection = db.reservations

    def list(self, start: datetime | None = None, end: datetime | None = None) -> list[dict]:
        q: dict = {}
        if start and end:
            q["time"] = {"$gte": start, "$lte": end}
        return [strip_mongo_id(d) for d in self.collection.find(q).sort("time", 1)]

    def find_by_id(self, reservation_id: str) -> dict | None:
        doc = self.collection.find_one({"id": reservation_id})
        return strip_mongo_id(doc) if doc else None

    def find_latest(self) -> dict | None:
        return self.collection.find_one(sort=[("time", -1)])

    def insert(self, data: dict) -> None:
        self.collection.insert_one(data)

    def update(self, reservation_id: str, data: dict) -> bool:
        res = self.collection.update_one({"id": reservation_id}, {"$set": data})
        return res.matched_count > 0

    def delete(self, reservation_id: str) -> bool:
        res = self.collection.delete_one({"id": reservation_id})
        return res.deleted_count > 0
