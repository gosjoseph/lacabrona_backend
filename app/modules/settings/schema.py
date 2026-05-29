"""Settings update schema.

Every section is optional: a provided section replaces that whole section
(section-level replace); omitted sections are left untouched.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel

from app.modules.settings.model import (
    Channels,
    Charges,
    DeliveryZone,
    HourRange,
    Identity,
    Settings,
    Table,
)

SettingsResponse = Settings


class SettingsUpdate(BaseModel):
    channels: Optional[Channels] = None
    hours: Optional[Dict[str, List[HourRange]]] = None
    delivery_zones: Optional[List[DeliveryZone]] = None
    tables: Optional[List[Table]] = None
    stations: Optional[List[str]] = None
    charges: Optional[Charges] = None
    identity: Optional[Identity] = None
