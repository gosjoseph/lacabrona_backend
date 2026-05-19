from fastapi import APIRouter, Depends, Query

from app.core.database import get_db
from app.modules.reservations.repository import ReservationRepository
from app.modules.reservations.schema import ReservationCreate, ReservationUpdate
from app.modules.reservations.service import ReservationService

router = APIRouter(prefix="/api/v1/reservations", tags=["reservations"])


def get_service() -> ReservationService:
    return ReservationService(ReservationRepository(get_db()))


@router.get("")
def list_reservations(
    date: str | None = Query(None, description="YYYY-MM-DD"),
    service: ReservationService = Depends(get_service),
) -> dict:
    return service.list_reservations(date)


@router.get("/{reservation_id}")
def get_reservation(
    reservation_id: str, service: ReservationService = Depends(get_service)
) -> dict:
    return service.get_reservation(reservation_id)


@router.post("", status_code=201)
def create_reservation(
    body: ReservationCreate, service: ReservationService = Depends(get_service)
) -> dict:
    return service.create_reservation(body)


@router.put("/{reservation_id}")
def update_reservation(
    reservation_id: str,
    body: ReservationUpdate,
    service: ReservationService = Depends(get_service),
) -> dict:
    return service.update_reservation(reservation_id, body)


@router.delete("/{reservation_id}", status_code=204)
def delete_reservation(
    reservation_id: str, service: ReservationService = Depends(get_service)
) -> None:
    service.delete_reservation(reservation_id)
