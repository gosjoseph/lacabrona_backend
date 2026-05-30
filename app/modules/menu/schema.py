from typing import List, Optional

from pydantic import BaseModel

from app.modules.menu.model import Ingredient, MenuItem

MenuItemCreate = MenuItem
MenuItemResponse = MenuItem


class MenuItemUpdate(BaseModel):
    category: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    unit: Optional[str] = None
    tags: Optional[List[str]] = None
    spice: Optional[int] = None
    vegetarian: Optional[bool] = None
    glutenFree: Optional[bool] = None
    image: Optional[str] = None
    available: Optional[bool] = None
    station: Optional[str] = None
    # Optional + None default: omitting `recipe` leaves the stored recipe
    # untouched (exclude_none drops it); passing `recipe=[]` (not None) clears it.
    recipe: Optional[List[Ingredient]] = None
