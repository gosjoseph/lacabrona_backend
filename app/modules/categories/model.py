from pydantic import BaseModel


class Category(BaseModel):
    id: str
    name: str
    icon: str
    color: str
    order: int
