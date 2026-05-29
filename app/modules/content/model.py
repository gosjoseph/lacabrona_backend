"""Free-form site content store — one document per key.

Each document is ``{_id: <key>, type, value, group}``. The keyspace is
deliberately open: any string key is accepted, so adding new editable copy on
the frontend needs no backend change. The read path never writes; an empty
collection yields an empty map.

This module owns PURE COPY ONLY. Contact details, the open/closed status and
business hours live in the ``settings`` module — they are never re-owned here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# The only value kinds the editor understands. ``richtext`` is rendered on the
# frontend as preserved-linebreak plain text (never HTML).
ContentType = Literal["text", "richtext", "image"]


class ContentItem(BaseModel):
    type: ContentType
    value: str
    group: str
