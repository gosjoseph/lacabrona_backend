import re

from pymongo import ASCENDING
from pymongo.database import Database

from app.core.utils import strip_mongo_id, utcnow


class CustomerRepository:
    def __init__(self, db: Database):
        self.collection = db.customers
        self.ensure_indexes()

    # ----- directory-entry methods --------------------------------------

    def ensure_indexes(self) -> None:
        try:
            self.collection.create_index(
                [("phone_normalized", ASCENDING)],
                name="phone_normalized_unique",
                unique=True,
                sparse=True,
            )
        except Exception:
            # Index creation is best-effort under mongomock and idempotent in
            # real MongoDB; never let it break service construction.
            pass

    def list(self, q: str | None = None) -> list[dict]:
        query: dict = {"id": {"$regex": "^cust-"}}
        if q:
            escaped = re.escape(q)
            query["$or"] = [
                {"name": {"$regex": escaped, "$options": "i"}},
                {"phone_normalized": {"$regex": escaped}},
            ]
        return [
            strip_mongo_id(d)
            for d in self.collection.find(query).sort("created", -1)
        ]

    def find_by_id(self, customer_id: str) -> dict | None:
        doc = self.collection.find_one({"id": customer_id})
        return strip_mongo_id(doc) if doc else None

    def find_by_phone_normalized(self, phone_normalized: str) -> dict | None:
        if not phone_normalized:
            return None
        doc = self.collection.find_one({"phone_normalized": phone_normalized})
        return strip_mongo_id(doc) if doc else None

    def find_latest(self) -> dict | None:
        return self.collection.find_one(
            {"id": {"$regex": "^cust-"}},
            sort=[("created", -1)],
        )

    def insert(self, data: dict) -> str:
        result = self.collection.insert_one(data)
        return str(result.inserted_id)

    def update(self, customer_id: str, patch: dict) -> bool:
        res = self.collection.update_one({"id": customer_id}, {"$set": patch})
        return res.matched_count > 0

    def delete(self, customer_id: str) -> bool:
        res = self.collection.delete_one({"id": customer_id})
        return res.deleted_count > 0

    # ----- legacy auth methods (SuperTokens linkage) --------------------

    def find_by_email(self, email: str) -> dict | None:
        return self.collection.find_one({"email": email})

    def find_by_supertokens_id(self, supertokens_user_id: str) -> dict | None:
        return self.collection.find_one({"supertokens_user_id": supertokens_user_id})

    def stamp_supertokens_id(self, mongo_id, supertokens_user_id: str) -> None:
        self.collection.update_one(
            {"_id": mongo_id},
            {"$set": {
                "supertokens_user_id": supertokens_user_id,
                "updated_at": utcnow(),
            }},
        )

