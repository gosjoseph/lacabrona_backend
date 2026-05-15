from datetime import datetime

from pydantic import BaseModel


class InventoryItem(BaseModel):
    id: str
    name: str
    category: str
    stock: float
    unit: str
    min: float
    supplier: str
    updated: datetime
