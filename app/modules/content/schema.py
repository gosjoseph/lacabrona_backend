"""Content write schema.

The write body is a per-key map of items. Listed keys are upserted
(replaced/created); unlisted keys are left untouched. ``type`` is constrained
to the allowed set by ``ContentItem``, so an invalid type yields 422.
"""

from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, Field

from app.modules.content.model import ContentItem


class ContentUpdate(BaseModel):
    items: Dict[str, ContentItem] = Field(default_factory=dict)
