from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.core.utils import utcnow


class Customer(BaseModel):
    """Shared customer document.

    Two kinds of records coexist in the `customers` collection:
      - SuperTokens-linked auth records (created via Google signin) — populate
        `email`, `full_name`, `supertokens_user_id`, etc.
      - Directory entries (created via the ops Clientes UI or auto-upsert from
        reservations/orders) — populate `id` ("cust-NNNN"), `name`, `phone`,
        `phone_normalized`, `notes`, `created`, `updated`.
    """

    id: Optional[str] = None
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    supertokens_user_id: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    name: Optional[str] = None
    phone: Optional[str] = None
    phone_normalized: Optional[str] = None
    notes: str = ""
    created: Optional[datetime] = None
    updated: Optional[datetime] = None
