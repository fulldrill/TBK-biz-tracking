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
    allowed: list[str] | None = None,
) -> str | None:
    """Return an assignee name, or None when it cannot be determined.

    `allowed` is the org's own people list. Orgs do not share owners, so a
    rule that fires for Kenny must not attribute anything in an org he has no
    part in. When the computed name is not on the org's list it falls back to
    that org's sole person if there is exactly one, and to unassigned
    otherwise — a wrong name is worse than no name.
    """
    desc = (name or "").lower()
    counterparty = (zelle_counterparty or "").lower()

    result: str | None = None
    if is_zelle:
        is_kenny = any(k in desc or k in counterparty for k in _KENNY_KEYWORDS)
        result = "Kenny" if is_kenny else "Bright"
    elif transaction_type == "credit" and any(k in desc for k in _WALK_IN_KEYWORDS):
        result = "Bright"
    elif transaction_type == "debit" and any(k in desc for k in _DEBIT_CARD_KEYWORDS):
        result = "Kenny"

    if allowed is not None and result is not None and result not in allowed:
        return allowed[0] if len(allowed) == 1 else None

    return result
