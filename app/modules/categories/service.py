from fastapi import HTTPException

from app.core.utils import strip_mongo_id
from app.modules.categories.repository import CategoryRepository
from app.modules.categories.schema import CategoryCreate, CategoryUpdate


class CategoryService:
    def __init__(self, repository: CategoryRepository):
        self.repository = repository

    def list_categories(self) -> list[dict]:
        return self.repository.list()

    def get_category(self, category_id: str) -> dict:
        doc = self.repository.find_by_id(category_id)
        if not doc:
            raise HTTPException(404, "Category not found")
        return doc

    def create_category(self, body: CategoryCreate) -> dict:
        if self.repository.exists(body.id):
            raise HTTPException(409, "Category already exists")
        data = body.model_dump()
        self.repository.insert(data)
        return strip_mongo_id(data)

    def update_category(self, category_id: str, body: CategoryUpdate) -> dict:
        data = body.model_dump()
        if not self.repository.update(category_id, data):
            raise HTTPException(404, "Category not found")
        return data

    def delete_category(self, category_id: str) -> None:
        if not self.repository.delete(category_id):
            raise HTTPException(404, "Category not found")
