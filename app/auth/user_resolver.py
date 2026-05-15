"""Email → user_type resolver for the SuperTokens ThirdParty signin override.

Kept independent of the SuperTokens SDK so it can be unit-tested without
spinning up the core or constructing SDK response objects.
"""

from datetime import datetime, timezone
from typing import Any, Dict


class UnknownUserError(Exception):
    """Raised when a Google signin email is in neither customers nor employees."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def resolve_user_type(email: str, supertokens_user_id: str, db: Any) -> Dict[str, str]:
    """Look up `email` in customers then employees.

    On match: persist `supertokens_user_id` on the document (idempotent) and
    return `{"user_type": "customer"|"employee", "internal_id": str}`.

    If no match: raise `UnknownUserError`.
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

    raise UnknownUserError(
        f"Email {email} is not registered as a customer or employee"
    )
