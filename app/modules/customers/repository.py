from __future__ import annotations

import re

from pymongo import ASCENDING
from pymongo.database import Database

from app.core.utils import normalize_email, normalize_phone, strip_mongo_id, utcnow


class CustomerRepository:
    def __init__(self, db: Database):
        self.collection = db.customers
        self.ensure_indexes()

    # ----- directory-entry methods --------------------------------------

    def ensure_indexes(self) -> None:
        """Bring the index set onto the Part-2 convergence shape. Idempotent.

        - ``email_normalized``: SPARSE UNIQUE — one email == one customer, so a
          colliding email is detected (in application logic, before the write)
          and converged/merged rather than silently duplicated.
        - ``phone_normalized``: NON-unique. Phone uniqueness/merge moved into
          application logic because two auth-linked records may legitimately
          SHARE a phone (``shared_phone``), which a unique index would reject.
          The old ``phone_normalized_unique`` index is dropped if still present.

        Every step is best-effort and idempotent: it must never break service
        construction, and must not fail when the old phone index is already
        gone or the new indexes already exist.
        """
        try:
            existing = set(self.collection.index_information().keys())
        except Exception:
            existing = set()

        # Migration: retire the legacy sparse-unique phone index.
        if "phone_normalized_unique" in existing:
            try:
                self.collection.drop_index("phone_normalized_unique")
            except Exception:
                pass

        try:
            self.collection.create_index(
                [("phone_normalized", ASCENDING)],
                name="phone_normalized_idx",
            )
        except Exception:
            pass

        try:
            self.collection.create_index(
                [("email_normalized", ASCENDING)],
                name="email_normalized_unique",
                unique=True,
                sparse=True,
            )
        except Exception:
            # A pre-existing collection with duplicate/empty email_normalized
            # values would reject the unique index — leave it uncreated rather
            # than crashing startup; the application-level guard still applies.
            pass

    def list(self, q: str | None = None) -> list[dict]:
        query: dict = {"id": {"$regex": "^cust-"}}
        if q:
            escaped = re.escape(q)
            ors: list[dict] = [
                {"name": {"$regex": escaped, "$options": "i"}},
                {"email": {"$regex": escaped, "$options": "i"}},
            ]
            email_norm = normalize_email(q)
            if email_norm:
                ors.append({"email_normalized": {"$regex": re.escape(email_norm)}})
            phone_norm = normalize_phone(q)
            if phone_norm:
                ors.append({"phone_normalized": {"$regex": re.escape(phone_norm)}})
            query["$or"] = ors
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

    def find_other_by_email_normalized(
        self, email_normalized: str, exclude_id: str
    ) -> dict | None:
        """A different record sharing this normalized email (or None).

        Excludes the record `exclude_id` so a write that re-states a record's
        own email never collides with itself. At most one such record can exist
        because of the sparse-unique email index.
        """
        if not email_normalized:
            return None
        doc = self.collection.find_one(
            {"email_normalized": email_normalized, "id": {"$ne": exclude_id}}
        )
        return strip_mongo_id(doc) if doc else None

    def find_others_by_phone_normalized(
        self, phone_normalized: str, exclude_id: str
    ) -> list[dict]:
        """Every other record sharing this normalized phone (excluding self).

        Returns a list because the phone index is non-unique now: a shared
        phone can be held by two or more records.
        """
        if not phone_normalized:
            return []
        return [
            strip_mongo_id(d)
            for d in self.collection.find(
                {"phone_normalized": phone_normalized, "id": {"$ne": exclude_id}}
            )
        ]

    def repoint_orders(self, loser_id: str, survivor_id: str) -> int:
        """Re-point every order from a merged-away customer onto the survivor.

        Returns the number of orders re-pointed. Reservations carry no
        `customer_id`, so there is nothing to re-point there.
        """
        result = self.collection.database.orders.update_many(
            {"customer_id": loser_id}, {"$set": {"customer_id": survivor_id}}
        )
        return result.modified_count

    def find_latest(self) -> dict | None:
        return self.collection.find_one(
            {"id": {"$regex": "^cust-"}},
            sort=[("created", -1)],
        )

    def insert(self, data: dict) -> str:
        result = self.collection.insert_one(data)
        return str(result.inserted_id)

    def update(
        self, customer_id: str, patch: dict, unset: list[str] | None = None
    ) -> bool:
        update_doc: dict = {}
        if patch:
            update_doc["$set"] = patch
        if unset:
            update_doc["$unset"] = {key: "" for key in unset}
        if not update_doc:
            return False
        res = self.collection.update_one({"id": customer_id}, update_doc)
        return res.matched_count > 0

    def delete(self, customer_id: str) -> bool:
        res = self.collection.delete_one({"id": customer_id})
        return res.deleted_count > 0

    # ----- legacy auth methods (SuperTokens linkage) --------------------

    def find_by_email(self, email: str) -> dict | None:
        return self.collection.find_one({"email": email})

    def find_by_email_normalized(self, email_normalized: str) -> dict | None:
        if not email_normalized:
            return None
        return self.collection.find_one({"email_normalized": email_normalized})

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

