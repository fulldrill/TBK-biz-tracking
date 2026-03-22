"""
TBK Management user attribution logic.
Used by both the Plaid sync pipeline and the statement parser.

Rules:
  - Zelle where counterparty/description contains Kenny's names → Kenny
  - All other Zelle                                             → Bright
  - Walk-in / cash / teller deposit                            → Bright
  - Debit card / POS purchase                                  → Kenny
  - Everything else                                            → None (unassigned)
"""

_KENNY_KEYWORDS = ["kenneth", "kenny", "manjo"]

_WALK_IN_KEYWORDS = [
    "walk-in", "walk in", "walkin",
    "cash deposit", "counter deposit",
    "teller deposit", "branch deposit",
    "manual deposit", "over the counter",
]

_DEBIT_CARD_KEYWORDS = [
    "pos debit", "pos purchase", "debit card",
    "card purchase", "visa debit", "mastercard debit",
    "point of sale",
]


def assign_user(
    name: str,
    transaction_type: str,          # "debit" | "credit"
    is_zelle: bool,
    zelle_counterparty: str | None = None,
) -> str | None:
    """Return 'Kenny', 'Bright', or None."""
    desc = (name or "").lower()
    counterparty = (zelle_counterparty or "").lower()

    if is_zelle:
        is_kenny = any(k in desc or k in counterparty for k in _KENNY_KEYWORDS)
        return "Kenny" if is_kenny else "Bright"

    if transaction_type == "credit" and any(k in desc for k in _WALK_IN_KEYWORDS):
        return "Bright"

    if transaction_type == "debit" and any(k in desc for k in _DEBIT_CARD_KEYWORDS):
        return "Kenny"

    return None
