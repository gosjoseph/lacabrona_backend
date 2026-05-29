from fastapi import APIRouter, Depends

from app.core.database import get_db
from app.modules.auth.dependencies import require_employee
from app.modules.settings.repository import SettingsRepository
from app.modules.settings.schema import SettingsUpdate
from app.modules.settings.service import SettingsService

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


def get_service() -> SettingsService:
    return SettingsService(SettingsRepository(get_db()))


@router.get("")
def get_settings(service: SettingsService = Depends(get_service)) -> dict:
    return service.get_settings()


@router.put("", dependencies=[Depends(require_employee)])
def update_settings(
    body: SettingsUpdate, service: SettingsService = Depends(get_service)
) -> dict:
    return service.update_settings(body)
