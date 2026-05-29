from typing import List, Optional

from pydantic import BaseModel

from app.modules.orders.model import Order, OrderChannel, OrderLine, OrderStatus

OrderResponse = Order


class OrderCreate(BaseModel):
    channel: OrderChannel
    customer: str
    # Optional canonical customer id (cust-NNNN) chosen in the ops picker. When
    # present a staff order links straight to it; when absent and only a name is
    # typed, the service creates a name-only canonical customer. Ignored for
    # customer-placed orders (identity always comes from the session).
    customer_id: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    table: Optional[int] = None
    items: List[OrderLine]
    delivery: float = 0
    zone: Optional[str] = None
    etaMinutes: Optional[int] = None


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


class OrderLineReadyUpdate(BaseModel):
    ready: bool
