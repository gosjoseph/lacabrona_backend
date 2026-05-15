from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


# ---------- Categories ----------
class Category(BaseModel):
    id: str
    name: str
    icon: str
    color: str
    order: int


# ---------- Menu ----------
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


# ---------- Inventory ----------
class InventoryItem(BaseModel):
    id: str
    name: str
    category: str
    stock: float
    unit: str
    min: float
    supplier: str
    updated: datetime


class InventoryAdjust(BaseModel):
    delta: float
    note: Optional[str] = None


class InventoryUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    stock: Optional[float] = None
    min: Optional[float] = None
    supplier: Optional[str] = None


# ---------- Orders ----------
OrderStatus = Literal["new", "preparing", "ready", "served", "cancelled"]
OrderChannel = Literal["delivery", "table", "pickup"]


class OrderLine(BaseModel):
    id: str
    qty: int
    subtotal: float


class Order(BaseModel):
    id: str
    channel: OrderChannel
    created: datetime
    status: OrderStatus = "new"
    customer: str
    address: Optional[str] = None
    phone: Optional[str] = None
    table: Optional[int] = None
    items: List[OrderLine]
    subtotal: float
    delivery: float = 0
    total: float
    etaMinutes: Optional[int] = None


class OrderCreate(BaseModel):
    channel: OrderChannel
    customer: str
    address: Optional[str] = None
    phone: Optional[str] = None
    table: Optional[int] = None
    items: List[OrderLine]
    delivery: float = 0
    etaMinutes: Optional[int] = None


class OrderStatusUpdate(BaseModel):
    status: OrderStatus


# ---------- Reservations ----------
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


class ReservationCreate(BaseModel):
    name: str
    party: int
    time: datetime
    table: Optional[int] = None
    status: ReservationStatus = "pending"
    phone: str
    note: str = ""


class ReservationUpdate(BaseModel):
    name: Optional[str] = None
    party: Optional[int] = None
    time: Optional[datetime] = None
    table: Optional[int] = None
    status: Optional[ReservationStatus] = None
    phone: Optional[str] = None
    note: Optional[str] = None
