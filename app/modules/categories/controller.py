from fastapi import APIRouter, Depends

from app.core.database import get_db
from app.modules.categories.repository import CategoryRepository
from app.modules.categories.schema import CategoryCreate, CategoryUpdate
from app.modules.categories.service import CategoryService

router = APIRouter(prefix="/api/v1/categories", tags=["categories"])


def get_service() -> CategoryService:
    return CategoryService(CategoryRepository(get_db()))


@router.get("")
def list_categories(service: CategoryService = Depends(get_service)) -> list[dict]:
    return service.list_categories()


@router.get("/{category_id}")
def get_category(category_id: str, service: CategoryService = Depends(get_service)) -> dict:
    return service.get_category(category_id)


@router.post("", status_code=201)
def create_category(
    body: CategoryCreate, service: CategoryService = Depends(get_service)
) -> dict:
    return service.create_category(body)


@router.put("/{category_id}")
def update_category(
    category_id: str,
    body: CategoryUpdate,
    service: CategoryService = Depends(get_service),
) -> dict:
    return service.update_category(category_id, body)


@router.delete("/{category_id}", status_code=204)
def delete_category(
    category_id: str, service: CategoryService = Depends(get_service)
) -> None:
    service.delete_category(category_id)
