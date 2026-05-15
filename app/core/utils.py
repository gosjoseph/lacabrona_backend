from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def strip_mongo_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc
