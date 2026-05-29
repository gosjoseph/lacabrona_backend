from __future__ import annotations

from pymongo.database import Database


class ContentRepository:
    """One document per content key in the ``content`` collection."""

    def __init__(self, db: Database):
        self.collection = db.content

    def find_all(self) -> list[dict]:
        """Return every stored content document (read-only — never writes)."""
        return list(self.collection.find())

    def upsert_many(self, items: dict) -> None:
        """Per-key upsert: each listed key is replaced/created; keys not present
        in ``items`` are left untouched."""
        for key, item in items.items():
            self.collection.update_one(
                {"_id": key},
                {
                    "$set": {
                        "type": item["type"],
                        "value": item["value"],
                        "group": item["group"],
                    }
                },
                upsert=True,
            )
