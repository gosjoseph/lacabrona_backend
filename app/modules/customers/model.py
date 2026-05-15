from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field

from app.core.utils import utcnow


class Customer(BaseModel):
    """Customer profile authenticated via SuperTokens ThirdParty (Google)."""

    id: Optional[str] = None
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    supertokens_user_id: Optional[str] = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
