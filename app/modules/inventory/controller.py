from fastapi import APIRouter, Depends

from app.core.database import get_db
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schema import (
    InventoryAdjust,
    InventoryItemCreate,
    InventoryUpdate,
)
from app.modules.inventory.service import InventoryService

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


def get_service() -> InventoryService:
    return InventoryService(InventoryRepository(get_db()))


@router.get("")
def list_inventory(service: InventoryService = Depends(get_service)) -> dict:
    return service.list_inventory()


@router.get("/{item_id}")
def get_item(item_id: str, service: InventoryService = Depends(get_service)) -> dict:
    return service.get_item(item_id)


@router.post("", status_code=201)
def create_item(
    body: InventoryItemCreate, service: InventoryService = Depends(get_service)
) -> dict:
    return service.create_item(body)


@router.put("/{item_id}")
def update_item(
    item_id: str,
    body: InventoryUpdate,
    service: InventoryService = Depends(get_service),
) -> dict:
    return service.update_item(item_id, body)


@router.post("/{item_id}/adjust")
def adjust_stock(
    item_id: str,
    body: InventoryAdjust,
    service: InventoryService = Depends(get_service),
) -> dict:
    return service.adjust_stock(item_id, body)


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: str, service: InventoryService = Depends(get_service)) -> None:
    service.delete_item(item_id)
