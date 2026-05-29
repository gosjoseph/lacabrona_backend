from __future__ import annotations

from pymongo.database import Database


class SettingsRepository:
    """Single-document store for the operational settings singleton."""

    DOC_ID = "settings"

    def __init__(self, db: Database):
        self.collection = db.settings

    def find(self) -> dict | None:
        """Return the stored settings document, or None when it doesn't exist."""
        return self.collection.find_one({"_id": self.DOC_ID})

    def replace_sections(self, sections: dict) -> None:
        """Upsert the singleton, replacing each provided top-level section."""
        if not sections:
            # Nothing to write — still ensure the doc exists so reads are stable.
            self.collection.update_one(
                {"_id": self.DOC_ID}, {"$setOnInsert": {"_id": self.DOC_ID}}, upsert=True
            )
            return
        self.collection.update_one(
            {"_id": self.DOC_ID}, {"$set": sections}, upsert=True
        )
