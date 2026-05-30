from typing import List, Optional

from pydantic import BaseModel, Field


class Ingredient(BaseModel):
    inventory_id: str
    qty: float  # in the inventory item's own unit


class MenuItem(BaseModel):
    id: str
    category: str
    name: str
    description: str
    price: float
    unit: str
    tags: List[str] = Field(default_factory=list)
    spice: int = 0
    vegetarian: bool = False
    glutenFree: bool = False
    image: Optional[str] = None
    available: bool = True
    station: Optional[str] = None
    recipe: List[Ingredient] = Field(default_factory=list)
