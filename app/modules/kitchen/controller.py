from fastapi import APIRouter, Depends

from app.core.database import get_db
from app.modules.categories.repository import CategoryRepository
from app.modules.kitchen.service import KitchenService
from app.modules.menu.repository import MenuRepository
from app.modules.orders.repository import OrderRepository

router = APIRouter(prefix="/api/v1/kitchen", tags=["kitchen"])


def get_service() -> KitchenService:
    db = get_db()
    return KitchenService(
        OrderRepository(db),
        MenuRepository(db),
        CategoryRepository(db),
    )


@router.get("")
def list_tickets(service: KitchenService = Depends(get_service)) -> dict:
    return service.list_tickets()
