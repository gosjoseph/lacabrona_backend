from datetime import datetime

from pydantic import BaseModel, Field


class Provider(BaseModel):
    name: str
    price: float = 0.0  # price per `unit`


class InventoryItem(BaseModel):
    id: str
    name: str
    category: str
    unit: str
    min: float = 0.0
    stock_real: float
    stock_estimated: float
    providers: list[Provider] = Field(default_factory=list)
    updated: datetime
