from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel

OrderStatus = Literal["new", "preparing", "ready", "served", "cancelled"]
OrderChannel = Literal["delivery", "table", "pickup"]


class OrderLine(BaseModel):
    id: str
    qty: int
    subtotal: float
    station: Optional[str] = None
    ready: bool = False


class Order(BaseModel):
    id: str
    channel: OrderChannel
    created: datetime
    status: OrderStatus = "new"
    customer: str
    # Stable identity of the customer who placed the order; stamped from the
    # session for customer-placed orders, None for staff-entered orders.
    customer_id: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    table: Optional[int] = None
    items: List[OrderLine]
    subtotal: float
    delivery: float = 0
    zone: Optional[str] = None
    service: float = 0
    tax: float = 0
    total: float
    etaMinutes: Optional[int] = None
