from __future__ import annotations

from app.modules.content.repository import ContentRepository
from app.modules.content.schema import ContentUpdate


class ContentService:
    def __init__(self, repository: ContentRepository):
        self.repository = repository

    def get_content(self) -> dict:
        """All stored content keyed by id. The read never writes; an empty
        collection yields ``{"items": {}}``."""
        items = {
            doc["_id"]: {
                "type": doc["type"],
                "value": doc["value"],
                "group": doc["group"],
            }
            for doc in self.repository.find_all()
        }
        return {"items": items}

    def update_content(self, body: ContentUpdate) -> dict:
        """Per-key upsert of the provided items; returns the full stored map."""
        items = {key: item.model_dump() for key, item in body.items.items()}
        self.repository.upsert_many(items)
        return self.get_content()
