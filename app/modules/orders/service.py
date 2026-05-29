from datetime import datetime, timezone

from fastapi import HTTPException

from app.core.utils import normalize_phone, strip_mongo_id, utcnow
from app.modules.customers.service import CustomerService
from app.modules.kitchen.resolver import StationResolver
from app.modules.orders.model import Order
from app.modules.orders.repository import OrderRepository
from app.modules.orders.schema import OrderCreate, OrderStatusUpdate
from app.modules.orders.status import derive_status
from app.modules.settings.model import Settings
from app.modules.settings.service import SettingsService

# Per-customer cap on simultaneously-open orders. An order counts as "active"
# until it is served or cancelled. Enforced only for customer-placed orders.
MAX_ACTIVE_CUSTOMER_ORDERS = 3
ACTIVE_ORDER_STATUSES = ["new", "preparing", "ready"]


def _customer_identity(doc: dict) -> tuple[str, str]:
    """Derive a stable ``(customer_id, display_name)`` from a customer doc.

    The directory id (``cust-…``) is preferred for the id; otherwise the Mongo
    ``_id``. The name prefers the directory ``name``, then the Google
    first/last name, then ``full_name``, then the email local-part.
    """
    customer_id = doc.get("id") or str(doc.get("_id") or "")
    name = (doc.get("name") or "").strip()
    if not name:
        name = " ".join(
            part for part in (doc.get("first_name"), doc.get("last_name")) if part
        ).strip()
    if not name:
        name = (doc.get("full_name") or "").strip()
    if not name and doc.get("email"):
        name = str(doc["email"]).split("@")[0]
    if not name:
        name = "Cliente"
    return customer_id, name


class OrderService:
    def __init__(
        self,
        repository: OrderRepository,
        menu_repository=None,
        category_repository=None,
        settings_repository=None,
        customer_repository=None,
    ):
        self.repository = repository
        self.menu_repository = menu_repository
        self.category_repository = category_repository
        self.settings_repository = settings_repository
        self.customer_repository = customer_repository

    def _settings(self) -> dict:
        """Resolve the operational settings.

        When no settings repository is injected (e.g. unit tests that only need
        order CRUD) fall back to the model DEFAULTS so behaviour is inert: all
        channels on, no zones, zero charge rates.
        """
        if self.settings_repository is None:
            return Settings().model_dump()
        return SettingsService(self.settings_repository).settings_doc()

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

    def create_order(self, body: OrderCreate, actor: dict | None = None) -> dict:
        """Create an order.

        When ``actor`` is a customer the order is hardened against pre-payment
        abuse: empty orders are rejected, identity is stamped from the session
        (ignoring any client-sent identity), the status is forced to "new", and
        a per-customer open-order cap applies. For an employee actor (or no
        actor — internal/legacy callers) behaviour is unchanged.

        Order of checks for a customer:
        empty(422) -> channel(409) -> cap(429) -> delivery/zone(422) -> insert.
        """
        is_customer = bool(actor) and actor.get("user_type") == "customer"

        # 0. Empty order — a customer must order something.
        if is_customer and not body.items:
            raise HTTPException(422, "El pedido no puede estar vacío")

        settings = self._settings()

        # 1. Channel gating — a disabled channel is refused regardless of who
        #    creates the order.
        if not settings["channels"].get(body.channel, True):
            raise HTTPException(409, "Canal no disponible")

        # 2. Customer linkage + open-order cap. For a customer the identity
        #    always comes from the session (any client-sent customer/customer_id
        #    is ignored). For a staff order it is resolved from the picked
        #    customer_id, or a canonical customer is created from the typed name.
        customer_name = body.customer
        if is_customer:
            customer_id, customer_name = _customer_identity(actor["doc"])
            active = self.repository.count_active_by_customer(
                customer_id, ACTIVE_ORDER_STATUSES
            )
            if active >= MAX_ACTIVE_CUSTOMER_ORDERS:
                raise HTTPException(429, "Demasiados pedidos activos")
        else:
            customer_id = self._resolve_staff_customer_id(body)

        subtotal = sum(line.subtotal for line in body.items)

        # 3. Delivery fee — when a delivery order names a zone, the server is
        #    authoritative for its fee (any client-sent delivery is ignored).
        #    With no zone, the client delivery is kept (backward compatible).
        #    A customer delivery order must also carry an address.
        delivery = body.delivery
        zone = None
        if body.channel == "delivery":
            if is_customer and not body.address:
                raise HTTPException(422, "El delivery requiere una dirección")
            if body.zone is not None:
                zones = {z["id"]: z for z in settings["delivery_zones"]}
                match = zones.get(body.zone)
                if match is None:
                    raise HTTPException(422, "Zona inválida")
                delivery = match["fee"]
                zone = body.zone

        # 4. Charges — service over subtotal, tax over (subtotal + service).
        #    tax is excluded from the total when prices already include it.
        #    tip_default_rate is config only and never added to a total.
        charges = settings["charges"]
        service = round(subtotal * charges["service_rate"], 2)
        tax = round((subtotal + service) * charges["tax_rate"], 2)
        total = subtotal + delivery + service + (0 if charges["tax_included"] else tax)

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
            customer=customer_name,
            customer_id=customer_id,
            address=body.address,
            phone=body.phone,
            table=body.table,
            items=lines,
            subtotal=subtotal,
            delivery=delivery,
            zone=zone,
            service=service,
            tax=tax,
            total=total,
            etaMinutes=body.etaMinutes,
        )
        data = order.model_dump()
        self.repository.insert(data)
        return strip_mongo_id(data)

    def _resolve_staff_customer_id(self, body: OrderCreate) -> str | None:
        """Resolve the canonical customer id for a staff-entered order.

        Picked id wins. Otherwise, when a customer service is wired, a phone
        upserts/links a directory customer and a bare typed name creates a
        name-only canonical customer. Returns None when nothing identifies a
        customer (or no customer repository is injected).
        """
        if body.customer_id:
            return body.customer_id
        if self.customer_repository is None:
            return None
        customers = CustomerService(self.customer_repository)
        if normalize_phone(body.phone):
            linked = customers.upsert(name=body.customer, phone=body.phone)
            if linked:
                return linked.get("id")
        name = (body.customer or "").strip()
        if name:
            return customers.create_name_only(name)["id"]
        return None

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
