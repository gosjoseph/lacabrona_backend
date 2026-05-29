import re
from datetime import datetime, timezone

_PHONE_STRIP_RE = re.compile(r"[\s\-\(\)\.]")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def strip_mongo_id(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc


def normalize_phone(s) -> str:
    """Strip ASCII whitespace, dashes, parens, dots; preserve any leading '+'.

    Returns "" for None or empty input.
    """
    if not s:
        return ""
    return _PHONE_STRIP_RE.sub("", str(s))


def normalize_email(s) -> str:
    """Trim surrounding whitespace and lowercase an email.

    Returns "" for None or empty input. Used to populate `email_normalized`
    so customers can be matched/linked case-insensitively.
    """
    if not s:
        return ""
    return str(s).strip().lower()
