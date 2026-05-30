from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.modules.inventory.model import InventoryItem, Provider

InventoryItemResponse = InventoryItem


class InventoryItemCreate(BaseModel):
    id: str
    name: str
    category: str
    unit: str
    min: float = 0.0
    stock_real: float
    # When omitted the service defaults estimated to the real count.
    stock_estimated: Optional[float] = None
    providers: list[Provider] = Field(default_factory=list)


class InventoryUpdate(BaseModel):
    """Metadata-only patch. Stock changes go through /restock, never here."""

    name: Optional[str] = None
    category: Optional[str] = None
    min: Optional[float] = None
    providers: Optional[list[Provider]] = None


class InventoryRestock(BaseModel):
    mode: Literal["add", "set"]
    amount: float
    note: Optional[str] = None
