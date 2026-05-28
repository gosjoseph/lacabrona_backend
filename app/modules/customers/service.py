import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from app.core.utils import strip_mongo_id, utcnow
from app.modules.customers.repository import CustomerRepository
from app.modules.customers.schema import CustomerCreate, CustomerUpdate

_PHONE_STRIP_RE = re.compile(r"[\s\-\(\)\.]")


def normalize_phone(s) -> str:
    """Strip ASCII whitespace, dashes, parens, dots; preserve any leading '+'.

    Returns "" for None or empty input.
    """
    if not s:
        return ""
    return _PHONE_STRIP_RE.sub("", str(s))


class CustomerService:
    def __init__(self, repository: CustomerRepository):
        self.repository = repository

    # ----- directory CRUD ----------------------------------------------

    def list_customers(self, q: str | None = None) -> dict:
        return {"customers": self.repository.list(q)}

    def get_customer(self, customer_id: str) -> dict:
        doc = self.repository.find_by_id(customer_id)
        if not doc:
            raise HTTPException(404, "Customer not found")
        return doc

    def create_customer(self, body: CustomerCreate) -> dict:
        phone_normalized = normalize_phone(body.phone)
        if phone_normalized and self.repository.find_by_phone_normalized(
            phone_normalized
        ):
            raise HTTPException(409, "Customer with that phone already exists")
        now = utcnow()
        doc = {
            "id": self._next_customer_id(),
            "name": body.name,
            "phone": body.phone,
            "phone_normalized": phone_normalized,
            "email": body.email,
            "notes": body.notes or "",
            "created": now,
            "updated": now,
        }
        self.repository.insert(doc)
        return strip_mongo_id(doc)

    def update_customer(self, customer_id: str, body: CustomerUpdate) -> dict:
        existing = self.repository.find_by_id(customer_id)
        if not existing:
            raise HTTPException(404, "Customer not found")

        updates = body.model_dump(exclude_unset=True)
        if not updates:
            return existing

        if "phone" in updates:
            new_norm = normalize_phone(updates["phone"])
            if new_norm:
                collision = self.repository.find_by_phone_normalized(new_norm)
                if collision and collision.get("id") != customer_id:
                    raise HTTPException(
                        409, "That phone already belongs to another customer"
                    )
            updates["phone_normalized"] = new_norm

        updates["updated"] = utcnow()
        self.repository.update(customer_id, updates)
        return self.get_customer(customer_id)

    def delete_customer(self, customer_id: str) -> None:
        if not self.repository.delete(customer_id):
            raise HTTPException(404, "Customer not found")

    # ----- upsert + backfill -------------------------------------------

    def upsert(
        self, name: str, phone: str, email: Optional[str] = None
    ) -> Optional[dict]:
        phone_norm = normalize_phone(phone)
        if not phone_norm:
            return None
        existing = self.repository.find_by_phone_normalized(phone_norm)
        now = utcnow()
        if existing:
            patch: dict = {"updated": now}
            if existing.get("name") != name:
                patch["name"] = name
            if email and not existing.get("email"):
                patch["email"] = email
            self.repository.update(existing["id"], patch)
            return self.repository.find_by_id(existing["id"])
        doc = {
            "id": self._next_customer_id(),
            "name": name,
            "phone": phone,
            "phone_normalized": phone_norm,
            "email": email,
            "notes": "",
            "created": now,
            "updated": now,
        }
        self.repository.insert(doc)
        return strip_mongo_id(doc)

    def backfill(self) -> dict:
        db = self.repository.collection.database
        scanned = 0
        created = 0
        updated = 0

        def _process(name: str, phone: str) -> None:
            nonlocal scanned, created, updated
            if not phone:
                return
            phone_norm = normalize_phone(phone)
            if not phone_norm:
                return
            scanned += 1
            existing = self.repository.find_by_phone_normalized(phone_norm)
            if existing is None:
                self.upsert(name=name, phone=phone)
                created += 1
            else:
                old_name = existing.get("name")
                self.upsert(name=name, phone=phone)
                if old_name != name:
                    updated += 1

        for r in db.reservations.find({}):
            _process(r.get("name", ""), r.get("phone", ""))
        for o in db.orders.find({}):
            _process(o.get("customer", ""), o.get("phone", ""))

        return {"scanned": scanned, "created": created, "updated": updated}

    def _next_customer_id(self) -> str:
        last = self.repository.find_latest()
        if not last:
            return "cust-1001"
        try:
            n = int(str(last["id"]).split("-")[-1])
            return f"cust-{n + 1}"
        except Exception:
            return f"cust-{int(datetime.now(timezone.utc).timestamp())}"

    # ----- legacy auth helpers (SuperTokens linkage) -------------------

    def find_by_email(self, email: str) -> dict | None:
        return self.repository.find_by_email(email)

    def find_by_supertokens_id(self, supertokens_user_id: str) -> dict | None:
        return self.repository.find_by_supertokens_id(supertokens_user_id)

    def ensure_linked_to_supertokens(
        self, customer_doc: dict, supertokens_user_id: str
    ) -> None:
        if not customer_doc.get("supertokens_user_id"):
            self.repository.stamp_supertokens_id(customer_doc["_id"], supertokens_user_id)

    def create_from_profile(
        self, email: str, supertokens_user_id: str, profile: dict
    ) -> str:
        now = utcnow()
        new_doc = {
            "email": email,
            "full_name": profile.get("full_name", ""),
            "first_name": profile.get("first_name", ""),
            "last_name": profile.get("last_name", ""),
            "supertokens_user_id": supertokens_user_id,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        return self.repository.insert(new_doc)
