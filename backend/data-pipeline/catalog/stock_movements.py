"""The rules for changing a stock count, and how ledger rows read back.

A count changes because something happened to the stock, and each kind of event moves the
count one way only:

    received              + units                              RESTOCK
    sold                  - available units, sellable places   SALE
    shipped elsewhere     - units here, + units there          TRANSFER_OUT + TRANSFER_IN
    damaged / lost        - available units                    DAMAGE / LOST
    customer return       + units (or written off at once)     RETURN (+ DAMAGE)
    count correction      = the counted quantity               ADJUST

Only a count correction replaces a count, and in doing so it hides whatever explains the
difference: a sale nobody recorded, theft, a miscount. So only workspace owners and admins
may make one, and they must say why. Putting stock where there is none yet is opening stock,
not a correction.

"Available" means on hand minus reserved: units promised to a customer can't be sold,
shipped or written off until the reservation is released.

``ProductService`` applies these rules; this module holds what the service, the routes and
the tests share.
"""

from __future__ import annotations

from typing import Dict, Optional

MAX_ON_HAND = 2_147_483_647  # catalog.inventory_level.qty_on_hand is a 32-bit integer

# Rows that record a hold on stock (qty_reserved) and leave qty_on_hand alone.
HOLD_REASONS = ("RESERVE", "RELEASE")

TOTAL_FIELDS = (
    "received", "sold", "shipped_out", "shipped_in", "damaged", "lost", "returned", "corrected_up", "corrected_down",
)

# reason -> (total it adds to, direction it normally moves stock)
_NATURAL_DIRECTION = {
    "RESTOCK": ("received", +1),
    "RETURN": ("returned", +1),
    "TRANSFER_IN": ("shipped_in", +1),
    "SALE": ("sold", -1),
    "TRANSFER_OUT": ("shipped_out", -1),
    "DAMAGE": ("damaged", -1),
    "LOST": ("lost", -1),
}

_TYPE_BY_REASON = {
    "RESTOCK": "RECEIVED",
    "RETURN": "RETURNED",
    "TRANSFER_IN": "SHIPPED_IN",
    "SALE": "SOLD",
    "TRANSFER_OUT": "SHIPPED_OUT",
    "DAMAGE": "DAMAGED",
    "LOST": "LOST",
    "ADJUST": "CORRECTION",
    "RESERVE": "RESERVED",
    "RELEASE": "RELEASED",
}


class StockPermissionError(PermissionError):
    """The caller's workspace role doesn't allow this stock change (HTTP 403)."""


class StockConflictError(ValueError):
    """The stock changed after the caller read it (HTTP 409)."""


def clean_text(value: Optional[str]) -> Optional[str]:
    """Trimmed text, or None when nothing is left."""
    value = (value or "").strip()
    return value or None


def movement_type(reason: str, delta: int) -> str:
    """How a ledger row reads to a person.

    Before typed movements existed, every "Update Stock" overwrote the count and was logged
    as RESTOCK or ADJUST whatever the direction, so a row that moved stock against its
    reason's direction was really a count correction.
    """
    natural = _NATURAL_DIRECTION.get(reason)
    if natural and delta and (delta > 0) != (natural[1] > 0):
        return "CORRECTION"
    return _TYPE_BY_REASON.get(reason, "CORRECTION")


def add_to_totals(totals: Dict[str, int], reason: str, units_in: int, units_out: int, count: int) -> None:
    """Add one (reason, units in, units out) group of ledger rows to a location's totals."""
    if reason in HOLD_REASONS:
        return
    natural = _NATURAL_DIRECTION.get(reason)
    if natural is None:  # ADJUST
        totals["corrected_up"] += units_in
        totals["corrected_down"] += units_out
    else:
        field, direction = natural
        if direction > 0:
            totals[field] += units_in
            totals["corrected_down"] += units_out
        else:
            totals[field] += units_out
            totals["corrected_up"] += units_in
    totals["movements"] += count
    totals["net_change"] += units_in - units_out


def empty_totals() -> Dict[str, int]:
    return {field: 0 for field in (*TOTAL_FIELDS, "net_change", "movements")}
