"""Settings service: defaults-merged read, section-level replace write, and
the pure open/closed status helper.

The status helper is deliberately a stdlib-only pure function so it can be unit
tested without a database or a real clock.
"""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from app.modules.settings.model import Settings
from app.modules.settings.repository import SettingsRepository
from app.modules.settings.schema import SettingsUpdate

# Restaurant timezone — used to evaluate the open/closed status from the
# configured weekly hours.
TZ = "America/Montevideo"

# datetime.weekday(): Monday == 0 ... Sunday == 6
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def compute_open_status(hours: dict, now: datetime) -> dict:
    """Resolve open/closed and the closing time of the active range.

    ``hours`` maps a weekday key ("mon".."sun") to a list of ``{open, close}``
    ranges in "HH:MM". A range whose ``close <= open`` crosses midnight (an
    overnight range that ends the following day). An empty (or missing) list
    means the venue is closed that day.

    Returns ``{"open": bool, "until": "HH:MM" | None}`` where ``until`` is the
    closing time of the currently-active range (None when closed).
    """
    now_t = now.time()

    # 1. Ranges that start on the current weekday.
    today_key = WEEKDAYS[now.weekday()]
    for rng in hours.get(today_key, []) or []:
        opens = _parse_hhmm(rng["open"])
        closes = _parse_hhmm(rng["close"])
        if closes > opens:
            # Same-day range: open within [open, close).
            if opens <= now_t < closes:
                return {"open": True, "until": rng["close"]}
        else:
            # Overnight range: open from `open` today through midnight.
            if now_t >= opens:
                return {"open": True, "until": rng["close"]}

    # 2. Overnight ranges that started yesterday and are still active past
    #    midnight (so a Sat 23:00–02:00 range reads open at Sun 00:30).
    yesterday_key = WEEKDAYS[(now.weekday() - 1) % 7]
    for rng in hours.get(yesterday_key, []) or []:
        opens = _parse_hhmm(rng["open"])
        closes = _parse_hhmm(rng["close"])
        if closes <= opens and now_t < closes:
            return {"open": True, "until": rng["close"]}

    return {"open": False, "until": None}


class SettingsService:
    def __init__(self, repository: SettingsRepository):
        self.repository = repository

    def settings_doc(self) -> dict:
        """Stored settings merged over the defaults (no computed status)."""
        stored = self.repository.find() or {}
        data = {k: stored[k] for k in Settings.model_fields if k in stored}
        return Settings(**data).model_dump()

    def get_settings(self) -> dict:
        """Full defaults-merged settings plus the computed open/closed status.

        The read never mutates the stored document.
        """
        settings = self.settings_doc()
        now = datetime.now(ZoneInfo(TZ))
        settings["status"] = compute_open_status(settings["hours"], now)
        return settings

    def update_settings(self, body: SettingsUpdate) -> dict:
        """Apply a section-level replace and return the updated full settings.

        A provided section replaces that whole section; omitted sections are
        left untouched.
        """
        sections = body.model_dump(exclude_none=True)
        self.repository.replace_sections(sections)
        return self.get_settings()
