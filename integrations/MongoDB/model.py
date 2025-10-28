from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class CreateCollectionRequest(BaseModel):
    name: str = Field(..., description="Collection name")


class DocumentBody(BaseModel):
    data: Dict[str, Any] = Field(default_factory=dict)


class UpdateBody(BaseModel):
    updates: Dict[str, Any] = Field(default_factory=dict)


class QueryBody(BaseModel):
    filter: Dict[str, Any] = Field(default_factory=dict)
    limit: Optional[int] = Field(default=None, ge=1)


class FieldsBody(BaseModel):
    fields: Dict[str, Any] = Field(default_factory=dict)

