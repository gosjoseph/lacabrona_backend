from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.modules.reservations.model import Reservation, ReservationStatus

ReservationResponse = Reservation


class ReservationCreate(BaseModel):
    name: str
    party: int
    time: datetime
    table: Optional[int] = None
    status: ReservationStatus = "pending"
    phone: str
    note: str = ""


class ReservationUpdate(BaseModel):
    name: Optional[str] = None
    party: Optional[int] = None
    time: Optional[datetime] = None
    table: Optional[int] = None
    status: Optional[ReservationStatus] = None
    phone: Optional[str] = None
    note: Optional[str] = None
