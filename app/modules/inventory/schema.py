from typing import Optional

from pydantic import BaseModel

from app.modules.inventory.model import InventoryItem

InventoryItemCreate = InventoryItem
InventoryItemResponse = InventoryItem


class InventoryUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    stock: Optional[float] = None
    min: Optional[float] = None
    supplier: Optional[str] = None


class InventoryAdjust(BaseModel):
    delta: float
    note: Optional[str] = None
