import logging

from fastapi import APIRouter, Depends, Query

from app.core.database import get_db
from app.modules.customers.controller import get_customers_service
from app.modules.customers.service import CustomerService
from app.modules.reservations.repository import ReservationRepository
from app.modules.reservations.schema import ReservationCreate, ReservationUpdate
from app.modules.reservations.service import ReservationService

router = APIRouter(prefix="/api/v1/reservations", tags=["reservations"])
logger = logging.getLogger(__name__)


def get_service() -> ReservationService:
    return ReservationService(ReservationRepository(get_db()))


def _safe_upsert(customers: CustomerService, name: str, phone: str) -> None:
    if not phone:
        return
    try:
        customers.upsert(name=name, phone=phone)
    except Exception as exc:  # noqa: BLE001 — hook must never break the caller
        logger.exception("Customer upsert failed (name=%s phone=%s): %s", name, phone, exc)


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
    body: ReservationCreate,
    service: ReservationService = Depends(get_service),
    customers: CustomerService = Depends(get_customers_service),
) -> dict:
    result = service.create_reservation(body)
    _safe_upsert(customers, name=body.name, phone=body.phone)
    return result


@router.put("/{reservation_id}")
def update_reservation(
    reservation_id: str,
    body: ReservationUpdate,
    service: ReservationService = Depends(get_service),
    customers: CustomerService = Depends(get_customers_service),
) -> dict:
    result = service.update_reservation(reservation_id, body)
    phone = result.get("phone")
    name = result.get("name", "")
    if phone:
        _safe_upsert(customers, name=name, phone=phone)
    return result


@router.delete("/{reservation_id}", status_code=204)
def delete_reservation(
    reservation_id: str, service: ReservationService = Depends(get_service)
) -> None:
    service.delete_reservation(reservation_id)
