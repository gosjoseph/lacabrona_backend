from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.core.utils import utcnow


class Employee(BaseModel):
    """Staff/admin user authenticated via SuperTokens ThirdParty (Google)."""

    id: Optional[str] = None
    email: Optional[EmailStr] = None
    name: Optional[str] = None
    role: str = "admin"
    supertokens_user_id: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
