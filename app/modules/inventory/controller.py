from fastapi import APIRouter, Depends

from app.core.database import get_db
from app.modules.auth.dependencies import require_employee
from app.modules.inventory.repository import InventoryRepository
from app.modules.inventory.schema import (
    InventoryItemCreate,
    InventoryRestock,
    InventoryUpdate,
)
from app.modules.inventory.service import InventoryService

router = APIRouter(prefix="/api/v1/inventory", tags=["inventory"])


def get_service() -> InventoryService:
    return InventoryService(InventoryRepository(get_db()))


@router.get("")
def list_inventory(service: InventoryService = Depends(get_service)) -> dict:
    return service.list_inventory()


@router.get("/{item_id}")
def get_item(item_id: str, service: InventoryService = Depends(get_service)) -> dict:
    return service.get_item(item_id)


@router.post("", status_code=201, dependencies=[Depends(require_employee)])
def create_item(
    body: InventoryItemCreate, service: InventoryService = Depends(get_service)
) -> dict:
    return service.create_item(body)


@router.put("/{item_id}", dependencies=[Depends(require_employee)])
def update_item(
    item_id: str,
    body: InventoryUpdate,
    service: InventoryService = Depends(get_service),
) -> dict:
    return service.update_item(item_id, body)


@router.post("/{item_id}/restock", dependencies=[Depends(require_employee)])
def restock(
    item_id: str,
    body: InventoryRestock,
    service: InventoryService = Depends(get_service),
) -> dict:
    return service.restock(item_id, body)


@router.delete("/{item_id}", status_code=204, dependencies=[Depends(require_employee)])
def delete_item(item_id: str, service: InventoryService = Depends(get_service)) -> None:
    service.delete_item(item_id)
