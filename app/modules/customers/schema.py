from typing import Optional

from pydantic import BaseModel

from app.modules.customers.model import Customer

CustomerResponse = Customer


class CustomerCreate(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    notes: str = ""


class CustomerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None
