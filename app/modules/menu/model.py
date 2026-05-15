from typing import List, Optional

from pydantic import BaseModel, Field


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
