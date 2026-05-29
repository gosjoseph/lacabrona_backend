"""Shared station resolution for kitchen routing.

A single source of truth maps a menu-item id to the kitchen station that should
prepare it: the item's own ``station`` wins; otherwise its category's
``default_station``; otherwise the literal ``"general"`` fallback.

The resolver is built from the menu and category collections so both order
creation (stamping the station onto every new line) and the kitchen read
(back-filling legacy lines) resolve identically.
"""

from __future__ import annotations

FALLBACK_STATION = "general"


class StationResolver:
    def __init__(self, menu_by_id: dict[str, dict], category_by_id: dict[str, dict]):
        self._menu_by_id = menu_by_id
        self._category_by_id = category_by_id

    @classmethod
    def from_repositories(cls, menu_repository, category_repository) -> "StationResolver":
        menu_by_id = {item["id"]: item for item in menu_repository.list()}
        category_by_id = {cat["id"]: cat for cat in category_repository.list()}
        return cls(menu_by_id, category_by_id)

    def station_for(self, item_id: str) -> str:
        """Resolve the station for a menu-item id, never returning None."""
        item = self._menu_by_id.get(item_id) or {}
        if item.get("station"):
            return item["station"]
        category = self._category_by_id.get(item.get("category")) or {}
        if category.get("default_station"):
            return category["default_station"]
        return FALLBACK_STATION
