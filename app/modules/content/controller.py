from fastapi import APIRouter, Depends

from app.core.database import get_db
from app.modules.auth.dependencies import require_employee
from app.modules.content.repository import ContentRepository
from app.modules.content.schema import ContentUpdate
from app.modules.content.service import ContentService

router = APIRouter(prefix="/api/v1/content", tags=["content"])


def get_service() -> ContentService:
    return ContentService(ContentRepository(get_db()))


@router.get("")
def get_content(service: ContentService = Depends(get_service)) -> dict:
    return service.get_content()


@router.put("", dependencies=[Depends(require_employee)])
def update_content(
    body: ContentUpdate, service: ContentService = Depends(get_service)
) -> dict:
    return service.update_content(body)
