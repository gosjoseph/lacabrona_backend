from datetime import datetime, timezone

from fastapi import HTTPException

from app.core.utils import utcnow
from app.modules.orders.model import Order
from app.modules.orders.repository import OrderRepository
from app.modules.orders.schema import OrderCreate, OrderStatusUpdate


class OrderService:
    def __init__(self, repository: OrderRepository):
        self.repository = repository

    def list_orders(self, status: str | None = None) -> dict:
        return {"orders": self.repository.list(status)}

    def get_order(self, order_id: str) -> dict:
        doc = self.repository.find_by_id(order_id)
        if not doc:
            raise HTTPException(404, "Order not found")
        return doc

    def create_order(self, body: OrderCreate) -> dict:
        subtotal = sum(line.subtotal for line in body.items)
        total = subtotal + body.delivery
        order = Order(
            id=self._next_order_id(),
            channel=body.channel,
            created=utcnow(),
            status="new",
            customer=body.customer,
            address=body.address,
            phone=body.phone,
            table=body.table,
            items=body.items,
            subtotal=subtotal,
            delivery=body.delivery,
            total=total,
            etaMinutes=body.etaMinutes,
        )
        data = order.model_dump()
        self.repository.insert(data)
        return data

    def set_status(self, order_id: str, body: OrderStatusUpdate) -> dict:
        if not self.repository.update_status(order_id, body.status):
            raise HTTPException(404, "Order not found")
        return self.repository.find_by_id(order_id)

    def delete_order(self, order_id: str) -> None:
        if not self.repository.delete(order_id):
            raise HTTPException(404, "Order not found")

    def _next_order_id(self) -> str:
        last = self.repository.find_latest()
        if not last:
            return "ord-1001"
        try:
            n = int(str(last["id"]).split("-")[-1])
            return f"ord-{n + 1}"
        except Exception:
            return f"ord-{int(datetime.now(timezone.utc).timestamp())}"
