from datetime import datetime, timezone

from fastapi import HTTPException

from app.core.utils import strip_mongo_id, utcnow
from app.modules.kitchen.resolver import StationResolver
from app.modules.orders.model import Order
from app.modules.orders.repository import OrderRepository
from app.modules.orders.schema import OrderCreate, OrderStatusUpdate
from app.modules.orders.status import derive_status


class OrderService:
    def __init__(self, repository: OrderRepository, menu_repository=None, category_repository=None):
        self.repository = repository
        self.menu_repository = menu_repository
        self.category_repository = category_repository

    def _station_resolver(self) -> StationResolver:
        """Build a resolver from the wired repositories.

        When the menu/category repositories aren't injected (e.g. unit tests that
        only need order CRUD) the resolver simply falls everything back to the
        literal "general" station.
        """
        menu_by_id: dict = {}
        category_by_id: dict = {}
        if self.menu_repository is not None:
            menu_by_id = {item["id"]: item for item in self.menu_repository.list()}
        if self.category_repository is not None:
            category_by_id = {cat["id"]: cat for cat in self.category_repository.list()}
        return StationResolver(menu_by_id, category_by_id)

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
        # The server is authoritative for kitchen routing: resolve and stamp the
        # station on every line (ignoring any client-sent value) and reset ready.
        resolver = self._station_resolver()
        lines = []
        for line in body.items:
            stamped = line.model_copy(
                update={"station": resolver.station_for(line.id), "ready": False}
            )
            lines.append(stamped)
        order = Order(
            id=self._next_order_id(),
            channel=body.channel,
            created=utcnow(),
            status="new",
            customer=body.customer,
            address=body.address,
            phone=body.phone,
            table=body.table,
            items=lines,
            subtotal=subtotal,
            delivery=body.delivery,
            total=total,
            etaMinutes=body.etaMinutes,
        )
        data = order.model_dump()
        self.repository.insert(data)
        return strip_mongo_id(data)

    def set_status(self, order_id: str, body: OrderStatusUpdate) -> dict:
        if not self.repository.update_status(order_id, body.status):
            raise HTTPException(404, "Order not found")
        return self.get_order(order_id)

    def set_line_ready(self, order_id: str, line_id: str, ready: bool) -> dict:
        doc = self.repository.find_by_id(order_id)
        if not doc:
            raise HTTPException(404, "Order not found")
        lines = doc.get("items", [])
        target = next((line for line in lines if line.get("id") == line_id), None)
        if target is None:
            raise HTTPException(404, "Order line not found")
        target["ready"] = ready
        new_status = derive_status(doc["status"], lines)
        self.repository.update_lines_and_status(order_id, lines, new_status)
        return self.get_order(order_id)

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
