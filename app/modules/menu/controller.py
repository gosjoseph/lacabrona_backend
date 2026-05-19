from fastapi import APIRouter, Depends, Query

from app.core.database import get_db
from app.modules.menu.repository import MenuRepository
from app.modules.menu.schema import MenuItemCreate, MenuItemUpdate
from app.modules.menu.service import MenuService

router = APIRouter(prefix="/api/v1/menu", tags=["menu"])


def get_service() -> MenuService:
    return MenuService(MenuRepository(get_db()))


@router.get("")
def list_menu(
    category: str | None = Query(None),
    service: MenuService = Depends(get_service),
) -> dict:
    return service.list_menu(category)


@router.get("/{item_id}")
def get_item(item_id: str, service: MenuService = Depends(get_service)) -> dict:
    return service.get_item(item_id)


@router.post("", status_code=201)
def create_item(
    body: MenuItemCreate, service: MenuService = Depends(get_service)
) -> dict:
    return service.create_item(body)


@router.put("/{item_id}")
def update_item(
    item_id: str,
    body: MenuItemUpdate,
    service: MenuService = Depends(get_service),
) -> dict:
    return service.update_item(item_id, body)


@router.delete("/{item_id}", status_code=204)
def delete_item(item_id: str, service: MenuService = Depends(get_service)) -> None:
    service.delete_item(item_id)
