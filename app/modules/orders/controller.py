from fastapi import APIRouter, Depends, Query

from app.core.database import get_db
from app.modules.orders.repository import OrderRepository
from app.modules.orders.schema import OrderCreate, OrderStatusUpdate
from app.modules.orders.service import OrderService

router = APIRouter(prefix="/api/orders", tags=["orders"])


def get_service() -> OrderService:
    return OrderService(OrderRepository(get_db()))


@router.get("")
def list_orders(
    status: str | None = Query(None),
    service: OrderService = Depends(get_service),
) -> dict:
    return service.list_orders(status)


@router.get("/{order_id}")
def get_order(order_id: str, service: OrderService = Depends(get_service)) -> dict:
    return service.get_order(order_id)


@router.post("", status_code=201)
def create_order(
    body: OrderCreate, service: OrderService = Depends(get_service)
) -> dict:
    return service.create_order(body)


@router.patch("/{order_id}/status")
def set_status(
    order_id: str,
    body: OrderStatusUpdate,
    service: OrderService = Depends(get_service),
) -> dict:
    return service.set_status(order_id, body)


@router.delete("/{order_id}", status_code=204)
def delete_order(order_id: str, service: OrderService = Depends(get_service)) -> None:
    service.delete_order(order_id)
