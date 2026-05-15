from typing import List, Optional

from pydantic import BaseModel

from app.modules.orders.model import Order, OrderChannel, OrderLine, OrderStatus

OrderResponse = Order


class OrderCreate(BaseModel):
    channel: OrderChannel
    customer: str
    address: Optional[str] = None
    phone: Optional[str] = None
    table: Optional[int] = None
    items: List[OrderLine]
    delivery: float = 0
    etaMinutes: Optional[int] = None


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
