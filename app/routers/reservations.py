from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from ..db import get_db
from ..models import Reservation, ReservationCreate, ReservationUpdate

router = APIRouter(prefix="/api/reservations", tags=["reservations"])


def _clean(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


def _next_id() -> str:
    db = get_db()
    last = db.reservations.find_one(sort=[("time", -1)])
    if not last:
        return "rs-2401"
    try:
        n = int(str(last["id"]).split("-")[-1])
        return f"rs-{n + 1}"
    except Exception:
        return f"rs-{int(datetime.now(timezone.utc).timestamp())}"


@router.get("")
def list_reservations(date: str | None = Query(None, description="YYYY-MM-DD")) -> dict:
    db = get_db()
    q: dict = {}
    if date:
        try:
            start = datetime.fromisoformat(date)
            end = datetime.fromisoformat(date).replace(hour=23, minute=59, second=59)
            q["time"] = {"$gte": start, "$lte": end}
        except Exception:
            raise HTTPException(400, "Invalid date format (use YYYY-MM-DD)")
    reservations = [_clean(d) for d in db.reservations.find(q).sort("time", 1)]
    today = datetime.now(timezone.utc).date().isoformat()
    return {"today": today, "reservations": reservations}


@router.get("/{reservation_id}")
def get_reservation(reservation_id: str) -> dict:
    doc = get_db().reservations.find_one({"id": reservation_id})
    if not doc:
        raise HTTPException(404, "Reservation not found")
    return _clean(doc)


@router.post("", status_code=201)
def create_reservation(body: ReservationCreate) -> dict:
    reservation = Reservation(id=_next_id(), **body.model_dump())
    get_db().reservations.insert_one(reservation.model_dump())
    return reservation.model_dump()


@router.put("/{reservation_id}")
def update_reservation(reservation_id: str, body: ReservationUpdate) -> dict:
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")
    db = get_db()
    res = db.reservations.update_one({"id": reservation_id}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Reservation not found")
    return _clean(db.reservations.find_one({"id": reservation_id}))


@router.delete("/{reservation_id}", status_code=204)
def delete_reservation(reservation_id: str) -> None:
    res = get_db().reservations.delete_one({"id": reservation_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Reservation not found")
