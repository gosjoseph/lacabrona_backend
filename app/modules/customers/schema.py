from typing import Optional

from pydantic import BaseModel

from app.modules.customers.model import Customer

CustomerResponse = Customer


class CustomerCreate(BaseModel):
    name: str
    # Optional so the ops flow can create a name-only canonical customer (e.g.
    # a typed, unknown customer on a manual order). When omitted the customer
    # carries no phone and is left out of the sparse phone-uniqueness index.
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: str = ""


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
