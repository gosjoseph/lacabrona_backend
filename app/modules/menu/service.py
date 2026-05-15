from fastapi import HTTPException

from app.modules.menu.repository import MenuRepository
from app.modules.menu.schema import MenuItemCreate, MenuItemUpdate


class MenuService:
    def __init__(self, repository: MenuRepository):
        self.repository = repository

    def list_menu(self, category: str | None = None) -> dict:
        items = self.repository.list(category)
        return {"currency": self.repository.get_currency(), "items": items}

    def get_item(self, item_id: str) -> dict:
        doc = self.repository.find_by_id(item_id)
        if not doc:
            raise HTTPException(404, "Menu item not found")
        return doc

    def create_item(self, body: MenuItemCreate) -> dict:
        if self.repository.exists(body.id):
            raise HTTPException(409, "Menu item already exists")
        data = body.model_dump()
        self.repository.insert(data)
        return data

    def update_item(self, item_id: str, body: MenuItemUpdate) -> dict:
        updates = body.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(400, "No fields to update")
        if not self.repository.update(item_id, updates):
            raise HTTPException(404, "Menu item not found")
        return self.repository.find_by_id(item_id)

    def delete_item(self, item_id: str) -> None:
        if not self.repository.delete(item_id):
            raise HTTPException(404, "Menu item not found")
