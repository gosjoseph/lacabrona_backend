from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel

ReservationStatus = Literal["confirmed", "pending", "waitlist", "cancelled"]


class Reservation(BaseModel):
    id: str
    name: str
    party: int
    time: datetime
    table: Optional[int] = None
    status: ReservationStatus = "pending"
    phone: str
    note: str = ""
