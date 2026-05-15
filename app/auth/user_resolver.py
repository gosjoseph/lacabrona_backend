"""Email → user_type resolver for the SuperTokens ThirdParty signin override.

Kept independent of the SuperTokens SDK so it can be unit-tested without
spinning up the core or constructing SDK response objects.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional


class UnknownUserError(Exception):
    """Raised when a Google signin email is missing entirely."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def resolve_user_type(
    email: str,
    supertokens_user_id: str,
    db: Any,
    profile: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Link the Google signin to an existing record or create a new customer.

    - Existing customer: stamp `supertokens_user_id` (name fields untouched).
    - Existing employee: stamp `supertokens_user_id` (employee linking path).
    - Neither: create a new customer document using `profile`
      (`full_name`, `first_name`, `last_name`) and return its id.

    Raises `UnknownUserError` only when `email` is empty.
    """
    if not email:
        raise UnknownUserError("Google signin did not return an email")

    customer = db.customers.find_one({"email": email})
    if customer:
        if not customer.get("supertokens_user_id"):
            db.customers.update_one(
                {"_id": customer["_id"]},
                {"$set": {
                    "supertokens_user_id": supertokens_user_id,
                    "updated_at": _utcnow(),
                }},
            )
        return {"user_type": "customer", "internal_id": str(customer["_id"])}

    employee = db.employees.find_one({"email": email})
    if employee:
        if not employee.get("supertokens_user_id"):
            db.employees.update_one(
                {"_id": employee["_id"]},
                {"$set": {
                    "supertokens_user_id": supertokens_user_id,
                    "updated_at": _utcnow(),
                }},
            )
        return {
            "user_type": "employee",
            "internal_id": str(employee["_id"]),
            "role": employee.get("role", "admin"),
        }

    profile = profile or {}
    now = _utcnow()
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
    result = db.customers.insert_one(new_doc)
    return {"user_type": "customer", "internal_id": str(result.inserted_id)}
