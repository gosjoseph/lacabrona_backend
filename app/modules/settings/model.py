"""Structured operational settings — a single cached singleton.

Mirrors the existing `db.meta` singleton precedent (one document carrying
shared config): the whole configuration lives in one `settings` document
(`_id="settings"`). A missing document yields the model defaults below — the
read path never writes.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class Channels(BaseModel):
    delivery: bool = True
    pickup: bool = True
    table: bool = True


class HourRange(BaseModel):
    open: str
    close: str


class DeliveryZone(BaseModel):
    id: str
    name: str
    fee: float = 0


class Table(BaseModel):
    id: str
    label: str
    seats: int = 0


class Charges(BaseModel):
    tax_rate: float = 0
    service_rate: float = 0
    tip_default_rate: float = 0
    tax_included: bool = False


class Identity(BaseModel):
    name: str = ""
    tagline: str = ""
    phone: str = ""
    address: str = ""
    neighborhood: str = ""
    social: Dict[str, str] = Field(default_factory=dict)


class Settings(BaseModel):
    channels: Channels = Field(default_factory=Channels)
    # weekday key "mon".."sun" -> list of ranges; empty list means closed.
    hours: Dict[str, List[HourRange]] = Field(default_factory=dict)
    delivery_zones: List[DeliveryZone] = Field(default_factory=list)
    tables: List[Table] = Field(default_factory=list)
    stations: List[str] = Field(default_factory=list)
    charges: Charges = Field(default_factory=Charges)
    identity: Identity = Field(default_factory=Identity)
