"""Order-status logic.

`derive_status` recomputes an order's status from its lines' ready flags after a
line is toggled in the kitchen. It deliberately never touches the manual flow
(`new -> preparing -> ready -> served`) driven by `PATCH /status`: accepting an
order is always manual, and terminal states are immutable here.
"""

from __future__ import annotations

from typing import Iterable


def derive_status(status: str, lines: Iterable[dict]) -> str:
    """Recompute order status from line-ready flags.

    Truth table:
    - served / cancelled                       -> unchanged (terminal)
    - new                                       -> unchanged (accept is manual)
    - preparing AND all lines ready             -> ready
    - ready     AND NOT all lines ready         -> preparing
    - otherwise                                 -> unchanged
    """
    if status in ("served", "cancelled"):
        return status
    if status == "new":
        return status
    all_ready = all(line.get("ready", False) for line in lines)
    if status == "preparing" and all_ready:
        return "ready"
    if status == "ready" and not all_ready:
        return "preparing"
    return status
