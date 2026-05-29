from fastapi import APIRouter, Depends, File, UploadFile

from app.modules.auth.dependencies import require_employee
from app.modules.uploads.service import ImageStore, get_image_store, validate_image

router = APIRouter(prefix="/api/v1/uploads", tags=["uploads"])


@router.post("/image", dependencies=[Depends(require_employee)])
async def upload_image(
    file: UploadFile = File(...),
    store: ImageStore = Depends(get_image_store),
) -> dict:
    data = await file.read()
    validate_image(file.content_type or "", len(data))
    return store.save(data, file.content_type or "")
