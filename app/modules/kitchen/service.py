"""Kitchen Display System read service.

Surfaces only the tickets currently being prepared (status ``preparing``) and
guarantees every line carries a resolved ``station`` and a ``ready`` flag —
back-filling legacy lines on read without mutating the stored documents.

A ``new`` order has not been accepted yet, so it stays on the Pedidos board
(awaiting "Aceptar") and never reaches the cocina screen; ``ready`` and the
terminal statuses have already left the kitchen view.
"""

from __future__ import annotations

from app.modules.categories.repository import CategoryRepository
from app.modules.kitchen.resolver import StationResolver
from app.modules.menu.repository import MenuRepository
from app.modules.orders.repository import OrderRepository

ACTIVE_STATUSES = ["preparing"]


class KitchenService:
    def __init__(
        self,
        order_repository: OrderRepository,
        menu_repository: MenuRepository,
        category_repository: CategoryRepository,
    ):
        self.order_repository = order_repository
        self.menu_repository = menu_repository
        self.category_repository = category_repository

    def list_tickets(self) -> dict:
        resolver = StationResolver.from_repositories(
            self.menu_repository, self.category_repository
        )
        tickets = self.order_repository.list_by_statuses(ACTIVE_STATUSES)
        # `tickets` are detached copies (the repository strips _id and the driver
        # returns fresh dicts), so back-filling here never touches stored docs.
        for ticket in tickets:
            for line in ticket.get("items", []):
                if not line.get("station"):
                    line["station"] = resolver.station_for(line.get("id"))
                line["ready"] = bool(line.get("ready", False))
        return {"tickets": tickets}
