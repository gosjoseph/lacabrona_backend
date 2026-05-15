from datetime import datetime, timezone

from fastapi import HTTPException

from app.modules.reservations.model import Reservation
from app.modules.reservations.repository import ReservationRepository
from app.modules.reservations.schema import ReservationCreate, ReservationUpdate


class ReservationService:
    def __init__(self, repository: ReservationRepository):
        self.repository = repository

    def list_reservations(self, date: str | None = None) -> dict:
        start: datetime | None = None
        end: datetime | None = None
        if date:
            try:
                start = datetime.fromisoformat(date)
                end = datetime.fromisoformat(date).replace(hour=23, minute=59, second=59)
            except Exception:
                raise HTTPException(400, "Invalid date format (use YYYY-MM-DD)")
        reservations = self.repository.list(start, end)
        today = datetime.now(timezone.utc).date().isoformat()
        return {"today": today, "reservations": reservations}

    def get_reservation(self, reservation_id: str) -> dict:
        doc = self.repository.find_by_id(reservation_id)
        if not doc:
            raise HTTPException(404, "Reservation not found")
        return doc

    def create_reservation(self, body: ReservationCreate) -> dict:
        reservation = Reservation(id=self._next_id(), **body.model_dump())
        data = reservation.model_dump()
        self.repository.insert(data)
        return data

    def update_reservation(self, reservation_id: str, body: ReservationUpdate) -> dict:
        updates = body.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(400, "No fields to update")
        if not self.repository.update(reservation_id, updates):
            raise HTTPException(404, "Reservation not found")
        return self.repository.find_by_id(reservation_id)

    def delete_reservation(self, reservation_id: str) -> None:
        if not self.repository.delete(reservation_id):
            raise HTTPException(404, "Reservation not found")

    def _next_id(self) -> str:
        last = self.repository.find_latest()
        if not last:
            return "rs-2401"
        try:
            n = int(str(last["id"]).split("-")[-1])
            return f"rs-{n + 1}"
        except Exception:
            return f"rs-{int(datetime.now(timezone.utc).timestamp())}"
